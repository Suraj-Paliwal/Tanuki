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
PortAudio own block clock: callback-entry time carries 12-40 ms of scheduling
jitter on this PC, so no threshold on it could separate jitter from a lost
10 ms block, whereas the device clock does not jitter and a 2 ms tolerance
suffices.

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
Both readings of where speech ended are recorded per event; which one the
analysis uses is research-owned.

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

## D8 — Tests run on a fake backend with a manual clock

**Decided (M1).** `FakeBackend` implements the same interface as the PortAudio
backend and is pumped by the test, which advances a `ManualClock`. All 113
current tests use it, and it models the two clock domains separately: the
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
| D4 | Which reading of "where speech ended" the analysis uses, and the lateness budget beyond which a deadline becomes a deviation |
