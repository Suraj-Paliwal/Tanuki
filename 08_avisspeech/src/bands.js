/**
 * Three-band audio energy, for driving the body rather than the mouth.
 *
 * WHY THIS EXISTS
 * ---------------
 * Before this, the body was driven by one number: how open the mouth was.
 * That number is a good mouth signal and a bad body signal, because it is a
 * function of which vowel is being said. The tanuki leaned forward on あ and
 * went still on い - not because the sentence had a shape, but because /i/ is
 * a narrow vowel. Bodies do not work that way.
 *
 * Speech energy is not one signal, it is roughly three, and they belong to
 * different parts of the body:
 *
 *   low   70-260 Hz    the voiced fundamental. Present whenever the vocal
 *                      folds are working, absent in whispers and pauses.
 *                      This is the "am I producing voice" signal, and it is
 *                      what the torso and the breath should follow.
 *
 *   mid   260-2200 Hz  where F1 and F2 live, so this is where vowel identity
 *                      and the loudness you actually perceive both sit. This
 *                      is the phrase-level intensity: the lean and the bob.
 *
 *   high  2600-7000 Hz frication and plosive bursts - the /s/ in です, the
 *                      release of /t/ and /k/. These are events, not levels,
 *                      so what gets used downstream is the RISE of this band,
 *                      not its value. A rise is a consonant landing, and a
 *                      consonant landing is where a real speaker's head ticks.
 *
 * NORMALISATION
 * -------------
 * A fixed dB range does not survive contact with real audio: a VOICEVOX clip,
 * an edge-tts clip and a phone microphone sit at completely different levels,
 * and a fixed range means the body either never moves or is pinned at full
 * tilt. So each band carries a running peak that rises instantly and decays
 * slowly, and the band is reported as its position between a noise floor and
 * that peak. The effect is an automatic gain control with a few seconds of
 * memory: loud passages still read louder than quiet ones inside a sentence,
 * but the overall level of the recording stops mattering.
 */

const B = {
  low:  [70, 260],
  mid:  [260, 2200],
  high: [2600, 7000],
};

export class BandAnalyser {
  constructor(opts = {}) {
    this.floorDb = opts.floorDb ?? -68;   // below this, treat as silence
    this.minRange = opts.minRange ?? 12;  // dB; stops AGC exploding in silence
    this.peakDecay = opts.peakDecay ?? 6; // dB per second the running peak falls

    // Time constants, in seconds. Heavier things smooth longer - this is the
    // whole reason for splitting the bands, so do not level these out.
    this.tau = { low: 0.18, mid: 0.09, high: 0.030, ...(opts.tau || {}) };
    this.hitRelease = opts.hitRelease ?? 0.16;
    this.hitGain = opts.hitGain ?? 3.2;

    this.node = null;
    this.freq = null;
    this.sampleRate = 48000;
    this.ranges = null;

    this.value = { low: 0, mid: 0, high: 0 };
    this.hit = 0;
    this._peak = { low: -Infinity, mid: -Infinity, high: -Infinity };
    this._prevHigh = 0;
  }

  get ready() { return !!this.node; }

  /**
   * @param {AnalyserNode} node
   * @param {number} sampleRate
   */
  attach(node, sampleRate) {
    this.node = node;
    this.sampleRate = sampleRate || 48000;
    this.freq = new Float32Array(node.frequencyBinCount);
    // A little of the analyser's own smoothing keeps the spectrum from
    // flickering between frames; the rest of the smoothing is ours, below,
    // because ours is frame-rate independent and per-band.
    node.smoothingTimeConstant = 0.30;
    this._binRanges();
    return this;
  }

  detach() { this.node = null; this.freq = null; this.ranges = null; }

  /** Bin index range for each band. Bin k covers k * (sr/2) / bins Hz. */
  _binRanges() {
    const bins = this.freq.length;
    const nyquist = this.sampleRate / 2;
    const idx = (hz) => Math.max(0, Math.min(bins - 1, Math.round((hz / nyquist) * bins)));
    this.ranges = {};
    for (const [name, [lo, hi]] of Object.entries(B)) {
      const a = idx(lo), b = Math.max(a + 1, idx(hi));
      this.ranges[name] = [a, b];
    }
  }

  /** Mean power across a bin range, back in dB. */
  _bandDb(a, b) {
    const f = this.freq;
    let p = 0;
    for (let i = a; i < b; i++) {
      const db = f[i];
      // getFloatFrequencyData returns -Infinity for empty bins
      if (db > -200) p += Math.pow(10, db / 10);
    }
    const mean = p / (b - a);
    return mean > 0 ? 10 * Math.log10(mean) : -Infinity;
  }

  /**
   * Read the spectrum and advance the smoothers.
   * @returns {{low:number, mid:number, high:number, hit:number}} all 0..1
   */
  update(dt) {
    if (!this.node) return this.value;
    dt = Math.min(dt || 0.016, 0.1);
    this.node.getFloatFrequencyData(this.freq);

    for (const name of ['low', 'mid', 'high']) {
      const [a, b] = this.ranges[name];
      const db = this._bandDb(a, b);

      // running peak: instant attack, slow decay, never below floor + range
      let pk = this._peak[name];
      if (!isFinite(pk)) pk = this.floorDb + this.minRange;
      pk = Math.max(db, pk - this.peakDecay * dt, this.floorDb + this.minRange);
      this._peak[name] = pk;

      const span = Math.max(pk - this.floorDb, this.minRange);
      const norm = isFinite(db) ? clamp01((db - this.floorDb) / span) : 0;

      const k = 1 - Math.exp(-dt / Math.max(this.tau[name], 1e-4));
      this.value[name] += (norm - this.value[name]) * k;
    }

    // Consonants are events. Half-wave rectify the rise of the high band and
    // let it decay - a level would make the head lean during every /s/ and
    // stay there; an impulse makes it tick once, which is what a head does.
    const rise = Math.max(0, this.value.high - this._prevHigh) / Math.max(dt, 1e-4);
    this._prevHigh = this.value.high;
    const impulse = clamp01(rise * this.hitGain * 0.02);
    this.hit = Math.max(impulse, this.hit * Math.exp(-dt / this.hitRelease));

    return { ...this.value, hit: this.hit };
  }

  /**
   * Fallback when there is no audio graph at all - an external clock, a track
   * played against someone else's player, or a browser that refused the
   * context. Manufactures plausible bands from mouth openness alone:
   * openness stands in for mid, a laggier copy for low, and its own rise for
   * the consonant hits. Not as good as the real spectrum, but it keeps the
   * body behaving the same way instead of switching character.
   */
  synth(dt, openness) {
    dt = Math.min(dt || 0.016, 0.1);
    const o = clamp01(openness);
    for (const [name, target] of [['low', o * 0.9], ['mid', o], ['high', o * 0.5]]) {
      const k = 1 - Math.exp(-dt / Math.max(this.tau[name], 1e-4));
      this.value[name] += (target - this.value[name]) * k;
    }
    const rise = Math.max(0, this.value.high - this._prevHigh) / Math.max(dt, 1e-4);
    this._prevHigh = this.value.high;
    this.hit = Math.max(clamp01(rise * this.hitGain * 0.02), this.hit * Math.exp(-dt / this.hitRelease));
    return { ...this.value, hit: this.hit };
  }

  reset() {
    this.value = { low: 0, mid: 0, high: 0 };
    this.hit = 0;
    this._prevHigh = 0;
    this._peak = { low: -Infinity, mid: -Infinity, high: -Infinity };
  }
}

function clamp01(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

export { B as BAND_HZ };
export default BandAnalyser;
