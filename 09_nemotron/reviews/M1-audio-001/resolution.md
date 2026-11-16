# M1-audio-001 — findings, dispositions and fixes (round 1)

Round 1 of the bounded loop in `EGM_WORKFLOW.md` section 8. Two fresh-context
reviewers inspected the packet snapshot independently and both returned
**NEEDS_FIXES**:

- [R01, focused stage](goldfish-focused-R01-round-1.md) — 6 Major, 6 Minor.
- [R02, critic stage](goldfish-critic-R02-round-1.md) — 6 Major, 7 Minor.

Both independently verified all 14 SHA-256 digests in the packet manifest,
before and after their checks, and both reproduced the claimed `80 tests OK`
and the device-inventory rows. Neither saw the other's report during its
initial review. Their original reports are preserved unedited; this file
records only what was done about them.

The reviewers' substantive findings overlapped heavily, so they are
consolidated below under canonical IDs with both reviewers' IDs listed. No
severity was downgraded, and nothing was closed by moving it to a backlog.

## Snapshot note

Both reviewers observed that the reviewed files had been `git add`-ed during
the review window, and that `DEVELOPMENT_STATUS.md`, `README.md` and
`reviews/INDEX.md` were modified after the packet was frozen. The staging was
not done by the coordinator and nothing was committed; file *contents* matched
the manifest digests throughout, which both reviewers confirmed, so no
coverage was stale. The three modified files were outside the reviewed scope
(status and index updates recording that the review was in flight). The Git
index was deliberately left untouched rather than mutated during a review.

## Consolidated findings

| ID | Reviewers | Severity | Summary | Disposition |
|---|---|---|---|---|
| C1 | R01-F01, R02-F01 | Major | Onset estimate inflated 50 ms by a silent probe clip; evidence records mutually inconsistent | FIX |
| C2 | R01-F02, R02-F02 | Major | Recorder counted frames in the timeline before the enqueue, so lost audio shifted the sample/time mapping with `continuous: true` | FIX |
| C3 | R02-F03 | Major | `StreamTimebase.anchor` raised inside the input callback; stream died with no fault | FIX |
| C4 | R01-F03, R02-F04 | Major | `_committed` was session-scoped and never cleared, contaminating later trials' records | FIX |
| C5 | R02-F05 | Major | A guard-vetoed prompt returned bare `False`, which the contract read as "already committed", consuming the allowance | FIX |
| C6 | R01-F06, R02-F06 | Major | Hysteresis-band frames kept speech open but did not move the silence origin, so the assigned threshold could be silently shortened | FIX |
| C7 | R01-F04 | Major | 2 ms gap tolerance contradicted this PC's measured 12-40 ms callback jitter and accumulated drift | FIX |
| C8 | R01-F05, R02-F13 | Major | Dependencies were ranges while M1 requires pins and the packet called them pinned | FIX |
| C9 | R02-F07 | Minor | `TimingLedger.seq` was a read-modify-write across two threads | FIX |
| C10 | R02-F08 | Minor | Three divergent detector profiles; evidence named a fourth | FIX |
| C11 | R02-F09 | Minor | Zero-frame recording reported `continuous`/`finalized`; a failed `start()` could publish an empty WAV | FIX |
| C12 | R01-F12, R02-F10 | Minor | A `.partial` file from an abrupt kill reports zero frames (header written on close) | DEFER |
| C13 | R01-F08, R02-F11 | Minor | Tool stamped `verdict: PASS` on reports containing NOT_RUN/BLOCKED checks | FIX |
| C14 | R01-F11, R02-F12 | Minor | Audio-thread contract documented for `guard` only; torn read in `_open_segment` | FIX |
| C15 | R01-F09 | Minor | `capture_available` conflated "a default input exists" with "capture is possible" | FIX |
| C16 | R01-F10 | Minor | Nothing ties `PromptCandidate.deadline` to the `PauseTimer` that should be its only source | DEFER |
| C17 | R01-F07 | Minor | `decisions.md` D5 cited figures to the wrong source and quoted retracted single-shot numbers; one evidence file's command was missing from the reproduce list | FIX |

Also raised by both, and accepted: **M1 as a whole is not complete.** The
avatar clock-adapter demonstration required by `goal.md` section 7 and the M1
lens does not exist. That was already scoped as a separate checkpoint
(`M1-avatar-002`) and is recorded as an evidence gap, not a defect of this one.

## What was changed

### C1 — the onset estimate (the headline correction)

Both reviewers independently derived the same arithmetic from the published
JSON: the reported onset figures exceeded the commit figures by a constant
60.0000 ms across all 40 trials on WASAPI, which is not a device observation.
The cause was `_leading_silence_s` returning the *whole clip duration* when no
block exceeded its -45 dBFS floor, combined with a commit probe that used
`silence_clip(0.05)`. Every reported onset was inflated by exactly 50 ms.

Fixes:

- `_leading_silence_s` now returns `None` when no onset is detected, and
  `Clip.has_audible_onset` exposes that. A silent clip has no audible onset;
  reporting its length as "leading silence" was the defect.
- `OutputPlayer._maybe_commit` keeps the three quantities separate and records
  them separately: `commit_delay_s` (scheduling), `device_offset_s` (device
  latency) and `clip_leading_silence_s` (a property of the asset).
  `PromptCandidate.onset_delay_s` sums them and returns `None` when any term is
  unknown, instead of treating a missing term as zero.
- `tools/check_audio.py` probes with a faint tone carrying a known 10 ms lead,
  refuses to run if the probe has no detectable onset, and reports the three
  components alongside the total.
- Three regression tests, including one that asserts the exact artifact cannot
  recur (`test_the_onset_estimate_is_not_the_commit_delay_plus_a_clip_length`).

Corrected measurements, re-run on the fixed code (40 trials each):

| Device | Commit delay p95 | Device offset median | Onset delay p95 (incl. 10 ms probe lead) | Device-attributable p95 | Meets 100 ms candidate target |
|---|---|---|---|---|---|
| WASAPI, device 8 | 10.32 ms | 10.00 ms | 30.32 ms | ~20.3 ms | yes (estimated) |
| Default MME | 10.10 ms | 171.03 ms | 190.90 ms | ~181 ms | **no (estimated)** |

R02 predicted the corrected values as "WASAPI ≈ 20.1 ms, MME ≈ 182.8 ms"; the
re-measured device-attributable figures are 20.3 ms and ~181 ms. **No
conclusion changed**: WASAPI clears the candidate target, the Windows default
device does not, and decision D5 stands. The superseded figures and the wrong
explanation are marked as such in `validation/audio_spike.md` rather than
deleted.

### C2 — frames the recorder could not keep

`note_block` now runs only after a successful enqueue. A block that cannot be
enqueued, or that arrives after the writer thread has died, goes to the new
`CaptureTimeline.note_not_persisted`, which records a gap with a `counted`
(not estimated) frame count and opens a new segment on the far side of the
loss. `CaptureTimeline.note_persisted` is called from the writer thread with
what actually reached disk, and `integrity()` now reports `frames_persisted`,
`all_frames_persisted` and `empty`. `continuous` is true only when frames were
recorded, no gap exists, no clock anomaly occurred, and delivered equals
persisted.

A residual case the reviewers' proposed fix did not cover, found by the new
test: blocks already sitting in the queue when a writer dies have already been
counted. `finalize()` now reconciles delivered against persisted and records
the shortfall as a counted gap plus a `recording_shortfall` fault, because that
difference is only knowable at finalisation.

### C3 — nothing may raise on the audio thread

`StreamTimebase.anchor` clamps a non-monotonic anchor and *returns* an anomaly
string instead of raising; the timeline records it and `continuous` becomes
false. `ContinuousRecorder._callback` is a thin wrapper whose whole body is
guarded, turning any exception into a `capture_callback_error` fault rather
than letting sounddevice stop delivering blocks. A host API that changes its
block-timing method mid-stream now raises a `block_timing_method_changed`
fault — R02 noted the survey already shows WDM-KS doing exactly that. A new
`check_liveness(now)` lets the controller fault an attempt whose capture
callback has stopped, while the trial is still running, instead of discovering
it at finalisation.

### C4, C5 — prompt bookkeeping

`OutputPlayer.begin_attempt(attempt)` scopes the prompt slot to one trial
attempt and clears the committed, vetoed and armed state; it refuses to start
an attempt while a prompt is still armed. `cancel_candidate` returns a
`CancelOutcome` with four distinct outcomes (`removed`,
`already_cancelled`, `too_late_committed`, `nothing_armed`) and an
`allowance_consumed` property that is true only for a committed prompt. Every
branch is logged, including the no-op. A guard veto is remembered so a
controller cancellation arriving in the same instant is reported as
"already cancelled, allowance intact" — the race R02 identified, where the
one-prompt allowance was being spent on a prompt nobody heard.
`interrupted_committed_prompt` now tracks what was actually playing.

### C6 — the silence origin

A frame in the hysteresis band keeps the run open and resets the quiet counter,
so it is being treated as speech; it now also moves `_last_speech_frame`. The
last frame at or above the speech threshold is retained separately
(`last_strong_frame`, `strong_event_time`) along with `band_frames` and
`band_dwell_s`, so an analyst can see both readings of "where speech ended"
without re-running the detector.

Independently of that, `PauseTimer` now exposes `discovery_lateness` (how far
past the deadline already was when it first became knowable) and `too_late()`
against a configurable `lateness_budget_s` (default 50 ms), and `eligible()`
requires both conditions. A deadline discovered too late is a
`deadline_already_past` deviation for the controller to record and rearm from —
not a prompt fired after a fraction of the assigned threshold.
`validate_detector_profile` now states explicitly that it bounds only the fixed
part of the detector delay, since band dwell is data-dependent; D4's claim has
been corrected to match.

R02 noted that choosing between "band frames count as speech" and "keep the old
definition but refuse a stale deadline" is research-owned. Both are implemented:
the origin is corrected *and* the staleness guard exists, with both readings
recorded per event. Which definition the analysis uses is listed below as an
open research decision.

### C7 — gap detection on the device clock

The reviewers' diagnosis went further than a tolerance change. Callback-entry
time carries scheduling jitter (measured here: 12-40 ms against a 10 ms block),
so no time threshold on it can separate jitter from a lost 10 ms block.
`BlockTiming` now carries `device_time` — PortAudio's own stream clock, which
does not jitter — and `CaptureTimeline` uses consecutive device times for gap
detection with a tight 2 ms tolerance, falling back to callback time with an
80 ms tolerance only when the host API reports no block times (recorded as
`gap_basis` and `blocks_without_device_time`). The device-to-controller offset
is tracked with a minimum-biased estimator, since a callback can only ever run
late. Within a segment, `sample_to_time` interpolates between periodic
device-time anchors rather than extrapolating the nominal rate, which removes
the drift error from the mapping as well as from gap detection.

New tests: 30 ms of callback lateness on every block produces no gap; a
1000 ppm drifting device over three minutes of recall produces no gap and a
correct `drift_ppm`; a single omitted block is still exactly one gap; heavy
jitter *plus* one real loss still yields exactly one gap at the right sample.

### C8, C9, C10, C11, C13, C14, C15, C17

- Dependencies pinned exactly (`numpy==2.3.5`, `sounddevice==0.5.5`) with the
  PortAudio build recorded per measurement, and a note that pins must not be
  relaxed to ranges.
- `TimingLedger` takes a lock around the counter and the append.
- One named `DEFAULT_PROFILE` (32 ms / 96 ms / 150 ms), used by the tool,
  asserted equal to the dataclass defaults by test, and matching the documented
  profile. The library default's `min_speech_ms` was changed from 120 to 96 to
  agree.
- A failed `start()` tears down the sink and writer and removes the empty
  partial file instead of leaving it to be published; a zero-frame attempt
  records a `recording_empty` fault and is not `continuous`.
- The tool's verdict is `FAIL` / `BLOCKED` / `INCOMPLETE` / `PASS`, so a report
  containing NOT_RUN or BLOCKED checks can no longer read as a pass.
- `CaptureTimeline` mutations are under a lock; the audio-thread contract is
  documented on the callback, not only on `guard`.
- `inventory()` reports `default_capture_available` and `capture_possible`
  separately, lists input-capable device keys, and names the non-default input
  devices in its warning.
- `decisions.md` D5 rewritten with the corrected figures and correct sources;
  the missing command added to the reproduce list in `validation/audio_spike.md`.

### Deferred, with reasons

- **C12** (a `.partial` file reports zero frames after an abrupt kill). The
  file is *detectable* as an incomplete attempt, which is what `goal.md`
  section 10 requires, but its WAV header is only written on close, so a reader
  sees zero frames. Deferred to the M3 storage checkpoint, where the chosen fix
  is to write the partial as raw PCM with a sidecar metadata file and convert on
  finalisation, making a killed attempt fully recoverable. Owner: developer,
  M3. Affected gate: crash-recovery evidence for M3/M6, which remains unpassed.
- **C16** (nothing binds `PromptCandidate.deadline` to the `PauseTimer`). This
  seam does not exist yet — the controller that would own both is M3. The
  deadline-construction API will be added with it. Owner: developer, M3.
  Affected gate: M3 controller review.

## Checks after the fixes

Run from `C:/Users/suraj/Downloads/Tanuki/09_nemotron`, Python 3.13.9,
numpy 2.3.5, sounddevice 0.5.5, PortAudio V19.7.0-devel.

| Check | Command | Result |
|---|---|---|
| Unit suite | `python -m unittest discover -s tests -p "test_*.py"` | **113 tests OK** (was 80; 33 added for these fixes) |
| Device-free tool | `python tools/check_audio.py` | 8 PASS, 2 NOT_RUN, verdict `INCOMPLETE` |
| Host-API survey | `--survey` | WASAPI 22.0 ms / MME 180.0 / DirectSound 240.0 / WDM-KS 40.7 |
| Commit distribution, WASAPI | `--commit-trials 40 --device 8` | 0/40 early; commit p95 10.32 ms; onset p95 30.32 ms |
| Commit distribution, default | `--commit-trials 40` | 0/40 early; onset p95 190.90 ms; target check `FAIL` |

Still `NOT_RUN` or `BLOCKED`, unchanged by this round: microphone capture (no
input device on this PC), acoustic onset, last-speech-to-audible-response,
detector boundary error against real speech, echo and leakage, completion
suppression at 0.5 s, the renderer-side avatar clock, device drift over a real
session, and behaviour under load.

## Open research decisions this round surfaced

| Decision | Owner | Why it matters now |
|---|---|---|
| Which reading of "speech ended" the analysis uses: end of the in-speech run (including hysteresis-band frames) or end of the last frame above the speech threshold | Research director / analyst, before the timing tolerance is frozen | Both are now recorded per event. They differ by the band dwell, which directly changes how much silence a participant actually received |
| The lateness budget beyond which a deadline is a `deadline_already_past` deviation rather than a prompt | Research director, with the detector profile | Currently an engineering default of 50 ms |
| Whether a trial containing a counted recorder-side gap is analysable | Research director | `goal.md` section 6 leaves this open; the code now flags such attempts rather than deciding |

## Verdict after round 1

Coordinator position: all eight Majors are fixed with tests, two Minors are
explicitly deferred with named owners and still-open gates, and the corrected
measurements have been re-run and re-recorded. **This is not a pass.** A
fix-verification review of the changed snapshot is required before
`M1-audio-001` can be called complete, and M1 as a milestone additionally
requires the avatar clock-adapter checkpoint that does not yet exist.

---

# Round 2 — fix verification by R03

[R03, fix-verification stage](goldfish-fix-verification-R03-round-2.md)
reviewed the round-1 snapshot (`packet-round-2.md`), verified all 15 digests
before and after, ran the two permitted commands, and returned
**NEEDS_FIXES**. The report is preserved unedited.

R03's per-finding verdicts on the round-1 Majors: C1, C2, C3, C4, C5, C8
**VERIFIED FIXED**; C6 **VERIFIED FIXED** (origin) / **PARTIALLY FIXED**
(staleness guard unexercised on a reachable path); C7 **PARTIALLY FIXED**.
R03 confirmed that every invariant from round 1 still held: no output before
the deadline, the interval added exactly once, cancellation semantics, atomic
publication, no `measured` estimate. The two deferrals (C12, C16) were judged
legitimate.

The round-2 findings sit almost entirely on the C7 mechanism, plus one
process failure that was the coordinator's: the session preflight was created
while the review was in flight, so the packet's "113 tests" no longer
reproduced from the stated command.

## Round-2 findings and dispositions

| ID | Severity | Summary | Disposition |
|---|---|---|---|
| R03-F01 | Major | Stale `_last_device_end` across a fallback run fabricated gaps on return to device time (reachable on WDM-KS, this PC's only input host API); an unbounded `late_by` converted a device-clock jump into a huge lost-frame count | FIX |
| R03-F02 | Major | Minimum-biased offset estimator could step the mapping backwards and raise a spurious `clock_went_backwards`; its "late-only" rationale described the fake backend, not the real one | FIX |
| R03-F03 | Major | `continuous: true` on the callback-time basis, where a loss shorter than the tolerance is undetectable; `writer_shortfall` gap index past EOF | FIX |
| R03-F04 | Major | Snapshot drift: `preflight.py`, `tests/test_preflight.py`, `config/experiment.json` landed after the freeze; "113 tests" did not reproduce (139 did) | FIX (process) |
| R03-F05 | Minor | Default-device `--playback` command missing from the reproduce list; timestamp note wrong; superseded JSONs still read `"verdict": "PASS"` | FIX |
| R03-F06 | Minor | `on_fault` audio-thread contract undocumented (half of C14); `fsync` durability (half of R01-F12) had no disposition | FIX + DEFER (new C18) |
| R03-F07 | Minor | `begin_attempt()` was opt-in, so a controller omitting it reproduced the round-1 defect | FIX |
| R03-F08 | Minor | `too_late()` unreachable through the segmenter with any valid profile; its only test used a profile the validator rejects; C6's rationale for the guard was the path the origin fix removed | FIX |
| R03-F09 | Minor | The silence-origin choice governs the live deadline, not only the analysis, but was recorded as an analysis choice and hard-coded | FIX |
| R03-F10 | Minor | Onset `uncertainty_s` smaller than the known 12 ms latency disagreement; TeamViewer caveat missing from the primary evidence record; tool reintroduced "unknown treated as zero" | FIX |
| C15 residual | Minor | `duplex_check` could not target a pinned non-default input device | FIX |

## What was changed in round 2

**F01.** `CaptureTimeline` sets `_last_device_end = None` on every block that
arrives without a device time, so the first device-timed block after a
fallback run re-anchors instead of being measured against a stale reference.
A `late_by` of one second or more is recorded as a `device_time_discontinuity`
anomaly with the loss left unknown, never converted into a count. Tests:
`test_a_fallback_run_between_device_timed_blocks_is_not_a_gap` (k device /
m fallback / k device, plus repeated flips) and
`test_a_device_clock_jump_is_an_anomaly_not_a_fabricated_loss`.

**F02.** The rationale was wrong and is restated in the code and in
`decisions.md` D3: on the real backend the observation is `entry -
currentTime`, both sampled at callback entry, so lateness cancels and what
remains is a slowly drifting epoch difference. The estimator is now a slow
symmetric tracker (`OFFSET_TRACK_RATE = 0.01`); the derived block time is
clamped to the previous block's *start* so the mapping never runs backwards
(a first attempt clamped to the nominal *end* and would have erased device
drift - caught by the existing drift test before the change was recorded); a
correction larger than 5 ms is noted in `offset_steps` without affecting
`continuous`; and a device clock that genuinely runs backwards by more than
the tolerance is still flagged as `device_time_went_backwards`. `FakeStream`
now derives `first_frame_time` from the device clock plus a stable epoch in
device-time mode, matching `SoundDeviceBackend`, so callback lateness reaches
`entry_time` but not the mapping - the real asymmetry. The jitter test was
reordered so the first block is the latest, as R03 specified, and asserts a
monotonic mapping and no anomalies.

**F03.** `integrity()` reports `gap_basis`, `undetectable_gap_s` and
`continuity_supported_by_basis`, and `continuous` requires the device-clock
basis. `note_tail_shortfall` places a finalisation shortfall at
`frames_persisted` - the real end of the file - and opens no trailing segment;
the writer-failure test asserts every gap index is `<= RecordingResult.frames`.

**F04.** The round-3 packet lists every file in the tree, including the three
that landed during round 2, with the verbatim `git status --porcelain` output
and the per-file test split verified by running each file. The preflight
module and its tests are declared as an in-tree consumer of this layer and
offered for review in the same round rather than hidden from it. Process
note: two Git commits (`b4fd62f M1-audio-001`, `0198546 M1-fix`) were made by
the user during this period; the coordinator made none, and the round-3
packet cites the new base.

**F05.** Reproduce list completed; timestamp sentence names both windows; the
two superseded JSONs carry `superseded`, `superseded_reason`, `superseded_by`
and `verdict_note` keys at the top of the file.

**F06.** The `on_fault` / audio-path ledger contract is stated at the `_fault`
callsite and in D7. The `fsync` durability point is now **C18**, deferred to
the M3 storage checkpoint alongside C12 (owner: developer; gate: M3/M6
crash-recovery evidence, unpassed), recorded in D6.

**F07.** `arm()` and `play()` raise `AudioFault` outside a `begin_attempt()`,
and `arm()` refuses a candidate whose `trial_id` differs from the current
attempt. This caught the bench tool's own synthetic and `--playback` paths,
which armed outside an attempt; both were fixed and the measurements re-run.

**F08.** C6's rationale is restated (in code, D4 and this record): the origin
fix closes the band-dwell path; the staleness guard covers timeline gaps and
real detector latency. `StaleDeadlineTest` now uses `DEFAULT_PROFILE`, which
the validator accepts, and drives the segmenter through a `CaptureTimeline`
containing a 0.8 s recorder gap to show `too_late()` firing on a reachable
path; a companion test shows a valid profile on a healthy timeline is never
late.

**F09.** `PauseTimer(origin="run_end" | "last_strong")` reads the matching
field off the event and records the origin in `as_record()`. The open-decision
row below is restated as governing the live deadline. `SilenceOriginTest`
shows the two origins differ by exactly the band dwell.

**F10.** `uncertainty_s = max(block, |reported latency - per-block offset|)`,
with both readings in the estimate's `source` and in the `prompt_committed`
record; the TeamViewer caveat is in the spike record's header, Findings 2-3
and limitations; the tool skips and counts probes without an onset estimate
instead of writing zeros. `duplex_check` takes `--input-device` and gates on
`capture_possible`.

## Checks after round 2

| Check | Result |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | **153 tests OK** (74 + 53 + 26, each file run separately) |
| `python tools/check_audio.py` | 8 PASS, 2 NOT_RUN, verdict `INCOMPLETE` |
| `--commit-trials 40 --device 8` | 0/40 early; onset p95 29.61 ms (commit 9.61 + device 10.00 + probe lead 10.00) |
| `--commit-trials 40` (default) | 0/40 early; onset p95 192.88 ms; target check `FAIL` |
| `--survey` | WASAPI 22.0 / MME 180.0 / DirectSound 240.0 / WDM-KS 40.7 ms |
| `python preflight.py --config config/experiment.json` | pinned WASAPI resolves; verdict `INCOMPLETE_WITH_WARNINGS`; may start |

Still `NOT_RUN`/`BLOCKED`: microphone capture, acoustic onset,
last-speech-to-audible-response, detector error on real speech, echo,
completion suppression, renderer avatar clock, session-length drift, load. All
device figures were measured over TeamViewer.

## Open research decisions after round 2

| Decision | Owner | Note |
|---|---|---|
| Silence origin for the **live** deadline: `run_end` (band-inclusive) or `last_strong` | Research director, before the manipulation is frozen | Now configuration; both readings recorded per event; default `run_end` |
| Lateness budget (default 50 ms) | Research director with the detector profile | Bounds timeline-gap and detector-latency cases, not band dwell |
| Whether a trial with a counted recorder-side gap is analysable | Research director | Fabricated-gap paths removed in F01, so the flag now fires only on real loss or a clock anomaly |

## Verdict after round 2

Coordinator position: all four round-2 Majors and six Minors are fixed with
tests; the `fsync` point is deferred as C18 with owner and gate. This is
iteration 2 of the bounded three-iteration loop in `EGM_WORKFLOW.md` section
8. **This is not a pass.** Round 3 is a fix-verification review of the
complete current tree, including the preflight files.
