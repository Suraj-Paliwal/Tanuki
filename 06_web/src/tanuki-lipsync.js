/**
 * tanuki-lipsync - drives the tanuki rig's morph targets from Japanese speech.
 *
 * Framework-free. Give it the loaded glTF scene and call update() each frame.
 *
 *   import { TanukiLipSync } from 'tanuki-lipsync';
 *
 *   const tanuki = await TanukiLipSync.load('/models/tanuki_visemes.glb', loader);
 *   scene.add(tanuki.object);
 *
 *   renderer.setAnimationLoop(() => { tanuki.update(clock.getDelta()); ... });
 *
 *   await tanuki.speak({ audio: '/tts/line.mp3', track });  // text-driven
 *   await tanuki.speak({ audio: '/tts/line.mp3' });         // live analysis
 */
import { VowelTracker, VISEMES } from './formants.js';
import { BandAnalyser } from './bands.js';

const MOUTH = VISEMES;                       // A I U E O
const ALL   = [...MOUTH, 'Blink', 'BlinkL', 'BlinkR'];

export class TanukiLipSync {
  /**
   * @param {THREE.Object3D} object  the loaded glTF scene (or the mesh root)
   */
  constructor(object, opts = {}) {
    this.object = object;
    this.targets = [];                       // {mesh, index} per morph name
    this.byName = new Map();
    this.current = Object.fromEntries(ALL.map((n) => [n, 0]));
    this.goal    = Object.fromEntries(ALL.map((n) => [n, 0]));

    // Attack faster than release: a mouth snaps open and eases shut, and equal
    // times read as rubbery.
    // Attack faster than release: a mouth snaps open and eases shut, and equal
    // times read as rubbery. Both kept short, because an exponential filter
    // lags its input by roughly its own time constant - 45 ms of attack is
    // 45 ms of the mouth trailing the voice, which is right at the edge of
    // what reads as out of sync.
    this.attack  = opts.attack  ?? 0.022;
    this.release = opts.release ?? 0.055;

    // ── timing ────────────────────────────────────────────────────────────
    // audio.currentTime reports the DECODER position. The sound still has to
    // cross the output buffer and the hardware before it reaches the listener,
    // so driving the mouth straight off currentTime always renders it late.
    // The Web Audio API measures that delay for us - AudioContext.outputLatency
    // is exactly this number, and it is the difference between wired earbuds
    // (~10 ms) and Bluetooth (~150 ms+), which is far too large to leave to a
    // hand-set constant.
    this.autoLatency = opts.autoLatency ?? true;
    this.measuredLatency = 0;

    // Anticipatory lead. Two reasons, and they point the same way:
    //   1. Real speech is anticipatory - the lips start forming a vowel during
    //      the consonant before it. A mouth that moves exactly on the sound
    //      already looks a beat behind.
    //   2. The perceptual tolerance is asymmetric. ITU-R BT.1359 puts the
    //      detectability threshold at 45 ms of audio LEADING video against
    //      125 ms of audio LAGGING it; ATSC allows 15 ms lead and 45 ms lag.
    //      Erring early is roughly three times safer than erring late.
    this.lead = opts.lead ?? 0.03;

    // Manual trim on top of the measured value. Should not normally be needed.
    this.offset = opts.offset ?? 0.0;

    // ── band energy ───────────────────────────────────────────────────────
    // Split the audio into three bands and hand them to whatever drives the
    // body. The mouth does NOT use these - it has the phoneme track, which is
    // strictly better information. This is only so the body has a signal of
    // its own instead of borrowing the mouth's.
    //
    // Note the bands are read at playback position, with no lead applied,
    // while the mouth is read `timeShift()` early. So the body naturally
    // trails the mouth by ~30-40 ms, which is the right way round: lips
    // anticipate a sound, torsos do not.
    this.useBands = opts.useBands ?? true;
    this.bands = new BandAnalyser(opts.bands || {});
    this.band = { low: 0, mid: 0, high: 0, hit: 0 };

    this.idleBlink = opts.idleBlink ?? true;
    this.blinkGap  = opts.blinkGap  ?? [2.2, 5.5];
    this._blinkT   = 0.8;
    this._blinkPhase = -1;

    // Channels pinned by hand. Applied last, after the track and the idle
    // blink, so a held value cannot be washed out by the per-frame reset.
    this.override = Object.create(null);

    // Bumped by every speak()/playTrack()/stop(). A line that has been
    // superseded checks this before touching anything: when lines are queued
    // back to back, the previous speak()'s completion (or its safety-net
    // timer, which fires seconds later) would otherwise reset the mouth to
    // idle in the middle of the line now playing.
    this._gen = 0;

    this.mode = 'idle';                      // 'idle' | 'track' | 'live'
    this._track = null;
    this._audio = null;
    this._getTime = null;
    this._ctx = null;
    this._analyser = null;
    this._buf = null;
    this._tracker = null;
    this._sourceNodes = new WeakMap();

    this._bind();
  }

  static async load(url, gltfLoader, opts = {}) {
    const gltf = await gltfLoader.loadAsync(url);
    return new TanukiLipSync(gltf.scene || gltf.scenes[0], opts);
  }

  /** The GLB has three primitives (face, mouth cavity, tongue), so three.js
   *  builds three meshes. Every one of them carries the same morph targets and
   *  all of them must be driven, or the mouth opens while the tongue stays put. */
  _bind() {
    this.object.traverse((o) => {
      const dict = o.morphTargetDictionary;
      if (!dict || !o.morphTargetInfluences) return;
      for (const name of ALL) {
        if (name in dict) {
          if (!this.byName.has(name)) this.byName.set(name, []);
          this.byName.get(name).push({ mesh: o, index: dict[name] });
        }
      }
    });
    if (this.byName.size === 0) {
      console.warn('[tanuki-lipsync] no morph targets found - is this the rigged GLB?');
    }
  }

  get morphNames() { return [...this.byName.keys()]; }

  /** Set a target directly (bypasses smoothing on the next update if immediate). */
  setViseme(name, value, immediate = false) {
    if (!(name in this.goal)) return;
    this.goal[name] = clamp01(value);
    if (immediate) this.current[name] = this.goal[name];
  }

  /**
   * Total seconds the track is shifted by. Positive samples the track later
   * (mouth lags), negative earlier (mouth leads).
   */
  timeShift() {
    const auto = this.autoLatency ? this.measuredLatency : 0;
    return auto + this.lead + this.offset;
  }

  /**
   * Measure this device's audio output latency.
   *
   * Creating a context is enough - nothing has to be routed through it. Called
   * automatically before a line plays, because the figure changes when the user
   * switches to Bluetooth mid-session.
   */
  async measureLatency(context = null) {
    try {
      const ctx = context || this._ctx ||
        new (window.AudioContext || window.webkitAudioContext)();
      this._ctx = ctx;
      await resumeBounded(ctx);
      const out = typeof ctx.outputLatency === 'number' ? ctx.outputLatency : 0;
      const base = typeof ctx.baseLatency === 'number' ? ctx.baseLatency : 0;
      // outputLatency is unimplemented on some engines and reports 0; fall back
      // to baseLatency, and to a small typical figure if neither is available,
      // rather than assuming zero latency which is never true.
      this.measuredLatency = out > 0 ? out : (base > 0 ? base + 0.02 : 0.04);
      return this.measuredLatency;
    } catch (_) {
      this.measuredLatency = 0.04;
      return this.measuredLatency;
    }
  }

  /** Pin a channel until released. `value = null` releases it. */
  setOverride(name, value) {
    if (value == null) delete this.override[name];
    else this.override[name] = value;
    return this;
  }

  setVisemes(obj, immediate = false) {
    for (const n of ALL) this.setViseme(n, obj[n] ?? 0, immediate);
  }

  _apply() {
    for (const [name, slots] of this.byName) {
      const v = this.current[name] ?? 0;
      for (const { mesh, index } of slots) mesh.morphTargetInfluences[index] = v;
    }
  }

  /** Call once per frame. dt in seconds. */
  update(dt) {
    dt = Math.min(dt || 0.016, 0.1);

    // Clear every channel first. Anything not re-driven below settles to zero.
    // Without this, `goal.Blink` is only ever written when a track carries a
    // Blink channel - so in idle mode the first blink raised it to 1.0 and,
    // because _tickBlink combines with Math.max, nothing could ever bring it
    // back down. The eyes shut on the first blink and stayed shut.
    for (const n of ALL) this.goal[n] = 0;

    if (this.mode === 'track' && this._track && (this._audio || this._getTime)) {
      const t = (this._getTime ? this._getTime() : this._audio.currentTime)
                + this.timeShift();
      const s = sampleTrack(this._track, t);
      for (const n of MOUTH) this.goal[n] = s[n] ?? 0;
      if (this._track.tracks.Blink) this.goal.Blink = s.Blink ?? 0;
      if (!this._getTime && this._audio && this._audio.ended) this._finish();
      // NOTE: deliberately not finishing on `paused`. speak() sets the mode
      // before play() has resolved, so a paused check here fires on the very
      // first frame and ends the line before it starts. Pausing should freeze
      // the mouth mid-shape, which falling through to the track sampler does.
    } else if (this.mode === 'live' && this._analyser) {
      this._analyser.getFloatTimeDomainData(this._buf);
      const r = this._tracker.push(this._buf, this._ctx.sampleRate);
      for (const n of MOUTH) this.goal[n] = r.viseme === n ? r.weight : 0;
      if (this._audio && this._audio.ended) this._finish();
    }

    if (this.idleBlink && !(this._track && this._track.tracks.Blink && this.mode === 'track')) {
      this._tickBlink(dt);
    }

    for (const n in this.override) {
      if (this.override[n] != null) this.goal[n] = clamp01(this.override[n]);
    }

    // Band energy, for the body. Real spectrum when there is an audio graph;
    // otherwise manufactured from mouth openness so the body does not change
    // character between the two paths.
    if (this.useBands) {
      this.band = this.bands.ready
        ? this.bands.update(dt)
        : this.bands.synth(dt, this.mode === 'idle' ? 0 : mouthOpenness(this.current));
    }

    for (const n of ALL) {
      const g = this.goal[n], c = this.current[n];
      const tau = g > c ? this.attack : this.release;
      // exponential approach, frame-rate independent
      this.current[n] = c + (g - c) * (1 - Math.exp(-dt / Math.max(tau, 1e-4)));
    }
    this._apply();
  }

  /** Fast down, short hold, slower opening. Symmetric timing reads as a twitch,
   *  and evenly spaced blinks are one of the clearest tells that something is
   *  animated rather than alive - hence the random gap. */
  _tickBlink(dt) {
    if (this._blinkPhase < 0) {
      this._blinkT -= dt;
      // Re-arm when the blink *starts*, not when it ends. Decrementing the
      // timer during the blink itself leaves it already negative on the frame
      // the blink finishes, which restarts it immediately and produces a
      // permanent flutter instead of an occasional blink.
      if (this._blinkT <= 0) { this._blinkPhase = 0; this._blinkT = rand(this.blinkGap[0], this.blinkGap[1]); }
    }
    if (this._blinkPhase >= 0) {
      this._blinkPhase += dt;
      const p = this._blinkPhase;
      const DOWN = 0.055, HOLD = 0.03, UP = 0.075;
      let v = 0;
      if (p < DOWN) v = p / DOWN;
      else if (p < DOWN + HOLD) v = 1;
      else if (p < DOWN + HOLD + UP) v = 1 - (p - DOWN - HOLD) / UP;
      else { this._blinkPhase = -1; }
      this.goal.Blink = Math.max(this.goal.Blink, clamp01(v));
      this.current.Blink = this.goal.Blink;    // blinks are too short to smooth
    }
  }

  /**
   * Drive the mouth from a track against a clock you control - your own audio
   * player, a <video>, a timeline scrubber, or a test harness. No audio is
   * played; you own playback.
   * @param {object} track  track JSON from lipsync.py
   * @param {() => number} getTime  current time in seconds
   */
  playTrack(track, getTime) {
    this._gen++;
    this._track = normaliseTrack(track);
    this._getTime = getTime;
    this._audio = null;
    this.mode = 'track';
    return this;
  }

  /**
   * Play a line.
   * @param {object} o
   * @param {HTMLAudioElement|string} o.audio  element or URL
   * @param {object} [o.track]  track JSON from lipsync.py; omit for live analysis
   * @param {AudioContext} [o.context]
   * @param {() => number} [o.getTime]  override the clock (defaults to
   *        audio.currentTime). Use it to drive the mouth from your own player,
   *        a video element, or a test harness.
   * @param {number} [o.startAt]  where in the clip to begin, seconds. Use it to
   *        skip an engine's leading silence; the track is in file time, so it
   *        follows the seek without any adjustment.
   * @returns {Promise<void>} resolves when the audio ends
   */
  async speak({ audio, track = null, context = null, getTime = null,
                startAt = 0 } = {}) {
    const gen = ++this._gen;
    const el = typeof audio === 'string' ? new Audio(audio) : audio;
    el.crossOrigin = el.crossOrigin || 'anonymous';
    this._audio = el;
    // Reusing one <audio> across lines leaves currentTime parked at the end of
    // the previous one, so the second speak() would sample the track past its
    // last key and never move the mouth. Assigning `startAt` rather than a
    // hard 0 lets a caller position the clip first - the queue skips each
    // engine's leading silence that way - without this line stamping over it.
    try { if (el.currentTime !== startAt) el.currentTime = startAt; } catch (_) {}

    if (track) {
      this._track = normaliseTrack(track);
      this.mode = 'track';
      this._getTime = getTime;
      // A pre-generated track knows about consonants; live analysis does not.
      // Both are driven off audio.currentTime, so a stalled buffer stalls the
      // mouth too instead of drifting out of sync.
    } else {
      // Live analysis genuinely cannot start without the graph.
      await this._startLive(el, context);
      this.mode = 'live';
    }

    // Do NOT wait for readyState here. Assigning currentTime above starts a
    // seek, and a seek drops readyState back below HAVE_CURRENT_DATA - but
    // `loadeddata` only ever fires once per resource, so waiting for it after
    // a seek waits for an event that can never arrive. play() is happy to be
    // called on an element that is still buffering; it starts when data lands.
    const started = el.play();

    // NOTHING above this line may wait on the AudioContext.
    //
    // Both of these need one, and neither is needed to make sound: the latency
    // figure only trims the mouth by a few tens of milliseconds, and the bands
    // only drive the body. They used to be awaited BEFORE play(), and
    // `ctx.resume()` does not reject when it is blocked - it simply never
    // settles - so a page that speaks before the user has clicked anything
    // would sit there silently with the mouth shut, for ever. Measured: the
    // first two lines of a queued reply never played at all.
    if (this.autoLatency) this.measureLatency(context).catch(() => {});
    if (track && this.useBands) this._graph(el, context).catch(() => {});

    await started;

    return new Promise((res) => {
      let settled = false;
      const cleanup = () => {
        clearTimeout(timer);
        el.removeEventListener('ended', finish);
        el.removeEventListener('error', finish);
      };
      const finish = () => {
        if (settled) return;
        settled = true;
        cleanup();
        // With an external clock the caller owns the lifecycle, so the audio
        // element ending must not silently reset the mouth to idle. Nor may a
        // superseded line reset the mouth under the one now playing.
        if (!getTime && gen === this._gen) this._finish();
        res();
      };
      el.addEventListener('ended', finish);
      el.addEventListener('error', finish);
      // Safety net. `ended` is not guaranteed: a stalled buffer, a decode
      // error, or a device with no audio output all leave it unfired, and then
      // this promise never settles - which in a chat UI means the send button
      // stays disabled forever. Cap it at the clip's own length plus a margin.
      const len = (el.duration && isFinite(el.duration))
        ? el.duration
        : (track && track.duration) || 10;
      const timer = setTimeout(finish, (len + 2) * 1000);
    });
  }

  /**
   * Route an <audio> element through the AudioContext and hang an analyser off
   * it. Used by BOTH paths now: live analysis needs it to find vowels, and the
   * track path needs it for band energy.
   *
   * Returns false instead of throwing. That matters: once
   * createMediaElementSource has been called on an element, that element's
   * sound only ever reaches the speakers through the context, so if the
   * context cannot be resumed the audio is silenced permanently. Hence the
   * running check before touching it - a page that fails to get a running
   * context loses the band signal, which is cosmetic, rather than the voice,
   * which is not.
   */
  async _graph(el, context) {
    try {
      this._ctx = context || this._ctx ||
        new (window.AudioContext || window.webkitAudioContext)();
      await resumeBounded(this._ctx);
      if (this._ctx.state !== 'running') return false;

      let src = this._sourceNodes.get(el);
      if (!src) {
        // createMediaElementSource can only ever be called once per element;
        // calling it twice throws, so the node is cached against the element.
        src = this._ctx.createMediaElementSource(el);
        this._sourceNodes.set(el, src);
        src.connect(this._ctx.destination);
      }
      if (!this._analyser) {
        this._analyser = this._ctx.createAnalyser();
        this._analyser.fftSize = 2048;
        this._buf = new Float32Array(this._analyser.fftSize);
      }
      src.connect(this._analyser);
      if (!this.bands.ready) this.bands.attach(this._analyser, this._ctx.sampleRate);
      return true;
    } catch (e) {
      console.warn('[tanuki-lipsync] no audio graph, bands disabled:', e.message);
      return false;
    }
  }

  async _startLive(el, context) {
    const ok = await this._graph(el, context);
    if (!ok) throw new Error('could not open an AudioContext for live analysis');
    this._tracker = new VowelTracker();
  }

  /** Drive from a live stream (microphone, or a streamed TTS MediaStream). */
  async listen(stream, context = null) {
    this._ctx = context || this._ctx || new (window.AudioContext || window.webkitAudioContext)();
    await resumeBounded(this._ctx);
    const src = this._ctx.createMediaStreamSource(stream);
    if (!this._analyser) {
      this._analyser = this._ctx.createAnalyser();
      this._analyser.fftSize = 2048;
      this._buf = new Float32Array(this._analyser.fftSize);
    }
    src.connect(this._analyser);
    if (!this.bands.ready) this.bands.attach(this._analyser, this._ctx.sampleRate);
    this._tracker = new VowelTracker();
    this._audio = null;
    this.mode = 'live';
  }

  stop() {
    this._gen++;
    if (this._audio && !this._audio.paused) this._audio.pause();
    this._finish();
  }

  _finish() {
    this.mode = 'idle';
    this._track = null;
    for (const n of MOUTH) this.goal[n] = 0;
  }
}

/* ------------------------------------------------------------------ */

function clamp01(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

/**
 * How open the mouth is right now, 0..1, from a channel map.
 * A and O open widest; I is a slit and must not read as a wide-open mouth.
 * Lives here rather than in body.js so the driver and the body agree.
 */
export function mouthOpenness(c) {
  if (!c) return 0;
  return Math.min(1, (c.A ?? 0) * 1.0 + (c.O ?? 0) * 0.8 +
                     (c.E ?? 0) * 0.5 + (c.U ?? 0) * 0.5 + (c.I ?? 0) * 0.25);
}
function rand(a, b) { return a + Math.random() * (b - a); }
function once(el, ev) { return new Promise((r) => el.addEventListener(ev, r, { once: true })); }

/** Resume an AudioContext without ever blocking on it.
 *  A context suspended by the autoplay policy returns a promise that stays
 *  pending until a user gesture arrives - which may be never. */
function resumeBounded(ctx, ms = 250) {
  if (!ctx || ctx.state !== 'suspended') return Promise.resolve();
  return Promise.race([
    ctx.resume().catch(() => {}),
    new Promise((r) => setTimeout(r, ms)),
  ]);
}

function normaliseTrack(t) {
  const out = { duration: t.duration ?? 0, tracks: {} };
  for (const [k, keys] of Object.entries(t.tracks || {})) {
    out.tracks[k] = keys.map((p) => (Array.isArray(p) ? p : [p.t, p.v])).sort((a, b) => a[0] - b[0]);
  }
  return out;
}

/** Linear interpolation of a sparse track at time t. */
export function sampleTrack(track, t) {
  const out = {};
  for (const [name, keys] of Object.entries(track.tracks)) {
    if (!keys.length) { out[name] = 0; continue; }
    if (t <= keys[0][0]) { out[name] = keys[0][1]; continue; }
    if (t >= keys[keys.length - 1][0]) { out[name] = keys[keys.length - 1][1]; continue; }
    let lo = 0, hi = keys.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; (keys[mid][0] <= t ? lo = mid : hi = mid); }
    const [t0, v0] = keys[lo], [t1, v1] = keys[hi];
    out[name] = t1 === t0 ? v1 : v0 + ((v1 - v0) * (t - t0)) / (t1 - t0);
  }
  return out;
}

export { VISEMES };
