/**
 * Browser-side vowel detection for Japanese speech.
 *
 * The five Japanese vowels sit far apart in formant space, so estimating F1/F2
 * per frame and picking the nearest is enough - no model, no aligner.
 *
 * Formants come from the LPC spectral envelope rather than from polynomial
 * roots: evaluating |1/A(w)| on a frequency grid and peak-picking is stable and
 * cheap, where root-finding a degree-20 polynomial 60 times a second is not.
 */

export const VISEMES = ['A', 'I', 'U', 'E', 'O'];

// reference F1/F2 for the five Japanese vowels, adult male, Hz
const REF = [[750, 1200], [300, 2300], [350, 1300], [500, 1900], [500, 900]];
const LREF = REF.map(([a, b]) => [Math.log(a), Math.log(b)]);

// F2 separates i / e / u, which is most of the work. F1 mostly reports how
// open the mouth is, and that already feeds the weight.
const F2_WEIGHT = 1.4;

/** Decimate to ~16 kHz. LPC order scales with sample rate, and at 48 kHz the
 *  order needed to resolve formants is high enough to be both slow and
 *  numerically fragile. */
export function decimateTo16k(buf, sampleRate) {
  const factor = Math.max(1, Math.round(sampleRate / 16000));
  if (factor === 1) return { data: buf, sr: sampleRate };
  const out = new Float32Array(Math.floor(buf.length / factor));
  for (let i = 0; i < out.length; i++) {
    let s = 0;
    for (let k = 0; k < factor; k++) s += buf[i * factor + k] || 0;
    out[i] = s / factor;                       // box filter, doubles as anti-alias
  }
  return { data: out, sr: sampleRate / factor };
}

function levinson(r, order) {
  const a = new Float64Array(order + 1);
  a[0] = 1;
  let e = r[0];
  if (e <= 0) return a;
  for (let i = 1; i <= order; i++) {
    let acc = r[i];
    for (let j = 1; j < i; j++) acc += a[j] * r[i - j];
    const k = -acc / e;
    const prev = a.slice(0, i);
    for (let j = 1; j <= i; j++) a[j] = prev[j] !== undefined ? prev[j] + k * prev[i - j] : k * prev[i - j];
    a[i] = k;
    e *= 1 - k * k;
    if (e <= 0) break;
  }
  return a;
}

/** First two formants, or null if the frame has no usable resonances. */
export function formants(frame, sr) {
  const n = frame.length;
  if (n < 128) return null;
  // pre-emphasis + Hamming
  const x = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    const pre = frame[i] - 0.97 * (i > 0 ? frame[i - 1] : 0);
    x[i] = pre * (0.54 - 0.46 * Math.cos((2 * Math.PI * i) / (n - 1)));
  }
  const order = Math.min(24, Math.max(10, Math.round(sr / 1000) + 4));
  const r = new Float64Array(order + 1);
  for (let k = 0; k <= order; k++) {
    let s = 0;
    for (let i = 0; i < n - k; i++) s += x[i] * x[i + k];
    r[k] = s;
  }
  if (r[0] < 1e-9) return null;
  const a = levinson(r, order);

  // sample the LPC envelope and take the first two peaks
  const LO = 120, HI = 4200, STEP = 12;
  const bins = Math.floor((HI - LO) / STEP) + 1;
  const mag = new Float64Array(bins);
  for (let b = 0; b < bins; b++) {
    const w = (2 * Math.PI * (LO + b * STEP)) / sr;
    let re = 0, im = 0;
    for (let k = 0; k <= order; k++) { re += a[k] * Math.cos(w * k); im -= a[k] * Math.sin(w * k); }
    mag[b] = 1 / Math.sqrt(re * re + im * im + 1e-18);
  }
  const peaks = [];
  for (let b = 1; b < bins - 1; b++) {
    if (mag[b] > mag[b - 1] && mag[b] >= mag[b + 1]) {
      // parabolic refinement, so a 12 Hz grid still gives usable precision
      const d = (0.5 * (mag[b - 1] - mag[b + 1])) / (mag[b - 1] - 2 * mag[b] + mag[b + 1] || 1e-9);
      peaks.push(LO + (b + d) * STEP);
      if (peaks.length >= 4) break;
    }
  }
  if (peaks.length < 2) return null;
  return [peaks[0], peaks[1]];
}

/** Running vowel classifier with light speaker adaptation. */
export class VowelTracker {
  constructor({ speakerAdapt = 0.35, floorDb = -38 } = {}) {
    this.speakerAdapt = speakerAdapt;
    this.floorDb = floorDb;
    this.hist = [];
    this.peakRms = 1e-6;
  }
  /** @returns {{viseme:string|null, weight:number}} */
  push(frame, sampleRate) {
    let sum = 0;
    for (let i = 0; i < frame.length; i++) sum += frame[i] * frame[i];
    const rms = Math.sqrt(sum / frame.length) + 1e-12;
    this.peakRms = Math.max(this.peakRms * 0.9995, rms);
    const db = 20 * Math.log10(rms / this.peakRms);
    if (db < this.floorDb) return { viseme: null, weight: 0 };

    const { data, sr } = decimateTo16k(frame, sampleRate);
    const f = formants(data, sr);
    if (!f) return { viseme: null, weight: 0 };

    this.hist.push(f);
    if (this.hist.length > 240) this.hist.shift();

    // Adapt to the speaker, but only partly: dividing by the utterance median
    // tracks a high or low voice, yet the median depends on which vowels happen
    // to occur, so a phrase heavy in /a/ drags every other vowel out of place.
    let s1 = 1, s2 = 1;
    if (this.hist.length > 25) {
      const m1 = median(this.hist.map((v) => v[0])) / 500;
      const m2 = median(this.hist.map((v) => v[1])) / 1300;
      s1 = Math.pow(Math.max(m1, 0.2), this.speakerAdapt);
      s2 = Math.pow(Math.max(m2, 0.2), this.speakerAdapt);
    }
    const l1 = Math.log(Math.max(f[0] / s1, 1)), l2 = Math.log(Math.max(f[1] / s2, 1));
    let best = 0, bestD = Infinity;
    for (let i = 0; i < LREF.length; i++) {
      const d1 = LREF[i][0] - l1, d2 = (LREF[i][1] - l2) * F2_WEIGHT;
      const d = Math.sqrt(d1 * d1 + d2 * d2);
      if (d < bestD) { bestD = d; best = i; }
    }
    const conf = Math.min(1, Math.max(0.2, 1 - bestD / 1.1));
    const loud = Math.min(1, Math.max(0, (db - this.floorDb) / 22));
    return { viseme: VISEMES[best], weight: loud * conf };
  }
}

function median(arr) {
  const a = Float64Array.from(arr).sort();
  const m = a.length >> 1;
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2;
}
