/**
 * clock-adapter - drives TanukiLipSync from the Python controller's playback
 * clock instead of from a browser <audio> element.
 *
 * The controller owns playback (goal.md section 5): audio comes out of the PC's
 * output device through PortAudio, and the browser never plays the same clip.
 * So the mouth has no local audio element to read a time from. It gets
 * position snapshots over the control connection and animates against them:
 *
 *     const adapter = new PlaybackClockAdapter({ onStop: () => tanuki.stop() });
 *     // for every clip:
 *     adapter.arm();                         // immediately before playTrack
 *     tanuki.playTrack(track, adapter.getTime);
 *     // ...for every snapshot the controller sends:
 *     adapter.accept(snapshot);
 *
 * **Lifecycle.** `arm()` is required before every `playTrack`, and it is the
 * only way out of a stop. It clears the previous clip's position (so clip B is
 * never sampled at clip A's last time), starts the staleness clock (so a
 * controller that never sends a first snapshot is a fault, not a frozen mouth),
 * and refuses snapshots from clips older than the one being armed for. Every
 * stop - clip end, fault, disconnect, staleness, supersession, an operator
 * stop - is latched until the next `arm()`: a later snapshot cannot silently
 * un-stop the adapter, and `onStop` fires once per armed clip. A not-playing
 * snapshot that arrives before this arm has seen its clip playing is ignored
 * rather than read as a stop: nothing has started for it to end, and the
 * staleness clock still runs from `arm()`, so a controller that never starts
 * the clip is still a fault. Construction counts as an arm.
 *
 * Three things this has to get right, and they are the whole reason it exists.
 *
 * **It extrapolates from arrival, not from the controller's clock.** A snapshot
 * carries `controller_time`, but that is a `perf_counter` reading inside
 * another process; the browser's `performance.now()` has a different epoch and
 * its own drift, and goal.md section 7 is explicit that browser timing is not
 * authoritative. Mapping between the two would mean estimating a clock offset
 * from the same transport whose latency is the thing being estimated. Instead
 * the adapter timestamps each snapshot on arrival and extrapolates from there.
 * The cost is honest and bounded: the mouth lags by however long the snapshot
 * took to arrive (L). During a clip's pre-roll the lag is about 2L, because
 * `pre_roll_s` is stated relative to `controller_time` but subtracted from an
 * arrival-based age, so the remaining pre-roll is overstated by L as well. On
 * loopback both are sub-millisecond, but they are real biases, they are never
 * subtracted out, and `transportBiasNote` records them.
 *
 * **A stale clock is a fault, not a freeze.** An external-clock track has no
 * end event of its own - `TanukiLipSync.update()` only calls `_finish()` when
 * it owns an `<audio>` element. If the controller stops sending snapshots
 * (crash, disconnect, hung Wi-Fi), a naive adapter would keep extrapolating
 * forever and hold the mouth open on a Tanuki that is silent. So past
 * `staleAfter` - measured from the last snapshot, or from `arm()` when none
 * has arrived yet - the adapter stops and reports a fault.
 *
 * **It stops on every ending.** Clip end, abort, fault and disconnect all have
 * to call `stop()`, because nothing else will. Clip end is the *audible* end:
 * the controller keeps publishing `playing: true` through the tail of a clip
 * that is still coming out of the device buffer.
 *
 * Framework-free and with no DOM or three.js dependency, so it runs under Node
 * for tests. Inject `now` to make those tests deterministic.
 */

/** Reasons the adapter stopped driving the mouth. */
export const STOP_CLIP_END = 'clip_end';
export const STOP_STALE = 'stale_clock';
export const STOP_FAULT = 'fault';
export const STOP_DISCONNECTED = 'disconnected';
export const STOP_SUPERSEDED = 'superseded';
export const STOP_REQUESTED = 'requested';

/** Default staleness limit. Matches `stale_after_s` in timing.interpolate. */
export const DEFAULT_STALE_AFTER_MS = 250;

/**
 * Map the controller's `ended_reason` onto a stop reason.
 *
 * `clip_end` is the clip finishing on its own. Anything else came from a
 * controller decision - an operator stop, a fault, the session moving on - and
 * is reported as such rather than as a completed clip, because the protocol
 * keeps those terminal reasons apart.
 */
export function endedReasonToStop(reason) {
  if (reason === 'clip_end') return STOP_CLIP_END;
  if (reason === null || reason === undefined) return STOP_REQUESTED;
  if (/fault/i.test(reason)) return STOP_FAULT;
  return STOP_REQUESTED;
}

export class PlaybackClockAdapter {
  /**
   * @param {object}   [o]
   * @param {(reason: string, detail: object) => void} [o.onStop]
   *        Called once per armed clip. Wire this to `tanuki.stop()`.
   * @param {(fault: object) => void} [o.onFault]
   *        Called for a stale clock or a rejected snapshot, before onStop.
   * @param {number}   [o.staleAfterMs]
   * @param {() => number} [o.now]  milliseconds; defaults to performance.now.
   */
  constructor({ onStop = null, onFault = null,
                staleAfterMs = DEFAULT_STALE_AFTER_MS, now = null } = {}) {
    this._onStop = onStop;
    this._onFault = onFault;
    this.staleAfterMs = staleAfterMs;
    this._now = now || (typeof performance !== 'undefined'
      ? () => performance.now()
      : () => Date.now());

    this.snapshot = null;       // last accepted snapshot
    this.arrivedAt = 0;         // local time it arrived, ms
    this.generation = null;     // controller generation of the driven clip
    this.minGeneration = null;  // oldest generation this arm will take
    this.seenPlaying = false;   // has this arm seen its clip playing?
    this.armedAt = this._now(); // staleness origin until a snapshot arrives
    this.stopped = false;
    this.stopReason = null;
    this.faults = [];
    this.accepted = 0;
    this.rejected = 0;          // malformed or superseded
    this.ignored = 0;           // well-formed, but nothing to act on
    this.lastFileTime = 0;      // monotonic guard, seconds

    // getTime is handed to playTrack, which calls it once per frame. Bound so
    // it can be passed as a bare function.
    this.getTime = () => this.fileTime();
  }

  /**
   * Prepare for the next clip. Call immediately before `playTrack`.
   *
   * @param {object} [o]
   * @param {number} [o.generation] the controller generation to drive, when
   *        known. Snapshots older than it are refused. Pass the current
   *        generation to resume the same clip after a stale stop. When omitted,
   *        anything newer than the last clip this adapter drove is accepted.
   */
  arm({ generation } = {}) {
    if (typeof generation === 'number' && Number.isFinite(generation)) {
      this.minGeneration = generation;
    } else if (this.generation !== null) {
      this.minGeneration = this.generation + 1;
    }
    this.generation = null;
    this.snapshot = null;
    this.lastFileTime = 0;
    this.stopped = false;
    this.stopReason = null;
    this.seenPlaying = false;
    this.armedAt = this._now();
  }

  /**
   * Take a position snapshot from the controller.
   *
   * Shape matches `timing.PlaybackPosition.as_record()`: `file_time`,
   * `controller_time`, `rate`, `playing`, `duration`, `generation`, and
   * optionally `pre_roll_s`, `audible_end_s` and `ended_reason`.
   *
   * @returns {boolean} whether the snapshot was acted on.
   */
  accept(snapshot) {
    if (!snapshot || typeof snapshot.file_time !== 'number'
        || !Number.isFinite(snapshot.file_time)
        || typeof snapshot.rate !== 'number'
        || typeof snapshot.duration !== 'number'
        || typeof snapshot.generation !== 'number'
        || !Number.isFinite(snapshot.generation)) {
      // A snapshot with no generation would escape the supersede check below,
      // so it is malformed rather than assumed to be the current clip.
      this._fault('malformed_snapshot', 'snapshot missing required fields');
      this.rejected++;
      return false;
    }

    // Latched: only arm() leaves a stop. Without this a same-generation
    // snapshot already in flight would silently mark a faulted or
    // operator-stopped adapter live again (R05-F08).
    if (this.stopped) {
      this.ignored++;
      return false;
    }

    // A snapshot from a clip the controller has moved on from must not drive
    // the mouth: the controller bumps its generation on every play, commit and
    // stop, so an out-of-order or late-delivered snapshot is detectable here
    // rather than animating the wrong clip.
    const g = snapshot.generation;
    if ((this.minGeneration !== null && g < this.minGeneration)
        || (this.generation !== null && g < this.generation)) {
      this.rejected++;
      return false;
    }

    // `playing: false` is how the controller reports clip end, stop and idle.
    // It is the only end signal this adapter gets, and the controller states
    // which of them it was: an idle snapshot carries no clip, so inferring
    // "did it finish?" from whether file_time reached duration is not
    // possible. A controller stop bumps the generation, so a newer
    // not-playing snapshot is still the end of this clip.
    if (!snapshot.playing || snapshot.rate === 0) {
      if (!this.seenPlaying) {
        // Nothing has started for this to end: an idle controller before the
        // clip starts, or a previous clip's stop arriving late. Reading it as
        // a stop tore the mouth down for a whole clip (R05-F05).
        this.ignored++;
        return false;
      }
      this.snapshot = snapshot;
      this.arrivedAt = this._now();
      this.accepted++;
      this._stop(endedReasonToStop(snapshot.ended_reason));
      return true;
    }

    if (this.generation !== null && g > this.generation) {
      // A different clip is now playing. The renderer still holds this clip's
      // track, so following the new position would animate the wrong track.
      // The UI arms again and calls playTrack with the new track.
      this._stop(STOP_SUPERSEDED);
      return false;
    }

    this.generation = g;
    this.seenPlaying = true;
    this.snapshot = snapshot;
    this.arrivedAt = this._now();
    this.accepted++;
    return true;
  }

  /**
   * Current position in the clip, in seconds of *file* time.
   *
   * File time, not elapsed time: the mouth track is indexed from the start of
   * the complete WAV including any leading silence, so this is what
   * `playTrack` needs.
   */
  fileTime() {
    if (this.stopped) return this.lastFileTime;

    if (!this.snapshot) {
      // Armed, but the controller has not said anything yet. The clock runs
      // from arm(): a transport that dies before its first snapshot must not
      // leave the mouth parked on a speaking pose with no fault (R05-F04).
      const waitedMs = this._now() - this.armedAt;
      if (waitedMs > this.staleAfterMs) {
        this._fault('stale_clock',
          `no position snapshot ${waitedMs.toFixed(0)} ms after arm `
          + `(limit ${this.staleAfterMs} ms)`);
        this._stop(STOP_STALE);
      }
      return this.lastFileTime;
    }

    const ageMs = this._now() - this.arrivedAt;
    if (ageMs > this.staleAfterMs) {
      // The controller has gone quiet. Extrapolating further would hold the
      // mouth open on a Tanuki that may not be speaking at all.
      this._fault('stale_clock',
        `no position update for ${ageMs.toFixed(0)} ms `
        + `(limit ${this.staleAfterMs} ms)`);
      this._stop(STOP_STALE);
      return this.lastFileTime;
    }

    // Nothing is audible during the pre-roll, so the position must not
    // advance through it. The controller publishes how much of it was left
    // when the snapshot was taken; without honouring it the mouth leads the
    // sound by the device latency at the start of every clip, which a
    // cross-check against a recorded controller trace caught.
    const preRollMs = (this.snapshot.pre_roll_s || 0) * 1000;
    const effectiveAgeMs = Math.max(0, ageMs - preRollMs);
    let t = this.snapshot.file_time
      + (effectiveAgeMs / 1000) * this.snapshot.rate;
    if (t < 0) t = 0;
    if (t > this.snapshot.duration) t = this.snapshot.duration;
    // Never let the sampled position go backwards within one clip: a snapshot
    // that arrives slightly stale behind an extrapolated frame would otherwise
    // make the mouth stutter.
    if (t < this.lastFileTime) t = this.lastFileTime;
    this.lastFileTime = t;
    return t;
  }

  /** The control connection dropped. */
  disconnected(detail = 'control connection lost') {
    this._fault('disconnected', detail);
    this._stop(STOP_DISCONNECTED);
  }

  /** The controller reported a fault. */
  fault(detail = 'controller fault') {
    this._fault('controller_fault', detail);
    this._stop(STOP_FAULT);
  }

  /** Operator stop, or the session moving on. */
  stop(reason = STOP_REQUESTED) {
    this._stop(reason);
  }

  /** Milliseconds since the last accepted snapshot, or since arm(). */
  age() {
    return this._now() - (this.snapshot ? this.arrivedAt : this.armedAt);
  }

  isStale() {
    return this.age() > this.staleAfterMs;
  }

  /** What this adapter cannot tell you, for the record. */
  get transportBiasNote() {
    return 'Position is extrapolated from snapshot arrival, so the mouth lags '
      + 'by the transport latency L of the control connection, and by about '
      + '2L during a clip pre-roll (pre_roll_s is relative to controller time '
      + 'but is subtracted from an arrival-based age). That bias is not '
      + 'measured or compensated here and is not an acoustic measurement of '
      + 'anything.';
  }

  _fault(kind, detail) {
    const fault = { kind, detail, at: this._now() };
    this.faults.push(fault);
    if (this._onFault) this._onFault(fault);
  }

  _stop(reason) {
    if (this.stopped) return;
    this.stopped = true;
    this.stopReason = reason;
    if (this._onStop) {
      this._onStop(reason, {
        fileTime: this.lastFileTime,
        generation: this.generation,
        faults: this.faults.length,
      });
    }
  }
}

export default PlaybackClockAdapter;
