/**
 * Idle and speaking body motion.
 *
 * The model is a single skinless mesh - no bones, no spine - so the only thing
 * that can move is the whole object's transform. That turns out to be enough:
 * for a stylised character, a slow breath, a little weight shift and a nod on
 * the stressed syllables is most of what reads as "alive". A perfectly still
 * body under a moving mouth is what makes an avatar look like a puppet.
 *
 * Applied to a wrapper you own, never to the loaded scene directly, so your own
 * placement of the character is never fought over.
 *
 *   const body = new BodyMotion(wrapperGroup);
 *   body.update(dt, tanuki);          // in the render loop, after tanuki.update
 *
 * WHAT DRIVES IT
 * --------------
 * Two modes, chosen automatically.
 *
 *   band drive (default, whenever the rig has an audio graph)
 *     Three separate signals from src/bands.js:
 *       low  -> the torso. Voicing energy, so the chest engages while sound is
 *               being produced and settles in the gaps between phrases.
 *       mid  -> the lean and the bob. Perceived loudness, so the body commits
 *               more on an emphatic phrase than a muttered one.
 *       hit  -> head accents. The RISE of the high band, which is a consonant
 *               landing. This is the part worth having: nods now fall on the
 *               plosives instead of on a fixed 1.55 Hz sine, so they line up
 *               with the sentence rather than drifting across it.
 *
 *   openness drive (fallback)
 *     One number - how open the mouth is - as before. Correct but blunt: it
 *     makes the body a function of which vowel is being said, so the character
 *     leans on あ and freezes on い. Kept because an external clock, a refused
 *     AudioContext or a muted tab all leave no spectrum to read.
 */
import { mouthOpenness } from './tanuki-lipsync.js';

export class BodyMotion {
  /**
   * @param {THREE.Object3D} target  a group you control that contains the model
   */
  constructor(target, opts = {}) {
    this.target = target;
    this.t = 0;
    this.speech = 0;                 // smoothed drive level, 0..1
    this.voice  = 0;                 // smoothed low-band (torso engagement)
    this.accent = 0;                 // decaying consonant impulse

    // breathing
    this.breathRate  = opts.breathRate  ?? 0.23;   // Hz, slow
    this.breathRise  = opts.breathRise  ?? 0.006;  // world units
    this.breathTilt  = opts.breathTilt  ?? 0.010;  // radians

    // idle drift: two sines at unrelated rates, so it never visibly repeats
    this.swayAmount  = opts.swayAmount  ?? 0.016;
    this.swayRate    = opts.swayRate    ?? 0.11;
    this.turnAmount  = opts.turnAmount  ?? 0.045;
    this.turnRate    = opts.turnRate    ?? 0.071;

    // speaking
    this.nodAmount    = opts.nodAmount    ?? 0.030;
    this.leanAmount   = opts.leanAmount   ?? 0.012;
    this.bobAmount    = opts.bobAmount    ?? 0.005;
    this.speechSmooth = opts.speechSmooth ?? 0.10;  // seconds

    // band drive
    this.bandDrive   = opts.bandDrive   ?? true;
    this.accentNod   = opts.accentNod   ?? 0.020;   // radians at full impulse
    this.accentDip   = opts.accentDip   ?? 0.0025;  // world units
    this.accentDecay = opts.accentDecay ?? 0.20;    // seconds
    this.torsoRise   = opts.torsoRise   ?? 0.004;
    // Residual sine, kept small. With band drive the accents carry the rhythm,
    // but a long vowel produces no consonant hits at all, and a body that goes
    // completely rigid through おおきい looks worse than one that keeps a
    // little idle motion under it.
    this.residualNod = opts.residualNod ?? 0.30;

    this.usingBands = false;         // read this to see which mode is live
    this.enabled = opts.enabled ?? true;
    this._base = {
      px: target.position.x, py: target.position.y, pz: target.position.z,
      rx: target.rotation.x, ry: target.rotation.y, rz: target.rotation.z,
    };
  }

  /** How open the mouth is right now, 0..1. */
  static openness(rig) {
    return rig && rig.current ? mouthOpenness(rig.current) : 0;
  }

  update(dt, rig) {
    if (!this.enabled) return;
    dt = Math.min(dt || 0.016, 0.1);
    this.t += dt;

    const band = this.bandDrive && rig && rig.useBands ? rig.band : null;
    this.usingBands = !!band;

    let target, voiceTarget, hit;
    if (band) {
      target      = band.mid;
      voiceTarget = band.low;
      hit         = band.hit;
    } else {
      target = voiceTarget = BodyMotion.openness(rig);
      hit = 0;
    }

    // Smooth, or the body twitches on every consonant instead of riding the
    // phrase. The mouth wants to be fast; the body wants to lag behind it.
    // (bands.js has already smoothed these once with its own per-band time
    // constants; this second pass is what gives the body its extra weight.)
    const k = 1 - Math.exp(-dt / Math.max(this.speechSmooth, 1e-4));
    this.speech += (target - this.speech) * k;
    this.voice  += (voiceTarget - this.voice) * (1 - Math.exp(-dt / 0.22));

    // Accents are impulses that decay, not a level to sit at.
    this.accent = Math.max(hit, this.accent * Math.exp(-dt / Math.max(this.accentDecay, 1e-4)));

    const T = 2 * Math.PI * this.t;
    const breath = Math.sin(T * this.breathRate);
    const sway   = Math.sin(T * this.swayRate);
    const turn   = Math.sin(T * this.turnRate + 1.3);
    const s      = this.speech;
    const v      = this.voice;
    const a      = this.accent;

    // You breathe shallower while you are talking. Small, but it is the
    // difference between a character that is speaking and one that happens to
    // be breathing and moving its mouth at the same time.
    const breathDepth = 1 - 0.5 * v;
    // With band drive the sine nod steps aside for the accents; without it,
    // the sine is all there is, so it stays at full strength.
    const sineNod = band ? this.residualNod : 1;

    const o = this.target, b = this._base;
    o.position.y = b.py + breath * this.breathRise * breathDepth
                        + v * this.torsoRise
                        + s * this.bobAmount * Math.sin(T * 1.9)
                        - a * this.accentDip;
    o.position.x = b.px + sway * this.swayAmount * 0.35;
    o.rotation.x = b.rx + breath * this.breathTilt * 0.5 * breathDepth
                        - s * this.leanAmount
                        + s * this.nodAmount * sineNod * Math.sin(T * 1.55)
                        - a * this.accentNod;
    o.rotation.y = b.ry + turn * this.turnAmount * (1 - 0.5 * s);
    o.rotation.z = b.rz + sway * this.swayAmount + a * this.accentNod * 0.15;
  }

  reset() {
    const o = this.target, b = this._base;
    o.position.set(b.px, b.py, b.pz);
    o.rotation.set(b.rx, b.ry, b.rz);
    this.speech = 0;
    this.voice = 0;
    this.accent = 0;
  }
}

export default BodyMotion;
