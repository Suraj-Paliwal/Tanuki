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
 */
export class BodyMotion {
  /**
   * @param {THREE.Object3D} target  a group you control that contains the model
   */
  constructor(target, opts = {}) {
    this.target = target;
    this.t = 0;
    this.speech = 0;                 // smoothed mouth openness, 0..1

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
    this.nodAmount   = opts.nodAmount   ?? 0.030;
    this.leanAmount  = opts.leanAmount  ?? 0.012;
    this.bobAmount   = opts.bobAmount   ?? 0.005;
    this.speechSmooth = opts.speechSmooth ?? 0.10;  // seconds

    this.enabled = opts.enabled ?? true;
    this._base = {
      px: target.position.x, py: target.position.y, pz: target.position.z,
      rx: target.rotation.x, ry: target.rotation.y, rz: target.rotation.z,
    };
  }

  /** How open the mouth is right now, 0..1. */
  static openness(rig) {
    if (!rig || !rig.current) return 0;
    const c = rig.current;
    // A and O open widest; I is a slit and should not drive a big nod
    return Math.min(1, (c.A ?? 0) * 1.0 + (c.O ?? 0) * 0.8 +
                       (c.E ?? 0) * 0.5 + (c.U ?? 0) * 0.5 + (c.I ?? 0) * 0.25);
  }

  update(dt, rig) {
    if (!this.enabled) return;
    dt = Math.min(dt || 0.016, 0.1);
    this.t += dt;

    const target = BodyMotion.openness(rig);
    // Smooth, or the body twitches on every consonant instead of riding the
    // phrase. The mouth wants to be fast; the body wants to lag behind it.
    const k = 1 - Math.exp(-dt / Math.max(this.speechSmooth, 1e-4));
    this.speech += (target - this.speech) * k;

    const T = 2 * Math.PI * this.t;
    const breath = Math.sin(T * this.breathRate);
    const sway   = Math.sin(T * this.swayRate);
    const turn   = Math.sin(T * this.turnRate + 1.3);
    const s      = this.speech;

    const o = this.target, b = this._base;
    o.position.y = b.py + breath * this.breathRise + s * this.bobAmount * Math.sin(T * 1.9);
    o.position.x = b.px + sway * this.swayAmount * 0.35;
    o.rotation.x = b.rx + breath * this.breathTilt * 0.5
                        - s * this.leanAmount
                        + s * this.nodAmount * Math.sin(T * 1.55);
    o.rotation.y = b.ry + turn * this.turnAmount * (1 - 0.5 * s);
    o.rotation.z = b.rz + sway * this.swayAmount;
  }

  reset() {
    const o = this.target, b = this._base;
    o.position.set(b.px, b.py, b.pz);
    o.rotation.set(b.rx, b.ry, b.rz);
    this.speech = 0;
  }
}

export default BodyMotion;
