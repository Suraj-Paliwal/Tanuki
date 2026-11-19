# Engineering decision record

Decisions the developer made while implementing `goal.md`, with the alternatives
and what each one costs. These are **engineering** choices. They do not settle
any research-owned decision in `goal.md` section 14, and several of them are
only valid if a research decision later confirms the operational rule they
implement.

Each entry: what was decided, why, what else was considered, and what would
overturn it.

---

## D1 — Commit prompt output at the deadline, never before it

**Decided (M1).** The encouragement clip is *armed* with its eligibility
deadline and is only handed to the device inside an audio callback that
observes `controller_time >= deadline`. Audible onset is therefore
`deadline + output latency + clip leading silence`, i.e. always late, by an
amount that can be bounded and reported.

**Why.** `goal.md` section 13 forbids an unintended early trigger, and
section 7 asks for a bounded delay *after* the deadline. Scheduling the buffer
hand-off early enough for the sound to land exactly on the deadline would make
onset depend on a latency estimate being right, and an overestimate would
produce a prompt before the participant's pause had actually qualified. It also
shortens the window in which resumed speech can still cancel the clip.

**Alternatives considered.** (a) Pre-roll: commit at `deadline - latency` so
onset lands on the deadline. Rejected: early triggers are a protocol violation,
and the cancellation window shrinks to nothing. (b) A timer thread that calls
`play()`. Rejected: timer wake-up jitter is added on top of device latency, and
the decision would not be serialised with the callback that actually moves the
samples.

**Overturned by.** A research decision that the prompt must be audible at the
threshold rather than after it, which would require measured latency
compensation and an accepted early-trigger risk.

## D2 — The output stream stays open for the whole session

**Decided (M1).** One `OutputPlayer` holds a single output stream from session
start to session end and emits silence when idle.

**Why.** Opening a stream per clip puts device initialisation (tens of
milliseconds, variable) inside the prompt's critical path, and the buffer depth
at commit time would differ from the depth during calibration. Keeping it open
makes the commit boundary mean the same thing in every trial.

**Cost.** The output device is held for the session, so it cannot be
reconfigured mid-session. That matches `goal.md` section 12: trial settings are
frozen at session start.

## D3 — Dropped input frames become timeline gaps, not padding

**Decided (M1).** When an input callback arrives later than the capture
timeline predicts (or reports an overflow), the recorder records a
`TimelineGap` with an *estimated* lost-frame count and starts a new timeline
segment. The WAV keeps exactly the frames the device delivered.

**Why.** The two alternatives both corrupt evidence. Inserting silence to keep
one linear sample/time mapping writes audio that never existed into a research
recording. Ignoring the gap makes every later sample index map to the wrong
time, which would silently shift annotated speech boundaries.

**Consequence.** `sample_to_time` is piecewise, and `time_to_sample` returns a
flag when the requested instant falls inside a gap. Any attempt with a gap is
flagged; whether such a trial is analysable is a research decision.

**Extended after review (round 1, findings C2 and C7).** Three changes. A block
the *recorder* dropped (writer backlog or a dead writer) is now recorded the
same way, with an exact `counted` frame count rather than an estimate -
previously such frames were counted as written, which left the file short while
every later sample index mapped to a time earlier than the truth, with
`continuous` still reporting true. Delivered and persisted frame counts are
tracked separately and reconciled at finalisation. And gap detection moved onto
PortAudio own block clock: without it, the only timing available is
callback-entry time, which carries 12-40 ms of scheduling jitter on this PC,
and no threshold on that could separate jitter from a lost 10 ms block; the
device clock does not jitter and a 2 ms tolerance suffices.

**Corrected after round 2 (findings R03-F01, F02, F03).** Three defects in
that mechanism were fixed. The device-clock reference is now dropped whenever
a block arrives without a device time and re-anchored by the next block that
carries one, so a host API that stops and resumes reporting block times (the
survey shows WDM-KS doing this, and WDM-KS is the only host API with an input
device on this PC) no longer reads the whole fallback run as lost audio; a
device-clock jump of a second or more is recorded as a
`device_time_discontinuity` anomaly with the lost count left unknown, rather
than converted into a fabricated number. The device-to-controller offset
estimator was described wrongly: on the real backend the observation is
`entry - currentTime`, both sampled at callback entry, so lateness cancels and
what remains is a slowly drifting epoch difference - it is now tracked
symmetrically and slowly, the derived block time is clamped so the mapping
never runs backwards, a large correction is noted as an `offset_steps` entry
rather than reported as a clock fault, and a device clock that genuinely runs
backwards is still flagged as `device_time_went_backwards`. And `continuous`
now requires the device-clock basis: on the callback-time basis a loss shorter
than the 80 ms tolerance is invisible, and the field says so
(`continuity_supported_by_basis`, `undetectable_gap_s`) instead of asserting
what the evidence cannot support. The fake backend now models the real
asymmetry - in device-time mode the block's controller time is derived from
the device clock plus a stable epoch, so callback lateness reaches
`entry_time` but not `first_frame_time`, exactly as PortAudio behaves.

## D4 — The silence threshold is added to the speech offset, once

**Decided (M1).** `SpeechSegmenter` reports a speech offset at the *end of the
last frame above the speech threshold*, and separately reports when the
detector could confirm it (after the hangover). `PauseTimer` adds the
configured threshold to the offset, never to the confirmation time.

**Why.** `goal.md` section 6 is explicit that the configured waiting interval
must not be added twice through detector hangover plus a second timer. A
participant at the 0.5 s condition must wait 0.5 s of real silence, not
0.5 s + 150 ms.

**Consequence.** The deadline can be in the past by the time the controller
hears about it. `validate_detector_profile` refuses any profile whose hangover
plus decision budget reaches the shortest configured threshold, rather than
letting that configuration run and be late.

**Corrected after review (round 1, finding C6).** That static check bounds only
the *fixed* part of the detector reporting delay. An earlier version of this
entry claimed it guaranteed a timely deadline, which was wrong: how long the
detector dwells in the hysteresis band before giving up on a run is
data-dependent and cannot be bounded from the profile. Two changes close the
gap. First, a frame in the hysteresis band now moves the silence origin, since
it is already being treated as speech - otherwise a participant trailing off
quietly would be dated as silent from the last loud frame and could receive the
prompt after a fraction of the assigned threshold. Second, `PauseTimer` exposes
`discovery_lateness` and refuses to be eligible when the deadline was already
past by more than a configurable budget (default 50 ms); the controller records
that as a `deadline_already_past` deviation and rearms instead of speaking.
Both readings of where speech ended are recorded per event.

**Corrected after round 2 (finding R03-F09).** That choice governs the *live*
deadline during collection, not only the analysis afterwards: the pause timer
consumes whichever origin is configured, and the two differ by the band dwell,
which is silence the participant may or may not have received before the
prompt. It is therefore a research decision about the manipulation, and it is
applied as configuration - `PauseTimer(origin="run_end" | "last_strong")`,
recorded with the trial - rather than by editing code. The engineering default
is `run_end`. The staleness guard (`too_late`) covers a different hazard from
the origin: with a valid profile on a healthy timeline an offset is always
confirmed before its deadline; it can still be discovered late when a capture
gap falls between the last speech frame and the confirming frame, or when a
real detector buffers beyond its nominal hangover, and those are the cases the
50 ms budget bounds (R03-F08).

## D5 — WASAPI, not the Windows default device

**Proposed (M1), pending final-hardware confirmation.** Use the WASAPI host API
for output, pinned by device identity rather than by index.

**Measured on this PC** (`validation/audio_spike.md` Findings 2 and 3; figures
corrected in round 1 of review, see below). Device-reported output latency and
worst callback interval, one second of silence per host API:

| Host API | Reported latency | Worst callback interval |
|---|---|---|
| MME (the Windows default here) | 180.0 ms | 33.5 ms |
| DirectSound | 240.0 ms | 30.0 ms |
| **WASAPI, device 8** | **22.0 ms** | **11.8 ms** |
| WDM-KS (SPDIF) | 40.7 ms | 40.3 ms |

Over 40 armed prompts, the estimated audible-onset delay after the eligibility
deadline, excluding the probe clip own 10 ms lead:

| Device | p95 | Of which device offset |
|---|---|---|
| WASAPI, device 8 | ~20.3 ms | 10.00 ms |
| Default MME | ~181 ms | 171.03 ms |

**Why.** The candidate engineering target in `goal.md` section 7 is a
playback-onset delay after the deadline of at most 100 ms at the 95th
percentile. The Windows default device misses it by nearly a factor of two;
WASAPI clears it with a wide margin. WASAPI also has the tightest callback
cadence, which matters because the commit decision is taken inside a callback.

**Corrected after review (round 1, finding C1).** The first version of this
entry quoted two single-shot figures (10.4 ms on WASAPI, 189 ms on MME) that
`validation/audio_spike.md` itself said must not be quoted, because they were
taken before the device buffer had filled. The spike meanwhile quoted
distribution figures inflated by 50 ms of probe-clip artifact. Both are
superseded by the table above, which separates the scheduling delay, the device
offset and the clip leading silence instead of summing them into one number.

**Not yet established.** These are estimates from PortAudio own latency
reporting, not acoustic measurements, and the two available reports still
disagree on WASAPI: `stream.latency` says 22.0 ms where the per-block DAC
offset says 10.00 ms. Resolving that needs the acoustic reference channel,
which needs a microphone this PC does not have. The device identity must also
be pinned in configuration and re-checked at session start, because PortAudio
indices move when a Bluetooth headset connects - and these measurements were
taken over a TeamViewer session, which can itself redirect or claim audio
endpoints, so they must be repeated at the physical machine with the final
speakers and microphone attached.

## D6 — int16 at 48 kHz, written through a queue, published by rename

**Decided (M1).** The preserved recording is 16-bit PCM mono at 48 kHz, written
by a writer thread fed from the audio callback, to `<name>.wav.partial`, renamed
to `<name>.wav` on finalisation. The detector gets a separate normalised 16 kHz
stream with an index map back to the original.

**Why.** 16-bit/48 kHz is standard for speech research and is what `wave` from
the standard library writes without an extra dependency. Disk I/O inside an
audio callback risks underruns, so the callback only copies bytes. The
`.partial` name makes an attempt that never finalised detectable after a crash,
which `goal.md` section 10 requires instead of a file that merely looks
complete.

**Cost.** A full-scale 16-bit recording cannot represent a very quiet signal as
finely as 24-bit or float. Microphone gain must be set during calibration.

**Known limitation, deferred to M3 (finding C12).** The `.partial` file is
detectable after a crash but reports zero frames, because `wave` writes its
header on close. The planned fix is to write the partial as raw PCM with a
sidecar metadata file and convert on finalisation, so a killed attempt is
recoverable rather than merely detectable.

**Also deferred to M3 (finding C18, from R01-F12 via R03-F06).** Publication
by `os.replace` is atomic but not proven durable: nothing flushes or `fsync`s
the file before the rename or the directory after it, so an attempt that was
"published" immediately before a power loss may not survive. The M3 storage
checkpoint owns both this and C12 together; its crash-recovery acceptance must
include a durability check, and until then the M3/M6 crash-recovery gate is
unpassed.

## D7 — A guard callable carries event precedence into the commit instant

**Decided (M1).** `OutputPlayer.arm(clip, candidate, guard=...)` takes a
non-blocking callable that returns a cancellation reason or `None`. It is
evaluated inside the callback, under the player lock, immediately before
commitment; a returned reason (or an exception) cancels the candidate silently.

**Why.** `goal.md` section 6 requires terminal conditions to be re-evaluated
immediately before output commitment, with Stop, fault, completion and timeout
all outranking an eligible encouragement. A guard evaluated at the only instant
that matters is simpler and harder to get wrong than mirroring controller state
into the audio layer.

**Constraint this imposes on M3.** The guard must read already-decided flags
and must not lock, allocate or block. The controller owns the one-prompt
allowance; the device layer only refuses to speak twice at once.

**The same contract applies to `on_fault` and to ledger writes from the audio
path (round 2, finding R03-F06).** `ContinuousRecorder` and `OutputPlayer`
call the controller-supplied `on_fault` synchronously, possibly from inside
the PortAudio callback and (for the player) while holding the player lock.
The handler must not block, take a lock a slow holder might own, do I/O, or
raise; it sets flags and returns, and the controller reads `faults` and the
ledger on its own thread. The ledger itself takes only a short uncontended
lock around the sequence counter and the append. Per-attempt scoping of the
prompt slot is likewise not optional: `arm()` and `play()` refuse to run
outside a `begin_attempt()`, and a candidate whose `trial_id` differs from
the current attempt is refused (R03-F07).

## D8 — Tests run on a fake backend with a manual clock

**Decided (M1).** `FakeBackend` implements the same interface as the PortAudio
backend and is pumped by the test, which advances a `ManualClock`. Every
Python test that touches an audio stream uses it (no count is given here: a
number in this sentence went stale in three consecutive rounds, R04-F05 and
R05-F03), and it models the two clock domains separately: the
device clock advances by exactly one block per block while callback entry can
be delayed, which is what makes the jitter-versus-loss cases testable at all.

**Why.** This PC currently exposes no input device at all, so a device-backed
test suite could not run here. More importantly, timing boundaries ("nothing
audible before the deadline", "the gap is 4800 frames") are only checkable
deterministically.

**Limit, stated wherever it matters.** A fake-backend pass is not hardware
validation. Real device latency, acoustic onset, echo and behaviour under load
are explicitly out of its scope and remain `NOT_RUN` in
`validation/audio_spike.md`.

## D9 — The browser extrapolates from snapshot arrival, not from the controller clock

**Decided (M1, avatar checkpoint).** `src/clock-adapter.js` timestamps each
position snapshot when it arrives and extrapolates from that local instant. It
does not attempt to map `controller_time` into the browser time base.

**Why.** `controller_time` is a `perf_counter` reading inside another process.
`performance.now()` has a different epoch and its own drift, and `goal.md`
section 7 states plainly that browser timing is not authoritative. Estimating
the offset between the two clocks would mean estimating it *across the very
transport whose latency is the unknown* - and getting it wrong moves the mouth
in whichever direction the error points, including early.

**Cost, stated rather than hidden.** The mouth lags by however long a snapshot
took to arrive, L. During a clip's pre-roll it lags by about **2L**:
`pre_roll_s` is stated relative to `controller_time`, but the adapter subtracts
it from an arrival-based age, so at arrival the remaining pre-roll is overstated
by L on top of the arrival lag itself (R05-F12a). On loopback both are
sub-millisecond, but they are real biases, they are never subtracted out, and
`transportBiasNote` on the adapter says so. They are currently unmeasured
because there is no transport yet (M3/M4 own the server).

**Alternatives considered.** (a) Clock-offset estimation with a slow tracker,
as the device offset uses. Rejected for now: the device-offset estimator works
because both of its terms are sampled at the same instant, which is exactly
what a cross-process transport cannot offer. Worth revisiting once the real
transport exists and its jitter can be characterised. (b) Having the browser
drive its own `<audio>` element. Rejected outright: the goal forbids playing
the same clip twice, and it would put protocol-critical timing on the browser.

## D10 — The controller publishes what the renderer cannot infer

**Decided (M1, avatar checkpoint).** `timing.PlaybackPosition` gained two
fields because a cross-language check showed the renderer was guessing at both:

- `pre_roll_s` - seconds until the clip becomes audible. Frames handed to the
  device sit in its output buffer first, so for the first output-latency of a
  clip the audible position is still zero. Extrapolating through that window
  ran the mouth ahead of the sound by the device latency at the start of every
  clip, roughly 20 ms on the bench configuration, and the start of a clip is
  where lip sync is most visible.
- `ended_reason` - why playback stopped. An idle snapshot carries no clip:
  `file_time` and `duration` are both zero whether the clip finished or an
  operator stopped it. The adapter had been inferring completion from
  `file_time` reaching `duration`, which cannot work on an idle snapshot, and
  `goal.md` section 6 requires terminal reasons to stay distinct.

**Why publish rather than infer.** In both cases the controller already knew
the answer and the renderer structurally could not. An inference that happens
to be right on the bench and wrong on real hardware is worse than no
inference: this is the same lesson as D5's latency reports and D3's gap basis.
The adapter now maps an absent `ended_reason` to "stopped" rather than
"completed", because "the clip finished" is the one reading that could be
mistaken for the participant having heard the whole prompt.

**How they were found.** `tools/make_position_trace.py` drives the real
`OutputPlayer` and emits a trace in which only every fifth position is
delivered to the adapter; the rest are assertions the adapter must reach by
extrapolating, with the controller's own position as the expected value. Both
defects failed that check on its first run. Hand-written fixtures on each side
would have agreed with each other and been wrong together.

**Extended after review R05.** The same principle covered three more gaps,
each a case where the controller knew the answer and the published contract
did not say it:

- *A clip that is starting.* Between `play()` and the first callback the
  audible start is unknown, and `position()` used to report that window as
  "not playing", which the adapter correctly read as a stop - for the whole
  clip (R05-F05). It now publishes playing at file time 0, with the stream's
  reported latency as `pre_roll_s` because nothing better is known yet.
- *The audible end* - `audible_end_s`, the symmetric twin of `pre_roll_s`. The
  last block is written one output latency before it is heard. The position
  used to flip to "not playing" at write completion, which closed the mouth
  early and, more seriously, would have handed M3 an "instruction audible end"
  (`goal.md` §6, `recall_cap_origin`) early by the output latency on every
  trial (R05-F06). The position now stays `playing` through the tail and
  `OutputPlayer.audible_end` exposes the controller-time instant. The
  alternative R05 offered - a post-roll field and a deferred stop in the
  adapter - was not taken, because it would leave every other consumer of
  the playing flag with the early end. An explicit stop still reports stopped
  at once: frames already in the device buffer will be heard (`goal.md` §6
  promises no perfect cancellation), but the mouth must not keep animating a
  clip the controller abandoned.
- *The adapter's lifecycle.* `arm()` before every `playTrack`, latched stops,
  a staleness clock that starts at arm, and a required `generation`
  (R05-F04, F08, F09). This is the browser half of the same rule: the adapter
  acts only on what it has been told for *this* clip.

**Still unestablished.** `pre_roll_s` and the audible end inherit the
device-latency uncertainty recorded in D5 (two estimators that disagree by
about 12 ms on WASAPI). Mid-clip both come from the per-block DAC time, not the
reported latency. Visual synchronisation is unverified;
`tools/avatar_clock_check.html` exists to check the adapter against the real
renderer and has not been opened.

---

## Open research decisions these choices depend on

Listed here only to make the dependency visible; the owners and deadlines are
in `goal.md` section 14.

| Engineering decision | Depends on research confirming |
|---|---|
| D1 | That the prompt may be audible shortly *after* the threshold |
| D4 | The detector profile (frame size, hangover) as part of the frozen manipulation |
| D5 | The final PC/speaker/microphone configuration and the frozen timing tolerance |
| D7 | The event precedence table and the rearming rule in `goal.md` section 6 |
| D9, D10 | Nothing research-owned. Both are engineering choices about where a number is computed; neither changes the manipulation |
| D4 | Which reading of "where speech ended" the live deadline counts from (`run_end` or `last_strong`), and the lateness budget beyond which a deadline becomes a deviation |
