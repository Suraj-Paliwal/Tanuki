# Goldfish review — M1-audio-001 / focused / R01 / round 1

## Provenance and scope

- **Fresh context: yes.** Separate agent session with no development-chat
  history; my entire input was the dispatch message, `packet.md`,
  `EGM_WORKFLOW.md`, `reviewers/GOLDFISH.md`, `goal.md`, `AGENTS.md`, the
  manifest files and the read-only baseline. Isolation mechanism: a new
  subagent session whose context contains no prior turns of the implementation
  conversation. I did not open `reviews/INDEX.md`, `DEVELOPMENT_STATUS.md` or
  any other reviewer's report, to avoid seeing a verdict. `reviews/M1-audio-001/`
  contained only `packet.md` at review time, so no concurrent reviewer output
  was available to leak.
- **Snapshot: content unchanged; Git state around it changed.**
  - Base commit `eeb0f0e2f4da98cf1e2cfade27a3c49a4b840479` confirmed
    (`git rev-parse HEAD`).
  - All **14** manifest SHA-256 digests recomputed at the start and again at the
    end of the review and **all 14 match the packet exactly**
    (`timing.py d763a690…`, `audio_io.py 5b674c24…`, `tools/check_audio.py
    e3025915…`, `requirements.txt 5b95c1de…`, `decisions.md 54b0fa7c…`,
    `.gitignore 60945863…`, `tests/test_timing.py 1c05c5a5…`,
    `tests/test_audio_io.py c531217a…`, `validation/audio_spike.md ce100336…`,
    and the five `validation/audio_check_*.json` files). **No reviewed coverage
    is stale.**
  - However, the packet's "Snapshot identity" section no longer describes the
    tree. It states "every reviewed file is untracked" and lists `??` entries;
    `git status --porcelain` now reports those paths as **staged (`A`)**, and
    additionally reports `M 09_nemotron/DEVELOPMENT_STATUS.md`,
    `M 09_nemotron/README.md`, `M 09_nemotron/reviews/INDEX.md` — three
    documents that are **not in the manifest, carry no digest, and were
    modified after `packet.md` was written** (mtimes 02:35:19–02:36:14 vs
    packet 02:34:30). Staging does not alter file bytes and those three files
    are outside the reviewed scope, so nothing I checked is invalidated; but
    per `EGM_WORKFLOW.md` §6 the packet's snapshot description should be
    corrected and those three documents either added to the manifest or
    explicitly excluded. See also the evidence-gap list below.
- **Stage/lenses:** focused route — comprehension combined with the changed
  behaviour and its test/evidence lens. Lenses: "Audio feasibility, M1" and
  "Recording/storage, M3/M6" (`EGM_WORKFLOW.md` §5).
  **Named readiness question:** is this timing/device layer sound enough to
  build the M3 experiment controller on, and is the recorded evidence described
  accurately?
- **Files inspected in full:** `reviews/M1-audio-001/packet.md`,
  `reviewers/GOLDFISH.md`, `EGM_WORKFLOW.md`, `AGENTS.md`, `decisions.md`,
  `goal.md` (§§1–8, 10–15), `timing.py` (875 lines), `audio_io.py` (1193),
  `tools/check_audio.py` (570), `tests/test_timing.py` (410),
  `tests/test_audio_io.py` (516), `validation/audio_spike.md`,
  `requirements.txt`, `.gitignore`, all five `validation/audio_check_*.json`,
  and the cited baseline lines in
  `../08_avisspeech/src/tanuki-lipsync.js` (`update` track branch 194–206,
  `playTrack` 290–300, `stop` 455–462 — the packet's line references and its
  claim that an external-clock track never finishes itself are both correct:
  line 202 auto-finishes only `if (!this._getTime …)`).
- **Referenced sources unavailable:** none needed. The two `.docx` research
  plans in `goal.md` §2 were not consulted and are not required for this
  scope (`goal.md` §3 carries the study contract).
- **Tools/tests actually executed** (scratch directory `/tmp/gf-R01-scratch`,
  `PYTHONPYCACHEPREFIX` redirected there; nothing written inside
  `09_nemotron` except this report):
  1. `python -m unittest discover -s tests -p "test_*.py"` from
     `09_nemotron` → **`Ran 80 tests … OK`**. The packet's "80 tests OK"
     claim is **confirmed**. (Wall time 0.304 s here vs 0.142 s claimed —
     immaterial, different machine load.)
  2. `python tools/check_audio.py` (no flags; permitted, opens no stream;
     I read `main()` first and confirmed it writes nothing without `--out`)
     → `capture_available=False playback_available=True`, 8 PASS + 2 NOT_RUN,
     exit 0. **Confirmed.**
  3. Per-file test counts recounted from source: `test_timing.py` = **43**,
     `test_audio_io.py` = **37**. **Both claims confirmed.**
  4. Digest verification and JSON evidence parsing (`sha256sum`,
     `python -c "import json…"` — no project module imported, no device
     touched).
- **Explicit NOT_RUN by me:** `--playback`, `--survey`, `--commit-trials`,
  `--duplex` (prohibited by the packet; I did not run them). I therefore did
  **not** re-measure any device figure; I verified every device number in the
  packet against the committed JSON reports instead. The reproduction of
  finding **F02** below is also **NOT_RUN**: demonstrating it requires a new
  test file inside `09_nemotron`, which I am not permitted to write, so it is
  reported as a code trace with the exact arithmetic and a proposed regression
  test rather than as an executed failure.

### Claim-by-claim verification of the packet's evidence table

| Packet claim | Verified against | Result |
|---|---|---|
| 80 tests OK | executed | **confirmed** |
| 43 + 37 tests | source recount | **confirmed** |
| deadline = offset + threshold exactly | executed; `audio_check_*.json` `pause_deadline_*` details (`offset 0.320s + 0.5/1.0/2.0s`) | **confirmed** |
| 9600 frames, 0 gaps, speech after commit sample | `tests/test_audio_io.py:473` asserts exactly this | **confirmed** |
| 0.25 s stall → 1 gap, 12000 frames lost, file still 9600 frames | `tests/test_audio_io.py:149` | **confirmed** |
| 960 frames published + `recording_write_failed` | `tests/test_audio_io.py:198` | confirmed, but see **F02** (the same attempt reports `continuous: true` / 2400 frames in its integrity block) |
| inventory: `capture_available=false`, 4 host APIs, 20 devices | executed; `audio_check_survey.json` inventory (4 hostapis, 20 devices, 2 inputs, 18 outputs) | **confirmed** (but see **F09** on what the flag means) |
| capture BLOCKED, `sd.default.device == [-1, 1]` | `audio_check_*.json` (`default_input_device: -1`, `default_output_device: 1`) | **confirmed** |
| WASAPI 0/40 early, commit p95 10.13 ms, onset p95 70.13 ms | `audio_check_commit_wasapi.json` | numbers transcribed correctly; **the 70.13 ms figure is wrong at source — see F01** |
| default device p95 232.78 ms, FAIL vs 100 ms candidate | `audio_check_commit_default.json` | transcribed correctly; **same defect, see F01** |
| survey WASAPI 22.0 / MME 180 / DS 240 / WDM-KS 40.7 ms | `audio_check_survey.json` | **confirmed** |
| no code path produces `method="measured"` | read `timing.py` (`MEASURED` is only a constant and a test import) and `audio_io.py` (`ESTIMATED` only) | **confirmed** |
| `requirements.txt` = "pinned dependencies" | read the file | **not confirmed — see F05** |

## My understanding

M1 is a feasibility slice that must establish, on this PC, that native capture,
playback and clock mapping can satisfy the protocol's timing rules — nothing
more. The controller (not the browser) owns audio: one monotonic controller
clock plus device sample positions are the only authority for intervals, and a
silence deadline is `end of the last detected participant speech frame +
the trial's configured threshold`, computed in exactly one place, with the
detector's confirmation delay recorded separately so the waiting interval is
never charged twice. The encouragement clip is not scheduled; it is *armed*
with that deadline and only handed to the device inside the audio callback that
first observes `now >= deadline` and whose controller-supplied guard still
returns `None`, so an early trigger is structurally impossible and the output is
instead late by a bounded, reportable amount. Before that instant a
cancellation removes the clip and nothing is heard; after it the one-prompt
allowance is spent even if the participant resumes speaking, and that must be
logged as an overlap rather than retried. Meanwhile one continuous recording
keeps exactly the frames the device delivered — a dropped input block becomes a
flagged timeline gap with an *estimated* lost-frame count rather than invented
silence — and is published by rename so an attempt that never finalised stays
detectable. Finally, every onset number this layer can produce is a device
latency *estimate*; a measured acoustic onset needs a recorded playback
reference that this PC cannot provide, and the code must never let the former
masquerade as the latter.

## Findings

### M1-audio-001-R01-F01 — Major — the headline onset numbers are inflated by a silent-probe artefact, and the evidence record misdiagnoses it twice

- **Location:** `tools/check_audio.py:391` (`clip = silence_clip(clip_s, …)`),
  `audio_io.py:247-257` (`_leading_silence_s`), `audio_io.py:1144-1149`
  (`onset = Estimate(seconds=timing.first_frame_time + clip.leading_silence_s …)`);
  claims in `validation/audio_spike.md` Finding 3 (table and notes 2 and 3) and
  `decisions.md` D5; packet rows "§7 playback delay after the deadline" and
  "§7 same, default device".
- **Requirement:** `goal.md` §7 ("Audible onset measurement or calibrated
  estimate, its method and uncertainty … Report all observations and maxima";
  the 100 ms p95 candidate target); `AGENTS.md` "Do not turn … timer timestamps
  into acoustic measurements"; `EGM_WORKFLOW.md` §5 ("A bench test with mock
  audio does not prove acoustic timing. State these limits where relevant").
- **Concrete failure.** `commit_distribution` probes with
  `silence_clip(0.05)` — an all-zero clip. `_leading_silence_s` scans for the
  first block above −45 dBFS and, finding none, falls through to
  `return mono.size / samplerate` (line 257), so the probe reports
  `leading_silence_s = 0.050`. `_maybe_commit` then adds that to every onset
  estimate. The artefact is exactly 50 ms and is visible in the committed
  evidence: in `audio_check_commit_wasapi.json`, `onset − commit` is
  **60.0000 ms at the median (65.9409 − 5.9409), at the p95 (70.1303 − 10.1303)
  and at the max (70.8046 − 10.8046)** — constant to seven digits, i.e. a
  per-block DAC offset of exactly **10.000 ms** (one 480-frame block) plus the
  50 ms artefact. Corrected figures: WASAPI estimated onset-delay p95
  ≈ **20.1 ms**, not 70.13 ms; default-device p95 ≈ **182.8 ms**, not
  232.78 ms (`229.3888 − 9.2392 = 220.15` ⇒ MME DAC offset ≈ 170.2 ms, which is
  consistent with its 180 ms reported latency).
  Three consequential misstatements follow:
  1. `audio_spike.md` Finding 3 note 2 — "the steady-state per-block DAC offset
     implies about 60 ms … the ~70 ms p95 above uses the per-block figure, which
     is the larger and therefore the safer of the two for planning" — is
     **wrong in both directions**. The per-block offset is 10 ms, which is
     *smaller* than the 22 ms `stream.latency`, so the recorded estimate is
     optimistic about real device latency, not conservative. The "discrepancy"
     the note cannot resolve is not a discrepancy at all; it is this artefact.
  2. Note 3 — the 10.37 ms single-shot `--playback` figure was "measured on the
     first commitment after the stream opened, before the device buffer had
     filled" — is also **wrong**. That run used a *tone* clip
     (`leading_silence_s = 0`), and `audio_check_wasapi.json` shows
     `onset 10.37 − commit 0.37 = 10.00 ms`: the identical DAC offset. The
     single-shot and 40-trial runs agree exactly once the artefact is removed;
     there was no buffer warm-up effect.
  3. `decisions.md` D5 states the per-block DAC offset is "~10 ms" while
     `audio_spike.md` says "about 60 ms" for the same quantity. D5 is right
     and the spike is wrong, so the packet contains two contradictory accounts
     of its own central measurement.
  Production consequence (independent of the bench tool): on WASAPI
  `timing.first_frame_time` is built from a constant nominal one-block DAC
  offset, so the `audible_onset` Estimate written into trial records
  **understates** the device's own reported output latency (22.0 ms) by ~12 ms,
  while `uncertainty_s` is hard-coded to one block duration
  (`audio_io.py:1147`, 10 ms) — narrower than the known disagreement between
  the two latency reports, and excluding the whole unmeasured acoustic path.
  The *decision* to use WASAPI over MME survives the correction (20 ms vs
  183 ms), and the default-device FAIL verdict survives too (183 ms > 100 ms);
  only the numbers and the explanations are wrong.
- **Proposed fix.** (a) Make `_leading_silence_s` return `None` (or raise) when
  it finds no signal, and make `Clip` refuse to report a whole-clip silence as
  "leading silence"; (b) probe with a tone of known lead in
  `commit_distribution`, and report *commit delay*, *per-block DAC offset*,
  *`stream.latency`* and *clip lead* as four separate recorded numbers instead
  of one summed onset; (c) set `uncertainty_s` to at least
  `|stream.latency − per-block offset| + blocksize/samplerate`, or to `None`
  ("not characterised", which `Estimate` already distinguishes from zero) until
  an acoustic calibration exists; (d) rewrite `audio_spike.md` Finding 3's
  table and notes 2–3 and align D5 with them.
- **Verification.** Coordinator re-runs
  `python tools/check_audio.py --commit-trials 40 --device 8` after the fix and
  checks that `onset − commit` equals the reported DAC offset alone; add unit
  tests that `silence_clip(0.05)` does not report 0.05 s of *leading* silence
  and that a tone with a 20 ms lead reports 20 ms; re-derive every figure in
  Finding 3 and D5 from the regenerated JSON.
- **Scope blocked:** the §7 onset evidence row and D5's numeric justification,
  until regenerated. Does not block the WASAPI device choice or synthetic M3
  work.

### M1-audio-001-R01-F02 — Major — a dropped block corrupts the sample→time mapping with no gap recorded

- **Location:** `audio_io.py:747-760` (`ContinuousRecorder._callback`) and
  `audio_io.py:766-774` (`_drain`); test gap at
  `tests/test_audio_io.py:222-234`.
- **Requirement:** `goal.md` §6 ("Log the mapping back to original audio sample
  indices"), §13 ("clock/sample mapping and dropped-frame detection are
  verified"), `decisions.md` D3 ("Ignoring the gap makes every later sample
  index map to the wrong time, which would silently shift annotated speech
  boundaries").
- **Concrete failure.** `self.timeline.note_block(frames, …)` runs at line 750,
  **before** `self._queue.put_nowait(...)` at line 753. When the put raises
  `queue.Full` the callback increments `dropped_blocks`, raises
  `recording_queue_full` and returns — but the timeline has already counted
  those frames in `frames_written` and recorded **no** `TimelineGap`. The same
  happens for every block delivered after `_drain` returns on a write failure:
  `put_nowait` keeps succeeding until the queue reaches `max_queue_blocks`
  (512 blocks ≈ 5.1 s at a 10 ms blocksize), and all of those frames are
  counted yet never written, silently. Consequences:
  `integrity()["continuous"]` stays `True`; `frames_lost_estimate` stays `0`;
  and `timeline.sample_to_time(n)` for every sample after the drop point is
  late by `dropped_frames / 48000` s — the exact silent mis-annotation D3 claims
  to prevent. The author's own cited evidence already shows the inconsistency:
  in `test_a_write_failure_is_a_fault_and_what_survived_is_published`,
  `RecordingResult.frames` is 960 (2 blocks, from the writer thread) while the
  attached `integrity["frames_written"]` is 2400 (5 blocks, from the timeline)
  with `continuous: true`. Two different frame counts travel in one record and
  nothing reconciles or flags them. The existing queue-overrun test asserts
  only `dropped_blocks > 0` and the presence of the fault, so the suite cannot
  detect this.
- **Reproduction status:** **NOT_RUN** — demonstrating it needs a new test file
  under `09_nemotron`, which I may not write. The trace above is from source
  and from the two frame counts in the existing passing test.
- **Proposed fix.** On `queue.Full` (and when the writer has died) record a
  `TimelineGap(kind="writer_backlog", frames_lost=frames, method=ESTIMATED)`
  and roll the frames back out of `frames_written` — i.e. count only frames
  accepted for persistence — or invert the order so `note_block` is called after
  a successful enqueue with an explicit gap on failure. Additionally, assert in
  `finalize()` that `timeline.frames_written == self.frames_written` and raise a
  recorded fault when they differ, so no attempt can ever publish a file whose
  length contradicts its own timeline.
- **Verification.** A test that drops one mid-recording block and then asserts:
  published frame count excludes it; exactly one gap at the drop sample;
  `continuous is False`; and `sample_to_time(last_sample)` still equals the
  controller time of the last delivered block. Plus a `finalize()` test that
  the two frame counts always agree or a fault is raised.
- **Scope blocked:** the §13 "dropped-frame detection" and
  "flagged recoverable attempt on storage failure" rows cannot be read as
  covering the queue/writer-failure path until fixed.

### M1-audio-001-R01-F03 — Major — session-long player leaks prompt state across trials and `cancel_candidate` overloads `False`

- **Location:** `audio_io.py:890` and `1151` (`self._committed`, never cleared),
  `1011-1040` (`cancel_candidate`), `1070-1071`
  (`interrupted = clip_id is not None and self._committed … .committed`).
- **Requirement:** `goal.md` §6 ("`RECALL` has a one-use encouragement flag …
  Log every candidate and cancellation separately"; precedence table rows 5–6),
  §7 (record "Prompt scheduled, committed … Participant restart, overlap"),
  `decisions.md` D2 (the stream and player live for the whole session).
- **Concrete failure.** Because D2 keeps one `OutputPlayer` for the session but
  `_committed` is per-player and has no public reset:
  1. In any trial *after* a prompt has committed, a controller that calls
     `cancel_candidate("stop")`/`("completion")` with nothing armed — the normal
     teardown path for precedence rows 1–4 — takes the `cand is None` branch,
     finds the **previous trial's** `_committed`, and logs
     `prompt_cancel_too_late` with that stale candidate record (including its
     old `trial_id`). That is a fabricated post-commitment overlap deviation in
     a trial where no prompt was ever armed.
  2. `stop()` reports `interrupted_committed_prompt: True` whenever *any* prompt
     has ever committed and *any* clip is playing — including stopping a story
     or instruction clip in a later trial, and including a reference trial that
     by protocol never plays encouragement (`goal.md` §6).
  3. `cancel_candidate` returns `False` for three different situations —
     "nothing was ever armed" (no log at all), "already cancelled"
     (logged as `prompt_cancel_too_late` if the candidate object was cancelled
     directly, since `PromptCandidate.cancel` is public), and the genuine
     "too late, already committed" — while its own docstring tells the caller
     "A `False` return is the protocol's 'commitment consumed the allowance'
     case; the caller must log the overlap rather than retry." An M3 author
     following that docstring will log spurious overlaps. This is the
     comprehension half of the finding: two implementers would wire the return
     value differently, and the packet's invariant "after commitment the attempt
     is consumed and reported as such" is only true within one trial.
  The commit/cancel **race itself is correct** — `cancel_candidate` and
  `_maybe_commit` both run under `self._lock`, so the two outcomes are
  serialised and neither speaks when it should not nor loses the record that it
  spoke (packet question 2: yes, the boundary is where D1 says it is). The
  defect is the missing per-attempt scoping around it.
- **Proposed fix.** Add a public `begin_attempt(trial_id, attempt_id)` that
  clears `_committed`, `_finished` and any stale candidate and records the
  transition; make `cancel_candidate` return an explicit outcome
  (`removed` / `too_late` / `nothing_armed` / `already_cancelled`) instead of a
  bare bool, and only consult `_committed` for the current attempt; derive
  `interrupted_committed_prompt` from whether the clip being stopped *is* the
  committed prompt's clip (compare generation), not from history.
- **Verification.** A two-trial test: trial 1 arms and commits; trial 2 arms
  nothing, then calls `cancel_candidate("stop")` and `stop()` — assert no
  `prompt_cancel_too_late` record in trial 2 and
  `interrupted_committed_prompt is False` when a story clip is stopped; plus a
  reference-trial test asserting `committed_candidate is None` after
  `begin_attempt`.
- **Scope blocked:** the §6 "cancel before commit / consumed after commit"
  evidence row covers a single trial only.

### M1-audio-001-R01-F04 — Major — the gap detector's 2 ms tolerance is untestable on this PC's real timing and will manufacture gaps

- **Location:** `timing.py:243-298` (`CaptureTimeline.__init__`
  `gap_tolerance_s: float = 0.002`, `note_block`,
  `predicted_time_of_next_sample`), `audio_io.py:418-431`
  (`SoundDeviceBackend._timing`); test coverage at
  `tests/test_timing.py:163-167`.
- **Requirement:** `goal.md` §13 ("clock/sample mapping and dropped-frame
  detection are verified"), §7 ("device faults and dropped frames" recorded),
  `EGM_WORKFLOW.md` §5 M1 lens ("sample-to-time mapping"), `decisions.md` D3.
- **Concrete failure.** Two independent sources push the measured quantity past
  a 2 ms threshold without any audio actually being lost:
  1. **Jitter.** `first_frame_time` is computed as
     `perf_counter()` *at callback entry* plus `(adcTime − currentTime)`
     (line 426/429), so it inherits the full callback-entry jitter instead of
     being derived once from the device's smooth stream clock — which is what
     `StreamTimebase` was built to do but is never used for. The cadence
     actually measured on this PC, on the *output* side, is max interval
     **14.47 ms** (WASAPI, `audio_check_wasapi.json`), **30.77 ms** (MME,
     `audio_check_playback.json`) and **30.37/30.43/40.29 ms** across the survey,
     with MME and WDM-KS medians of 0.018 ms and 0.014 ms — i.e. callbacks
     arriving in bursts. Those are one to two orders of magnitude above a 2 ms
     tolerance.
  2. **Accumulated drift.** `predicted_time_of_next_sample` extrapolates from
     the segment start at the *nominal* 48 000 Hz. Any real device-clock offset
     therefore accumulates until it crosses 2 ms and fabricates a gap: at a
     modest 50 ppm that is every ~40 s, and over a 3-minute recall
     (`goal.md` §3) it is unavoidable. Each spurious gap appends a
     `frames_lost` estimate (~96+ frames), sets `continuous: False` and flags an
     otherwise clean attempt — and `goal.md` §6 leaves "whether such a trial is
     analysable" to the research director, so false positives have protocol cost.
  The only jitter evidence in the suite is `test_small_jitter_is_not_a_gap` with
  **0.5 ms**; nothing between 2 ms and the observed 15–40 ms is exercised, and
  no drift case exists at all. Because capture is BLOCKED on this PC
  (`default_input_device: -1`), the mechanism has **never run against hardware**;
  `audio_spike.md` correctly lists "Device drift over a full session" as
  NOT_RUN, but the 2 ms constant it depends on is presented as working.
- **Proposed fix.** Derive the block's controller time by mapping PortAudio's
  stream clock into controller time through `StreamTimebase` (anchor once,
  re-anchor with filtering) rather than per-callback `perf_counter`; make the
  gap criterion count-based (expected device frame counter vs frames delivered,
  which PortAudio's stream time supports) instead of time-threshold-based; and
  if a time threshold is kept, set it from the measured callback jitter
  (e.g. ≥ 2 × observed max interval) and predict against
  `timebase.effective_rate()` so drift is absorbed rather than reported as loss.
  Report accumulated drift separately as `drift_ppm` (already available) instead
  of as lost frames.
- **Verification.** A jitter series (±1 block of jitter, zero true loss ⇒ zero
  gaps), a drift test (true rate 48 048 Hz for 180 s ⇒ zero gaps, non-null
  `drift_ppm`), and a true-loss test (one block omitted ⇒ exactly one gap with
  the right `file_sample`); then one real `--duplex --allow-microphone` capture
  reporting `gaps` and `drift_ppm` once a suitable input device exists.
- **Scope blocked:** dropped-frame detection must be treated as unvalidated for
  hardware; it does not block synthetic M3 development.

### M1-audio-001-R01-F05 — Major — dependencies are not pinned, though M1 requires pinning and the packet claims they are

- **Location:** `requirements.txt` (`numpy>=1.24,<3`,
  `sounddevice>=0.4.6,<0.6`); packet "Files created" table ("pinned
  dependencies with the measured environment").
- **Requirement:** `goal.md` §1 M1 ("select and **pin** audio dependencies"),
  §12 M1 exit evidence ("Select/pin audio/VAD dependencies"), §5 ("choose and
  pin compatible versions after the spike"), §2 ("Versions … must be verified
  and pinned when installed").
- **Concrete failure.** The file specifies **ranges**; the measured versions
  (numpy 2.3.5, sounddevice 0.5.5) appear only in a header comment, so
  `pip install -r requirements.txt` on another day does not reproduce the
  environment the timing evidence was produced in. For a checkpoint whose whole
  output is timing numbers from PortAudio, the runtime that produced them is
  part of the result. The packet's description of the file as "pinned" is
  therefore not accurate, and a named M1 exit criterion is unmet.
- **Proposed fix.** `numpy==2.3.5`, `sounddevice==0.5.5`; record the PortAudio
  build string (`V19.7.0-devel`) that `inventory()` already reports; keep the
  compatible-range note as a comment; state explicitly that `onnxruntime` is
  deliberately deferred to M3 (as the file already does).
- **Verification.** `pip install -r requirements.txt` (or `--dry-run`) resolves
  to exactly the recorded versions; re-run the 80-test suite and
  `tools/check_audio.py` on the pinned set and re-record the environment block.

### M1-audio-001-R01-F06 — Major — the silence origin ignores hysteresis-band speech, and nothing bounds how stale a deadline may be

- **Location:** `timing.py:584-629` (`SpeechSegmenter.push`, specifically the
  in-speech branch at 606-612 where `_last_speech_frame` is updated only for
  `p >= speech_threshold`), `timing.py:684-700` (`PauseTimer.deadline`,
  `known_at`, `eligible`), `timing.py:459-483`
  (`validate_detector_profile`).
- **Requirement:** `goal.md` §6 ("Define silence onset from the end of the most
  recent detected participant speech frame … Do not add the configured waiting
  interval twice"), §3 (the manipulation *is* the 0.5/1.0/2.0 s threshold),
  `decisions.md` D4.
- **Concrete ambiguity and failure.** A frame whose probability sits in the
  hysteresis band (`exit_threshold ≤ p < speech_threshold`) keeps `in_speech`
  true and resets the hangover counter, but does **not** update
  `_last_speech_frame`. So a participant who trails off at band level for Δ
  seconds and then goes quiet produces an offset Δ seconds in the past, a
  deadline Δ seconds in the past, and — since `eligible(now)` is a bare
  `now >= deadline` with no staleness bound — a prompt that commits after only
  `hangover` (150 ms) of *real* silence, whatever the assigned condition. At the
  2.0 s condition that collapses the manipulation to ~0.15 s. `goal.md` §6 does
  not say whether a band frame is "a detected participant speech frame", and two
  implementers would code it differently; the code's own rule is stated only in
  a docstring ("the end of the last frame above the speech threshold") and is
  not recorded in `decisions.md` or as part of the detector profile.
  `validate_detector_profile` guards only `hangover + decision_budget <
  shortest threshold`, which assumes — as D4's "Consequence" paragraph states
  outright — that the deadline can be stale by *at most* the hangover. The band
  path (and equally a detector stall that stops pushing frames) breaks that
  assumption without any check. This is a defect independent of the research
  values: the missing piece is a bound.
- **Proposed fix.** (a) Decide and record which frames define the silence
  origin — either update `_last_speech_frame` on any frame `>= exit_threshold`
  (making "detected speech" and "keeps the run open" the same set), or keep the
  current rule explicitly; add it to `DetectorProfile.as_record()` so it is part
  of the frozen manipulation. (b) Add a configured
  `max_deadline_staleness_s`: when `now − deadline` exceeds it at evaluation
  time, record a flagged deviation (and, per the research decision, either
  suppress the prompt or commit and mark it) instead of firing silently.
- **Verification.** Segmenter tests driving a 2 s band-level tail at each of
  0.5/1.0/2.0 s and asserting the documented offset; a `PauseTimer` test that a
  deadline older than the bound is reported as stale rather than simply
  eligible; and an `OutputPlayer` test that a stale-deadline candidate takes the
  flagged path.
- **Gate note:** the *values* (frame size, thresholds, hangover) are
  research-owned (`goal.md` §14, "detector profile values"); the *rule* and the
  staleness bound are engineering decisions that must be written down before
  that gate can be closed, so this blocks the detector-profile freeze rather
  than synthetic M3 work.

### M1-audio-001-R01-F07 — Minor — evidence traceability: one command missing, two figures cited to the wrong source

- **Location:** `validation/audio_spike.md` "Reproduce with" block and
  Finding 3 note 3; `decisions.md` D5; `tools/check_audio.py:504-545`
  (the report dict records no `argv`).
- **Requirement:** `EGM_WORKFLOW.md` §6 ("Evidence files with command, working
  directory, tool/dependency versions, exit result, brief output and
  limitations"); `AGENTS.md` ("Keep evidence with commands, results,
  environment and file identity").
- **Concrete failure.** (i) `validation/audio_check_playback.json` is in the
  packet manifest, but the command that produced it — a `--playback` run on the
  **default** device (its `playback_stream` check reports 180.0 ms, i.e. MME) —
  is absent from the spike's reproduce list, which only has
  `--playback --device 8`. Since the JSON stores no `argv` or device index, the
  command→file mapping exists only in prose, and for this file not even there.
  (ii) D5 cites "a 14.5 ms worst callback interval" to
  `validation/audio_spike.md`, but that document's Finding 2 table says
  **12.08 ms** for WASAPI; 14.47 ms comes from `audio_check_wasapi.json`'s
  `callback_cadence` — a different run with a different method (one 193-callback
  tone playback vs a 1 s silent survey). (iii) D5's "the estimated onset was
  189 ms" / "On WASAPI the same check estimated 10.4 ms" are the single-shot
  figures that the spike's own note 3 says "must not be quoted as the result",
  and the 40-trial figures are not quoted at all (see F01 for why the spike's
  reasoning about those two numbers is itself wrong).
- **Proposed fix.** Record `argv`, resolved device index and host API inside the
  JSON report; add the missing command line; make every numeric claim in
  `decisions.md` and `audio_spike.md` cite `<file>` + `<check name>`.
- **Verification.** Each figure in both documents resolves to a named check in a
  named JSON file; a reader can regenerate every file from the listed commands.

### M1-audio-001-R01-F08 — Minor — a report containing NOT_RUN/BLOCKED checks is stamped `"verdict": "PASS"`

- **Location:** `tools/check_audio.py:538-539`
  (`report["verdict"] = FAIL if counts.get(FAIL) else PASS`).
- **Requirement:** `EGM_WORKFLOW.md` §6 ("Mark each check `PASS`, `FAIL`,
  `NOT_RUN` or `BLOCKED`; **missing evidence is not PASS**").
- **Concrete failure.** All five committed reports carry two `NOT_RUN` checks
  and a top-level `"verdict": "PASS"` (or `FAIL`, for the default-device commit
  run). My own permitted no-flag run produced `summary: NOT_RUN=2, PASS=8` with
  exit 0. Worse, `--duplex --allow-microphone` on this PC yields
  `duplex_capture: BLOCKED` and still a `PASS` verdict — the one case where the
  machine-readable field would most mislead. The human-readable records are
  honest; the field a future gate or script would read is not.
- **Proposed fix.** Make the verdict `FAIL` > `BLOCKED`/`INCOMPLETE` >
  `PASS`, and include `not_run` / `blocked` counts in the verdict line and the
  printed summary.
- **Verification.** No-flag run reports an incomplete verdict naming its two
  NOT_RUN items; a simulated BLOCKED check does not yield PASS.

### M1-audio-001-R01-F09 — Minor — `capture_available` conflates "a default input exists" with "capture is possible"

- **Location:** `audio_io.py:160-181` (`inventory`, `capture_available=bool(inputs)
  and default_in is not None and default_in >= 0`);
  `validation/audio_spike.md` Finding 1 heading; `tools/check_audio.py:461-467`
  (`duplex_check` gates on `capture_available`).
- **Requirement:** `goal.md` §6 start-of-trial step 1 ("Validate … device
  identities"), §12 ("Configuration must record … versioned device IDs").
- **Concrete failure.** This PC *does* expose two input endpoints — indices 13
  and 15, Bluetooth hands-free on WDM-KS, confirmed in the inventory of every
  evidence JSON — yet `capture_available` is `False` because the *default* is
  −1. So (a) the spike's heading "this PC has no input device" overstates its
  own body (which correctly says two unsuitable BT endpoints exist), (b)
  `--duplex` reports BLOCKED without ever attempting a device that exists, and
  there is no flag to name an input device, and (c) once M3 pins an input device
  by `DeviceIdentity.key()` — the design the module itself argues for — a
  `False` `capture_available` would wrongly refuse to start a session on a
  correctly configured machine.
- **Proposed fix.** Report `default_capture_available` and
  `capture_devices` separately; add a `device_for_key()` resolver and an
  `--input-device` flag; reword Finding 1 to "no *default* input device; the
  only inputs are two Bluetooth hands-free endpoints, unsuitable as a research
  microphone" (the argument is already made in the body and I agree with it —
  no coverage is actually lost).
- **Verification.** No-flag run prints both flags; a test that a pinned
  `DeviceIdentity.key()` present in the inventory passes start-of-trial
  validation while a missing one fails with a named fault.

### M1-audio-001-R01-F10 — Minor — nothing ties the armed deadline to the one place that computes it

- **Location:** `audio_io.py:989-1009` (`OutputPlayer.arm` accepts any
  `PromptCandidate.deadline`), `timing.py:635-700` (`PromptCandidate`
  constructor takes a free-form `deadline`; `PauseTimer.known_at()` returns
  `max(deadline, confirmed_at)`).
- **Requirement:** packet invariant "The configured waiting interval is added
  exactly once … computed in exactly one place"; `goal.md` §6; `decisions.md` D4.
- **Concrete ambiguity.** Inside `timing.py` the arithmetic is correct and
  single-sourced, and I found **no path in this checkpoint** by which the
  interval is added twice (packet question 1: the deadline arithmetic is right,
  and `_maybe_commit` compares against `cand.deadline` without adding anything).
  But the invariant is enforced by convention precisely at the seam M3 must
  write: `PromptCandidate(deadline=…)` is hand-assembled by the caller, and
  `known_at()` sits right next to `deadline` as an inviting but wrong value to
  arm with. An M3 author who writes `confirmed_time + threshold` gets a
  double-charged interval with no check anywhere, which is the one mistake
  `goal.md` §6 names explicitly.
- **Proposed fix.** A `PauseTimer.candidate(trial_id, index)` factory that
  stamps `deadline`, `silence_since` and `threshold_s` together (carry
  `silence_since` on `PromptCandidate`), plus an assertion in `arm()` that
  `abs(deadline − (silence_since + threshold_s)) < 1e-9`.
- **Verification.** A test that arming a hand-assembled deadline not equal to
  offset + threshold raises, and that `known_at()` cannot be used as a deadline.

### M1-audio-001-R01-F11 — Minor — the audio-thread contract is documented for `guard` only

- **Location:** `audio_io.py:731-746` and `943-957` (`_fault` calls the
  controller's `on_fault` from inside the audio callback),
  `audio_io.py:1080-1117` (`OutputPlayer._callback` holds `_lock` across the
  whole callback and calls `TimingLedger.record`), `decisions.md` D7.
- **Requirement:** `goal.md` §6 ("Any unexpected recording, playback, clock,
  device or disk failure stops prompt output"), §7 (bounded output delay);
  D7's constraint on M3.
- **Concrete failure.** D7 states the non-blocking rule for `guard` only, so an
  M3 author will reasonably write an `on_fault` handler that takes the
  controller lock, writes JSONL or enqueues to a bounded queue — and it will run
  **on the audio thread**, inside `OutputPlayer._lock`, at exactly the moment a
  device is already misbehaving, producing underruns during the prompt.
  Relatedly, `TimingLedger.records` is an unbounded in-memory list appended to
  from the audio callback.
- **Proposed fix.** State the thread and latency contract for `on_fault` (and
  for ledger writes from the audio path) in D7 and the module docstring, or
  deliver faults through a queue drained by the controller thread, keeping the
  callback to a counter increment.
- **Verification.** A test that a deliberately slow `on_fault` does not extend
  callback work (or that faults are queued and drained off-thread).

### M1-audio-001-R01-F12 — Minor — a `.partial` recording is detectable but not readable, and the rename is not durable

- **Location:** `audio_io.py:616-642` (`WaveSink`, which relies on `wave`
  patching the RIFF/data sizes in `close()`), `audio_io.py:806-820`
  (`finalize` → `os.replace` with no `flush`/`fsync` of file or directory).
- **Requirement:** `goal.md` §10 ("Write incrementally and finalize atomically
  where appropriate. Detect incomplete attempts after crashes; never silently
  mark them complete"), §6 ("finalizes what is recoverable");
  `decisions.md` D6; packet question 3.
- **Concrete failure.** Publish-by-rename *is* crash-safe **for the claim the
  packet makes** — an attempt that never finalised stays detectable, and
  `start()` refuses to record over an existing `.partial`, which
  `test_refuses_to_start_over_an_unfinalized_attempt` confirms. The gap is the
  next step: `wave` writes the header with `nframes = 0` and patches it only on
  `close()`, so after a process crash the surviving `<name>.wav.partial` reports
  zero frames to any standard reader and the captured bytes cannot be recovered
  without a header-repair step that does not exist anywhere in this checkpoint.
  There is also no `fsync` of the file or the containing directory before
  `os.replace`, so durability under power loss is asserted rather than
  established.
- **Proposed fix.** Patch the header periodically from the writer thread (or
  write a raw PCM sidecar plus a small JSON descriptor); `flush` + `os.fsync`
  the file before `os.replace` and fsync the directory after; add a
  `.partial` recovery routine to the M3 `storage.py` scope and name it in D6.
- **Verification.** Kill the process mid-recording, then recover readable audio
  of the expected length from the `.partial` file and confirm the attempt is
  reported incomplete, not complete.

## Open research decisions / evidence gaps

Listed separately from the defects above. None of these is a code defect, and
per `EGM_WORKFLOW.md` §8 a research-owned gate may be deferred without blocking
synthetic development.

1. **M1's avatar-clock adapter demonstration is absent** (evidence gap, gate:
   **M1**). `goal.md` §7 says "Bring a minimal renderer/asset snapshot into M1
   to test this adapter", §12 lists "avatar clock adapter feasibility" as M1
   exit evidence, and the §5 M1 lens asks for an "adapter demonstration" and
   "Does the avatar use `playTrack` without duplicate audio?". This checkpoint
   contains no browser code, no renderer snapshot and no `asset-provenance.json`;
   `PlaybackPosition`, `interpolate` and `OutputPlayer.position()` are a
   Python-side design for the contract, tested only against themselves. The
   packet declares this honestly and `audio_spike.md` marks it NOT_RUN. I
   verified the contract it targets is real (`tanuki-lipsync.js:202` auto-finishes
   only when no external `getTime` is supplied, so the adapter genuinely must
   call `stop()` itself). Consequence: **M1 as specified is not complete**, even
   though the narrower question this packet asks can be answered.
2. **Acoustic onset, last-speech-to-audible-response, detector boundary error,
   echo/leakage, low-volume speech, load behaviour, device drift, completion
   suppression at 0.5 s** — all correctly NOT_RUN/BLOCKED (gates: **M1
   hardware / M3 / M6**). The input-device gap is the root cause for most of
   them and is a hardware/research decision (`goal.md` §14 "device models,
   measured timing tolerance and calibration method"). Note that F01 makes the
   gap wider than recorded: no *reliable* onset estimate exists either, only a
   nominal one-block device figure.
3. **Recall-cap origin, completion procedure, event precedence, rearming,
   early-speech and overlap policies** (gate: **material freeze / participant
   deployment**, owner research director per `goal.md` §14). D1, D4 and D7
   implement proposed interpretations and say so. I found nothing here that
   *presupposes* a settled answer (packet question 5): the guard callable in D7
   keeps precedence in the controller, `reset_for_rearm` implements the proposed
   rule without hard-coding it, and reference-trial suppression is left to M3.
   The one addition needed is F06's written rule for the silence origin, which
   must exist before the detector profile can be frozen.
4. **The 100 ms p95 onset target** is a proposal, labelled as such in the code,
   the tool (`meets_candidate_onset_target` … "a proposal, not a
   research-approved tolerance") and the spike. The tolerance freeze remains
   open (gate: **M6 / participant deployment**).
5. **Packet integrity:** `DEVELOPMENT_STATUS.md`, `README.md` and
   `reviews/INDEX.md` were modified after the packet was frozen and carry no
   digest. They are outside my scope and I did not open them, but a packet that
   claims "target edits are paused" should either cover them or say they are
   excluded.

## Verdict

**NEEDS_FIXES**

**Scope this covers.** The focused-route question — is this timing/device layer
sound enough to build the M3 controller on, and is the recorded evidence
described accurately? — against the exact snapshot whose 14 digests I
re-verified. The architecture answers well: the commit-inside-the-callback
boundary makes an early trigger structurally impossible rather than a matter of
timer accuracy (verified in code and by `no_early_commitment: 0 of 40` on real
hardware); the cancel/commit race is properly serialised under one lock and
cannot either speak when it should not or lose the record that it spoke; the
threshold is added exactly once in exactly one place; `Estimate` makes
"measured" unreachable from this code, which I confirmed by inspection; and the
80-test suite genuinely runs and genuinely tests observable boundaries rather
than restating the implementation. I would build M3 on this shape.

It does not pass as-is because, per `EGM_WORKFLOW.md` §8, unresolved Major
findings remain in the reviewed scope: the headline onset evidence is wrong by a
50 ms artefact and its recorded explanation is wrong in two places (F01); a
dropped block silently corrupts the sample→time mapping that D3 exists to
protect (F02); the session-long player fabricates cross-trial overlap deviations
and overloads its cancellation result (F03); the gap detector's 2 ms tolerance
is contradicted by this PC's own measured callback cadence and by ordinary clock
drift, and has never run against hardware (F04); dependencies are not pinned
although M1 requires it and the packet says they are (F05); and the silence
origin's treatment of hysteresis-band speech is both unspecified and unbounded
(F06). F01, F05 and F07 are documentation-level and cheap; F02, F03 and F06 are
contained code changes; F04 is the one that needs real design work.

**What this verdict does not cover.** No participant-use approval and no
universal safety guarantee is available from this review, and none is implied.
It is not acoustic validation — every onset figure in this checkpoint is a
device-latency estimate, and after F01 a poor one. It is not hardware
validation of capture: this PC has no usable input device, so every
microphone-side claim rests on the fake backend. It does not cover the
experiment state machine, Silero VAD, stimulus manifests, the server and its
access control, the browser adapter or renderer, transcription/scoring, or
anything concerning Nemotron. It does not certify M1 complete: the avatar
clock-adapter demonstration that `goal.md` §7 and §12 place in M1 does not
exist yet. And it applies only to the snapshot digested above — any edit
requires fresh review of the changed scope.
