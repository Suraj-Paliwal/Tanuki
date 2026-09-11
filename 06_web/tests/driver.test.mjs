import test from 'node:test';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';

const moduleURL = process.env.TANUKI_DRIVER
  ? pathToFileURL(process.env.TANUKI_DRIVER).href
  : new URL('../src/tanuki-lipsync.js', import.meta.url).href;
const { TanukiLipSync } = await import(moduleURL);
const vowels = ['A', 'I', 'U', 'E', 'O'];
function fixture(opts = {}) {
  const meshes = [0, 1, 2].map(() => ({
    morphTargetDictionary: Object.fromEntries([...vowels, 'Blink'].map((v, i) => [v, i])),
    morphTargetInfluences: Array(6).fill(0),
  }));
  const rig = new TanukiLipSync({ traverse: fn => meshes.forEach(fn) }, {
    idleBlink: false, useBands: false, autoLatency: false, lead: 0, ...opts,
  });
  return { rig, meshes };
}
const total = rig => vowels.reduce((sum, v) => sum + rig.current[v], 0);

test('all vowel transitions stay within the authored mouth shapes at 30, 60 and 120 fps', () => {
  let max = 0;
  for (const fps of [30, 60, 120]) for (const from of vowels) for (const to of vowels) {
    const { rig } = fixture();
    rig.current[from] = 1;
    rig.setOverride(to, 1);
    for (let frame = 0; frame < fps / 2; frame++) {
      rig.update(1 / fps);
      max = Math.max(max, total(rig));
    }
  }
  console.log('Maximum combined vowel weight:', max.toFixed(4));
  assert.ok(max <= 1.000001, `mouth shape overshoot ${max}`);
});

test('a held U becomes distinct from preceding A within 80 ms', () => {
  const { rig } = fixture();
  rig.current.A = 1;
  rig.setOverride('U', 1);
  for (let i = 0; i < 10; i++) rig.update(0.008);
  assert.ok(rig.current.U > 0.95);
  assert.ok(rig.current.A < 0.05, `previous A still at ${rig.current.A}`);
});

test('a closure clears at least 90 percent of the old vowel in 60 ms', () => {
  const { rig } = fixture();
  rig.current.A = 1;
  for (let i = 0; i < 6; i++) rig.update(0.01);
  assert.ok(total(rig) < 0.1, `mouth remains ${total(rig)} open during closure`);
});

test('face, mouth cavity, and tongue receive identical weights; blink is separate', () => {
  const { rig, meshes } = fixture();
  rig.setOverride('O', 1);
  rig.setOverride('Blink', 1);
  for (let i = 0; i < 20; i++) rig.update(0.016);
  assert.deepEqual(meshes[0].morphTargetInfluences, meshes[1].morphTargetInfluences);
  assert.deepEqual(meshes[1].morphTargetInfluences, meshes[2].morphTargetInfluences);
  assert.ok(rig.current.O > 0.99 && rig.current.Blink > 0.99);
});

test('audio output delay moves the sampled mouth back toward the audible sound', () => {
  const { rig } = fixture({ autoLatency: true, lead: 0.03 });
  rig.measuredLatency = 0.15;
  assert.ok(Math.abs(rig.timeShift() - (-0.12)) < 1e-9);
});

test('a caller can disable automatic audio latency and retain a manual trim', () => {
  const { rig } = fixture({ autoLatency: false, lead: 0.03, offset: -0.01 });
  rig.measuredLatency = 0.15;
  assert.ok(Math.abs(rig.timeShift() - 0.02) < 1e-9);
});

test('default playback does not apply an unrelated audio-context delay', () => {
  const rig = new TanukiLipSync({ traverse() {} }, { idleBlink: false, useBands: false });
  rig.measuredLatency = 0.15;
  assert.equal(rig.autoLatency, false);
  assert.ok(Math.abs(rig.timeShift() - rig.lead) < 1e-9);
});

test('overlapping external targets cannot exceed the model blend budget', () => {
  const { rig } = fixture();
  rig.setOverride('A', 1);
  rig.setOverride('U', 1);
  for (let i = 0; i < 30; i++) rig.update(0.016);
  assert.ok(total(rig) <= 1.000001);
  assert.ok(Math.abs(rig.current.A - rig.current.U) < 1e-9);
});
