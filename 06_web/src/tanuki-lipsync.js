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

    this.idleBlink = opts.idleBlink ?? true;
    this.blinkGap  = opts.blinkGap  ?? [2.2, 5.5];
    this._blinkT   = 0.8;
    this._blinkPhase = -1;

    // Channels pinned by hand. Applied last, after the track and the idle
    // blink, so a held value cannot be washed out by the per-frame reset.
    this.override = Object.create(null);

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
      if (ctx.state === 'suspended') await ctx.resume();
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
   * @returns {Promise<void>} resolves when the audio ends
   */
  async speak({ audio, track = null, context = null, getTime = null } = {}) {
    const el = typeof audio === 'string' ? new Audio(audio) : audio;
    el.crossOrigin = el.crossOrigin || 'anonymous';
    this._audio = el;
    // Reusing one <audio> across lines leaves currentTime parked at the end of
    // the previous one, so the second speak() would sample the track past its
    // last key and never move the mouth.
    try { el.currentTime = 0; } catch (_) {}

    if (this.autoLatency) await this.measureLatency(context);

    if (track) {
      this._track = normaliseTrack(track);
      this.mode = 'track';
      this._getTime = getTime;
      // A pre-generated track knows about consonants; live analysis does not.
      // Both are driven off audio.currentTime, so a stalled buffer stalls the
      // mouth too instead of drifting out of sync.
    } else {
      await this._startLive(el, context);
      this.mode = 'live';
    }

    if (el.readyState < 2) await once(el, 'loadeddata');
    await el.play();
    return new Promise((res) => {
      const done = () => {
        el.removeEventListener('ended', done);
        // With an external clock the caller owns the lifecycle, so the audio
        // element ending must not silently reset the mouth to idle.
        if (!getTime) this._finish();
        res();
      };
      el.addEventListener('ended', done);
    });
  }

  async _startLive(el, context) {
    this._ctx = context || this._ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (this._ctx.state === 'suspended') await this._ctx.resume();
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
    this._tracker = new VowelTracker();
  }

  /** Drive from a live stream (microphone, or a streamed TTS MediaStream). */
  async listen(stream, context = null) {
    this._ctx = context || this._ctx || new (window.AudioContext || window.webkitAudioContext)();
    if (this._ctx.state === 'suspended') await this._ctx.resume();
    const src = this._ctx.createMediaStreamSource(stream);
    if (!this._analyser) {
      this._analyser = this._ctx.createAnalyser();
      this._analyser.fftSize = 2048;
      this._buf = new Float32Array(this._analyser.fftSize);
    }
    src.connect(this._analyser);
    this._tracker = new VowelTracker();
    this._audio = null;
    this.mode = 'live';
  }

  stop() {
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
function rand(a, b) { return a + Math.random() * (b - a); }
function once(el, ev) { return new Promise((r) => el.addEventListener(ev, r, { once: true })); }

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
