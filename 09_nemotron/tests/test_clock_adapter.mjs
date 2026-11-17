/**
 * Tests for src/clock-adapter.js. Node's built-in test runner, no DOM, no
 * three.js, no browser:
 *
 *     node --test tests/
 *
 * The clock is injected, so every case is deterministic. What these cover is
 * the behaviour the goal makes protocol-critical for an externally clocked
 * mouth: that it stops on every ending (because nothing else will), that a
 * silent controller is a fault rather than a frozen open mouth, and that the
 * position it reports is file time.
 *
 * What they do not cover: the real renderer, the real transport, and anything
 * visual. Those are recorded as NOT_RUN in validation/avatar_clock.md.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  PlaybackClockAdapter, endedReasonToStop,
  STOP_CLIP_END, STOP_STALE, STOP_FAULT, STOP_DISCONNECTED, STOP_REQUESTED,
} from '../src/clock-adapter.js';

/** A controllable clock, in milliseconds. */
function clock(start = 1000) {
  let t = start;
  return { now: () => t, advance: (ms) => { t += ms; return t; } };
}

/** A snapshot shaped like timing.PlaybackPosition.as_record(). */
function snap({ file_time = 0, rate = 1, playing = true, duration = 2,
                generation = 1, controller_time = 500, pre_roll_s = 0,
                ended_reason = null } = {}) {
  return { file_time, controller_time, rate, playing, duration, generation,
           method: 'estimated', pre_roll_s, ended_reason };
}

function harness(opts = {}) {
  const c = clock();
  const stops = [];
  const faults = [];
  const adapter = new PlaybackClockAdapter({
    now: c.now,
    onStop: (reason, detail) => stops.push({ reason, detail }),
    onFault: (f) => faults.push(f),
    ...opts,
  });
  return { adapter, c, stops, faults };
}

test('position advances between snapshots at the clip rate', () => {
  const { adapter, c } = harness();
  adapter.accept(snap({ file_time: 0.5 }));
  assert.equal(adapter.fileTime(), 0.5);
  c.advance(100);
  assert.ok(Math.abs(adapter.fileTime() - 0.6) < 1e-9);
});

test('position is file time, so it includes the clip leading silence', () => {
  // The controller reports 0.3 s into a file whose sound starts at 0.25 s.
  // The mouth track is indexed in file time, so 0.3 is the right answer and
  // the adapter must not subtract anything.
  const { adapter } = harness();
  adapter.accept(snap({ file_time: 0.3, duration: 1.0 }));
  assert.equal(adapter.fileTime(), 0.3);
});

test('a stale clock stops the mouth instead of extrapolating forever', () => {
  // An external-clock track has no end event of its own, so a controller that
  // goes quiet would otherwise hold the mouth open indefinitely.
  const { adapter, c, stops, faults } = harness({ staleAfterMs: 250 });
  adapter.accept(snap({ file_time: 0.1, duration: 10 }));
  c.advance(200);
  assert.ok(adapter.fileTime() > 0.1);
  assert.equal(stops.length, 0);
  c.advance(100);                       // now 300 ms since arrival
  adapter.fileTime();
  assert.equal(stops.length, 1);
  assert.equal(stops[0].reason, STOP_STALE);
  assert.equal(faults.at(-1).kind, 'stale_clock');
  assert.ok(adapter.isStale());
});

test('a stale clock holds its last position rather than jumping', () => {
  const { adapter, c } = harness({ staleAfterMs: 250 });
  adapter.accept(snap({ file_time: 0.1, duration: 10 }));
  c.advance(200);
  const last = adapter.fileTime();
  c.advance(5000);
  assert.equal(adapter.fileTime(), last);
});

test('clip end stops the mouth and is distinguished from an operator stop', () => {
  // An idle snapshot carries no clip - file_time and duration are both zero
  // whatever happened - so the reason comes from the controller, not from
  // comparing the two.
  const { adapter, stops } = harness();
  adapter.accept(snap({ file_time: 0.5, duration: 2 }));
  adapter.accept(snap({ file_time: 0, duration: 0, playing: false, rate: 0,
                        ended_reason: 'clip_end' }));
  assert.equal(stops.length, 1);
  assert.equal(stops[0].reason, STOP_CLIP_END);
});

test('a stop partway through the clip is not reported as clip end', () => {
  const { adapter, stops } = harness();
  adapter.accept(snap({ file_time: 0.5, duration: 2 }));
  adapter.accept(snap({ file_time: 0, duration: 0, playing: false, rate: 0,
                        ended_reason: 'participant_stop' }));
  assert.equal(stops[0].reason, STOP_REQUESTED);
});

test('a controller fault reason is not reported as a completed clip', () => {
  const { adapter, stops } = harness();
  adapter.accept(snap({ file_time: 0.5, duration: 2 }));
  adapter.accept(snap({ file_time: 0, duration: 0, playing: false, rate: 0,
                        ended_reason: 'audio_fault' }));
  assert.equal(stops[0].reason, STOP_FAULT);
});

test('an absent ended_reason does not claim the clip completed', () => {
  // Conservative fallback: an older or truncated snapshot must not be read as
  // a finished clip, because "it finished" is the one reading that could be
  // mistaken for the participant having heard the whole prompt.
  const { adapter, stops } = harness();
  adapter.accept(snap({ file_time: 0.5, duration: 2 }));
  adapter.accept(snap({ file_time: 0, duration: 0, playing: false, rate: 0 }));
  assert.equal(stops[0].reason, STOP_REQUESTED);
});

test('the pre-roll is not animated through', () => {
  // Frames handed to the device are not audible until they clear its buffer.
  // Extrapolating through that window moves the mouth ahead of the sound at
  // the start of every clip; a cross-check against a recorded controller trace
  // caught exactly this.
  const { adapter, c } = harness();
  adapter.accept(snap({ file_time: 0, duration: 2, pre_roll_s: 0.020 }));
  assert.equal(adapter.fileTime(), 0);
  c.advance(10);
  assert.equal(adapter.fileTime(), 0, 'still inside the pre-roll');
  c.advance(10);
  assert.ok(Math.abs(adapter.fileTime() - 0) < 1e-9, 'pre-roll just elapsed');
  c.advance(30);
  assert.ok(Math.abs(adapter.fileTime() - 0.030) < 1e-9, 'advancing after it');
});

test('disconnect and controller fault each stop the mouth', () => {
  for (const [method, expected] of [['disconnected', STOP_DISCONNECTED],
                                     ['fault', STOP_FAULT]]) {
    const { adapter, stops, faults } = harness();
    adapter.accept(snap({ file_time: 0.2 }));
    adapter[method]();
    assert.equal(stops.length, 1, method);
    assert.equal(stops[0].reason, expected);
    assert.equal(faults.length, 1);
  }
});

test('stop fires exactly once however many times it is triggered', () => {
  const { adapter, stops } = harness();
  adapter.accept(snap({ file_time: 0.2 }));
  adapter.fault();
  adapter.disconnected();
  adapter.stop();
  assert.equal(stops.length, 1);
});

test('position is clamped to the clip and never negative', () => {
  const { adapter, c } = harness();
  adapter.accept(snap({ file_time: 1.95, duration: 2 }));
  c.advance(200);
  assert.equal(adapter.fileTime(), 2);
  const b = harness();
  b.adapter.accept(snap({ file_time: 0, duration: 2, rate: -1 }));
  b.c.advance(100);
  assert.equal(b.adapter.fileTime(), 0);
});

test('position never runs backwards inside one clip', () => {
  // A snapshot can arrive reporting slightly less than an already extrapolated
  // frame; the mouth must not stutter backwards.
  const { adapter, c } = harness();
  adapter.accept(snap({ file_time: 0.5, duration: 5 }));
  c.advance(200);
  const ahead = adapter.fileTime();      // ~0.7
  adapter.accept(snap({ file_time: 0.6, duration: 5 }));
  assert.ok(adapter.fileTime() >= ahead);
});

test('a snapshot from a superseded clip is rejected', () => {
  const { adapter } = harness();
  adapter.accept(snap({ file_time: 1.0, generation: 5, duration: 5 }));
  assert.equal(adapter.accept(snap({ file_time: 0.1, generation: 4 })), false);
  assert.equal(adapter.rejected, 1);
  assert.ok(adapter.fileTime() >= 1.0);
});

test('a new clip generation restarts file time from zero', () => {
  const { adapter, c } = harness();
  adapter.accept(snap({ file_time: 1.8, generation: 1, duration: 2 }));
  c.advance(50);
  adapter.accept(snap({ file_time: 0.0, generation: 2, duration: 3 }));
  assert.equal(adapter.fileTime(), 0.0);
});

test('a malformed snapshot is rejected and faulted, not animated', () => {
  const { adapter, faults } = harness();
  for (const bad of [null, {}, { file_time: 'x', rate: 1, duration: 1 },
                     { file_time: NaN, rate: 1, duration: 1 }]) {
    assert.equal(adapter.accept(bad), false);
  }
  assert.equal(adapter.rejected, 4);
  assert.ok(faults.every((f) => f.kind === 'malformed_snapshot'));
  assert.equal(adapter.fileTime(), 0);
});

test('getTime can be handed to playTrack as a bare function', () => {
  const { adapter, c } = harness();
  adapter.accept(snap({ file_time: 0.25, duration: 2 }));
  const getTime = adapter.getTime;        // detached, as playTrack stores it
  c.advance(100);
  assert.ok(Math.abs(getTime() - 0.35) < 1e-9);
});

test('before any snapshot the position is zero and nothing has stopped', () => {
  const { adapter, stops } = harness();
  assert.equal(adapter.fileTime(), 0);
  assert.equal(stops.length, 0);
  assert.equal(adapter.age(), null);
  assert.equal(adapter.isStale(), false);
});

test('ended reasons map conservatively onto stop reasons', () => {
  assert.equal(endedReasonToStop('clip_end'), STOP_CLIP_END);
  assert.equal(endedReasonToStop('participant_stop'), STOP_REQUESTED);
  assert.equal(endedReasonToStop('bench_complete'), STOP_REQUESTED);
  assert.equal(endedReasonToStop('audio_fault'), STOP_FAULT);
  assert.equal(endedReasonToStop(null), STOP_REQUESTED);
  assert.equal(endedReasonToStop(undefined), STOP_REQUESTED);
});

test('the transport bias is stated rather than silently compensated', () => {
  const { adapter } = harness();
  assert.match(adapter.transportBiasNote, /not measured or compensated/);
});

test('a recorded controller trace replays to the positions it recorded', async () => {
  // Cross-checks the adapter against real OutputPlayer output: the trace is
  // produced by tools/make_position_trace.py from the Python side, so the two
  // languages are verified against one shape of data rather than two
  // hand-written fixtures.
  const { readFile } = await import('node:fs/promises');
  const { fileURLToPath } = await import('node:url');
  const path = fileURLToPath(
    new URL('fixtures/position_trace.json', import.meta.url));
  let trace;
  try {
    trace = JSON.parse(await readFile(path, 'utf8'));
  } catch {
    // The fixture is generated; skip rather than fail if it is absent.
    return;
  }
  const c = clock(0);
  const stops = [];
  const adapter = new PlaybackClockAdapter({
    now: c.now, onStop: (reason) => stops.push(reason),
  });
  let checked = 0;
  for (const frame of trace.frames) {
    c.advance(frame.advance_ms);
    if (frame.snapshot) adapter.accept(frame.snapshot);
    if (typeof frame.expect_file_time === 'number') {
      assert.ok(Math.abs(adapter.fileTime() - frame.expect_file_time) < 0.002,
        `frame ${checked}: got ${adapter.fileTime()}, `
        + `expected ${frame.expect_file_time}`);
      checked++;
    }
  }
  assert.ok(checked > 0, 'trace contained no assertions');
  assert.deepEqual(stops, trace.expect_stops ?? stops);
});
