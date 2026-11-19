# M1 avatar clock adapter — renderer snapshot and executed checks

Checkpoint `M1-avatar-002`. First executed 2026-11-17; re-executed
2026-11-20 (Asia/Tokyo) after the R05 fixes, which this record now describes.
R05's findings and their dispositions are in
`reviews/M1-avatar-002/resolution.md`.

This is the second half of M1. `validation/audio_spike.md` covers the
controller side: the clock, the recorder and the deadline-gated output. This
covers the piece `goal.md` §7 asks for next — driving
`TanukiLipSync.playTrack(track, getTime)` from that controller's playback clock
instead of from a browser `<audio>` element, with a minimal renderer snapshot
brought forward to test it against.

A pass here means the adapter's logic behaves as the goal requires and agrees
with what the controller actually publishes. It is **not** visual
synchronisation, **not** acoustic, and establishes nothing about whether the
mouth matches speech.

## The renderer snapshot

Copied from `../08_avisspeech`, which was not modified. Verified byte-identical
at copy time and re-verifiable at any point:

```text
python tools/verify_snapshot.py --baseline
```

→ `23/23 assets match (21.0 MB); 5 tracked in Git, 18 excluded by .gitignore
and verified by hash only; PASS`

The verifier checks a closure, not only a list (R05-F11): every file under
`model/` and `vendor/` must be in the record, and an unlisted one is reported as
`UNEXPECTED` with a non-zero exit. Those directories are invisible to Git and
the bench page maps `three/addons/` onto `vendor/` wholesale, so a stray file
there would otherwise be loadable and unverified. Checked by dropping a scratch
file into `vendor/three/addons/` (exit 1, `UNEXPECTED`) and by
`tests/test_snapshot.py`.

| Part | Files | Size | In Git? |
|---|---|---|---|
| `model/` — glTF, binary, three textures | 5 | 19 MB | no, hash only |
| `vendor/three/` — `three.module.js` + LICENSE | 2 | 1.3 MB | no, hash only |
| `vendor/three/addons/` — the addon dependency closure | 11 | 158 KB | no, hash only |
| `src/` — renderer sources from the baseline | 5 | 46 KB | yes |

`asset-provenance.json` is tracked and records, per asset, the source path, the
SHA-256 and the byte count. That is how 21 MB of binary assets and a
third-party library stay out of the repository (`goal.md` §12) while the
snapshot remains verifiable and rebuildable.

**The addon closure was resolved, not guessed.** The baseline's
`../08_avisspeech/src/app.js` imports six three.js addons. That file is
deliberately not in this snapshot - the application shell is M4 work under
`goal.md` §12 - and `asset-provenance.json` now names it as the closure root.
The only in-snapshot consumer, `tools/avatar_clock_check.html`, imports
`GLTFLoader` alone; the other five are carried so M4 need not re-resolve the
closure. Following the six addons' following their relative imports transitively gives 11 files totalling
158 KB, against 29 MB for the whole `vendor` tree. The entry points are
`GLTFLoader`, `RoomEnvironment`, `EffectComposer`, `OutputPass`, `RenderPass`
and `ShaderPass`; the pulled-in files are `MaskPass`, `Pass`, `CopyShader`,
`OutputShader` and `BufferGeometryUtils`.

Version note: `08_avisspeech` documents three.js 0.169.0. This snapshot pins
the exact bytes by hash rather than trusting that string.

## What the adapter does, and the two things it must be told

`src/clock-adapter.js`. The controller owns playback, so the browser has no
audio element to read a time from; it receives `timing.PlaybackPosition`
snapshots and extrapolates between them.

**It extrapolates from snapshot arrival, not from `controller_time`.** That
field is a `perf_counter` reading in another process, and `goal.md` §7 says
browser timing is not authoritative. Mapping the two clocks would mean
estimating an offset across the very transport whose latency is in question.
The cost is stated rather than hidden: the mouth lags by the transport latency
L, and that bias is never subtracted out. During a clip's pre-roll the lag is
about **2L**, not L: `pre_roll_s` is relative to `controller_time` but the
adapter subtracts it from an arrival-based age, so the remaining pre-roll is
overstated by L as well (R05-F12a). On loopback both are sub-millisecond; neither
is measured here.

**Its lifecycle is explicit.** `arm()` is required immediately before every
`playTrack` and is the only way out of a stop. It clears the previous clip's
position, starts the staleness clock - so a controller that never sends a first
snapshot is a `stale_clock` fault rather than a mouth parked on a speaking pose
(R05-F04) - and refuses snapshots from older clips. Every stop is latched until
the next `arm()`, so a later snapshot cannot silently un-stop a faulted or
operator-stopped adapter and `onStop` fires once per armed clip (R05-F08). A
not-playing snapshot that arrives before the armed clip has been seen playing
is ignored rather than read as a stop (R05-F05). A snapshot without a numeric
`generation` is malformed (R05-F09). A newer generation that is *playing* while
an older clip is being driven is a `superseded` stop, because the renderer still
holds the old clip's track.

Things the adapter cannot derive and the controller therefore publishes. The
first two were added *because* the cross-language check below disagreed; the
other two came from review R05:

- **`pre_roll_s`.** Frames handed to the device are not audible until they
  clear the output buffer, so for the first output-latency of a clip the
  audible position is still zero. Linear extrapolation moved the mouth through
  that window, running ahead by the device latency at the start of every clip —
  about 20 ms on the bench configuration, and precisely where lip sync is most
  visible. The controller knows the pre-roll; it now reports it, and both
  `interpolate()` and the browser adapter hold position through it.
- **`ended_reason`.** An idle snapshot carries no clip: `file_time` and
  `duration` are both zero whether the clip finished or an operator stopped it.
  The adapter had been inferring completion from `file_time ≈ duration`, which
  cannot work. The player knows which happened and now says so, and the
  adapter maps an absent reason to "stopped" rather than "completed" — the one
  reading that could be mistaken for the participant having heard the whole
  prompt.
- **A clip that is starting.** Between `play()` and the first callback the
  audible start is unknown. The controller used to publish that window as
  "not playing", which the adapter read as a stop for the whole clip. It now
  publishes it as playing at file time 0 with the device latency as pre-roll,
  so the adapter holds the mouth closed instead (R05-F05).
- **The audible end.** The last block is handed to the device one output
  latency before it is heard. The controller used to flip to "not playing" at
  write completion, closing the mouth early and handing M3 an end that was
  early by the output latency - the opposite end of the clip from the pre-roll
  defect. It now keeps publishing `playing: true` through that tail, publishes
  `audible_end_s` (seconds until the clip is fully audible), and
  `OutputPlayer.audible_end` gives the controller-time instant, which is the
  value `goal.md` §6's "instruction audible end" needs (R05-F06). An explicit
  stop still reports stopped at once.

## Executed checks

Environment: Windows 11 Education 10.0.26300 x64, Node v24.14.0,
Python 3.13.9, from `09_nemotron`.

```text
node --test tests/test_clock_adapter.mjs
python tools/make_position_trace.py
python -m unittest discover -s tests -p "test_*.py"
python tools/verify_snapshot.py --baseline
```

| Requirement (`goal.md`) | Check | Status |
|---|---|---|
| §7 `getTime` returns file time including any leading silence | `position is file time, so it includes the clip leading silence` | PASS |
| §7 bounded interpolation between updates | `position advances between snapshots at the clip rate` | PASS |
| §7 explicit stale-update fault | `a stale clock stops the mouth instead of extrapolating forever` | PASS |
| §7 stale fault when no first snapshot arrives (R05-F04) | `no first snapshot after arm is a stale fault, not a parked mouth`, `the staleness clock restarts at arm, not at construction` | PASS |
| §7 a clip that is starting is not a stop (R05-F05) | Python `test_a_clip_that_has_not_reached_a_callback_is_starting_not_stopped`; JS `an idle snapshot before the clip starts is not a stop`, `the controller clip-starting snapshot holds position at zero` | PASS |
| §6/§7 clip end is the audible end (R05-F06) | Python `test_the_clip_is_playing_until_its_audible_end`; JS `the mouth keeps moving through the audible tail of a clip` | PASS |
| §6 stops are terminal until re-armed (R05-F08) | `a stop is latched: a same-generation snapshot cannot undo it`, `a stale stop recovers only through an explicit arm` | PASS |
| §6 no position leaks between clips (R05-F09) | `arm clears the previous clip position so it cannot leak`, `after arm, a late snapshot or stop from the previous clip is refused` | PASS |
| §7 stale clock must not hold the mouth open | `a stale clock holds its last position rather than jumping` | PASS |
| §7 adapter calls `stop()` on clip end | `clip end stops the mouth and is distinguished from an operator stop` | PASS |
| §7 …on abort | `a stop partway through the clip is not reported as clip end` | PASS |
| §7 …on fault | `a controller fault reason is not reported as a completed clip` | PASS |
| §7 …on disconnect | `disconnect and controller fault each stop the mouth` | PASS |
| §6 terminal reasons stay distinct | `ended reasons map conservatively onto stop reasons`, `an absent ended_reason does not claim the clip completed` | PASS |
| §7 no early mouth movement at clip start | JS `the pre-roll is not animated through`; Python `test_pre_roll_is_published_before_audio_and_zero_mid_clip`, `test_position_holds_through_the_pre_roll_then_advances` (R05-F07) | PASS |
| §7 position clamped to the clip | `position is clamped to the clip and never negative` | PASS |
| §6 a superseded clip must not drive the mouth | `a snapshot from a superseded clip is rejected` | PASS |
| §6 a different clip playing under the old track stops it | `a new clip playing under the old track is a superseded stop` | PASS |
| §7 malformed input is a fault, not animation | `a malformed snapshot is rejected and faulted, not animated` | PASS |
| §7 stop fires once | `stop fires exactly once however many times it is triggered` | PASS |
| mouth must not stutter backwards | `position never runs backwards inside one clip` | PASS |
| §12 snapshot provenance verifiable, as a closure | `tools/verify_snapshot.py --baseline`; `tests/test_snapshot.py` | PASS |
| the cross-language fixture matches the current controller (R05-F07) | `test_the_committed_position_trace_matches_the_current_controller` | PASS |

**30 JavaScript tests, 180 Python tests — 210 total, all passing.**

Every test added for an R05 finding was also run against the code with that
fix reverted, in a scratch copy, and failed there; the reverts and their
results are listed in `reviews/M1-avatar-002/resolution.md`.

### The cross-language check, and what it caught

`tools/make_position_trace.py` drives the real `OutputPlayer` on the fake
backend, samples `position()` every 10 ms, and writes a trace in which only
every fifth sample is *delivered* to the adapter. The other four are
assertions: the adapter must reach them by extrapolating, and the expected
value is the controller's own position at that instant. The current fixture is
53 frames, 12 delivered snapshots, 47 asserted positions.

Since R05 the trace covers both ends of the clip: frame 0 is sampled the
instant `play()` returns, before any callback (the clip-starting snapshot), and
the assertion window runs through the audible tail, so the clip-end flip is
inside the check (at 0.47 s, i.e. audible start 0.02 s + duration 0.45 s,
where it used to come at write completion, 0.45 s). The fixture is also a
standing guard now rather than a one-time discovery: a Python test regenerates
the trace and fails if the committed file differs, and the JS test fails, not
skips, if the fixture is missing.

Its limits, as R05 stated them: within an undelivered run both sides are
linear at rate 1.0, so what it pins is the slope, the pre-roll offset, the
clamps and the two ends; the expectation inherits the controller's own
definition of "audible", so a systematic error in that definition cannot be
detected by construction; and arrival time equals `controller_time` in the
replay, so it says nothing about D9's transport bias.

The point is that neither side's expectations are hand-written. It earned its
keep immediately — it failed twice on first run and both failures were real
contract defects, not test bugs: the pre-roll and the `ended_reason` described
above. Hand-written fixtures on both sides would have agreed with each other
and been wrong together.

## NOT_RUN — and these matter

| Item | Status | Why |
|---|---|---|
| Visual synchronisation against real speech | **NOT_RUN** | Needs audio playing against the rendered mouth and a human or a camera judging it. `goal.md` §7 explicitly says this needs bench verification and that energy-aligned tracks do not establish phoneme timing |
| Acoustic onset, anywhere | **NOT_RUN** | No acoustic reference channel exists; this PC has no input device |
| The adapter against the real renderer | **NOT_RUN** | `tools/avatar_clock_check.html` exists for exactly this and has **not been opened**. It needs an operator with a browser; it loads the model, drives it through a replayed trace, and checks that the mouth moves, closes on stop and closes on a stale clock. It plays no audio |
| The real transport | **NOT_RUN** | There is no server yet (M3/M4). Snapshots came from a file, not a socket, so transport latency and its jitter are uncharacterised and the stated bias is unquantified |
| `playTrack` under a real frame loop | **NOT_RUN** | Node tests call `getTime()` directly; `requestAnimationFrame` cadence, tab backgrounding and frame drops are untested |
| Mouth lead/offset settings | unchanged, unverified | The baseline's 30 ms anticipatory lead and `offset` trim were kept as-is. `goal.md` §7 says freeze them and add no browser AudioContext compensation for native audio — the adapter adds none. Whether 30 ms is right for native playback is unverified |
| Browser disconnect / refresh mid-clip | **NOT_RUN** | Requires the server; `goal.md` §9 requires a refresh not to restart playback |

## Limitations to carry forward

- A Node test of the adapter is not a test of the renderer. `TanukiLipSync`
  itself is unmodified baseline code and was not re-validated here.
- The synthetic track used by the bench page is a sine wave, not speech. It
  makes the mouth move so the wiring is observable; it says nothing about
  phoneme timing.
- The transport bias is a known, unmeasured, uncompensated lag: about 2L
  during a clip pre-roll and L thereafter. It gets added
  to every figure in `audio_spike.md` when the browser is in the loop.
- Mid-clip, `pre_roll_s` is derived from the per-block DAC time
  (`BlockTiming.first_frame_time`, via the clip's audible start), not from the
  stream's reported latency (corrected per R05-F12b). In the one-callback
  window before a clip starts, the only estimate available is the reported
  latency. `audio_spike.md` records those two estimators as disagreeing by
  about 12 ms on WASAPI, and the pre-roll inherits that uncertainty either way.
- The audible end has the same basis and the same uncertainty: it is the
  per-block DAC time of the last block plus its length, not a measurement.
- Nothing binds `staleAfterMs` (250 ms) to a required snapshot cadence. The
  fixture publishes every 50 ms; a server publishing much more slowly would
  fault every clip. M3/M4's transport design must state the cadence.
- The snapshot is pinned by hash against a baseline that is not itself
  version-controlled at those bytes; `verify_snapshot.py --baseline` detects
  drift but cannot restore it.
