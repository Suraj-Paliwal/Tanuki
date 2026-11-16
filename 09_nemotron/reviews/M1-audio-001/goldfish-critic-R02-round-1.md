# Goldfish review — M1-audio-001 / critic / R02 / round 1

## Provenance and scope

- **Fresh context: yes.** Dispatched as a separate agent session with no
  development-chat history; my inputs were the packet, the documents it names,
  the files in its manifest and their local dependencies. I did not see or seek
  any other reviewer's report, and no `goldfish-focused-R01-*.md` existed in the
  checkpoint directory while I worked.
- **Snapshot: unchanged.** I recomputed SHA-256 for all 14 manifest entries
  before and after running the permitted checks; every digest matches the packet
  table exactly (`timing.py` `d763a690…`, `audio_io.py` `5b674c24…`,
  `tools/check_audio.py` `e3025915…`, `requirements.txt` `5b95c1de…`,
  `decisions.md` `54b0fa7c…`, `.gitignore` `60945863…`,
  `tests/test_timing.py` `1c05c5a5…`, `tests/test_audio_io.py` `c531217a…`,
  `validation/audio_spike.md` `ce100336…`, and the five
  `validation/audio_check_*.json` files). Base commit `eeb0f0e` confirmed; as
  the packet states, it captures none of the reviewed content.
  - One deviation from the packet's description, content-neutral: the packet
    says every reviewed file is untracked (`??`). During my review the index
    changed — `git status --porcelain` now shows the manifest files as staged
    (`A `), plus `M 09_nemotron/DEVELOPMENT_STATUS.md`, `M 09_nemotron/README.md`
    and `M 09_nemotron/reviews/INDEX.md`. The reviewed **file contents** are
    byte-identical to the manifest, so no coverage is stale; but
    `DEVELOPMENT_STATUS.md` and `README.md` were modified inside the review
    window and are not in the manifest, so nothing I say covers their claims.
    (I note that `DEVELOPMENT_STATUS.md` now repeats the "~70 ms / ~233 ms"
    figures that finding F01 below shows to be mis-attributed.)
- **Stage/lenses:** critic. Lenses: timing and state-machine correctness;
  concurrency and cancellation races; recording/storage integrity; evidence
  honesty (estimated vs measured). From `EGM_WORKFLOW.md` §5: "Audio
  feasibility, M1" and "Recording/storage, M3/M6".
- **Named readiness question** (packet §"Identity and requested review"): is
  this timing/device layer sound enough to build the M3 experiment controller
  on, and is the recorded evidence described accurately? Explicitly not asked:
  participant readiness, acoustic validation, approval of any research decision.
- **Files inspected in full:** `reviews/M1-audio-001/packet.md`,
  `EGM_WORKFLOW.md`, `reviewers/GOLDFISH.md`, `AGENTS.md`, `timing.py` (875
  lines), `audio_io.py` (1193 lines), `decisions.md`, `requirements.txt`,
  `.gitignore`, `validation/audio_spike.md`, all five
  `validation/audio_check_*.json`, `goal.md` §§1, 4, 5, 6, 7, 8, 10, 11, 12, 13,
  14. Inspected in relevant part: `tools/check_audio.py` (`synthetic_checks`,
  `playback_check`, `commit_distribution`, `main`), `tests/test_timing.py` and
  `tests/test_audio_io.py` (full test inventory; recorder, output-player and
  segmenter cases read line by line), and the read-only baseline
  `../08_avisspeech/src/tanuki-lipsync.js` at the cited lines (`playTrack` 294,
  track branch 197-204, `stop` 459 — all three citations are accurate, and the
  `!this._getTime` condition at line 203 does confirm that an external-clock
  track never self-finishes).
- **Referenced sources unavailable:** none. Everything the packet cites exists
  and is readable.
- **Tools/tests actually executed** (scratch: `/tmp/gf-R02/pycache`, i.e. the
  system temp directory; `PYTHONPYCACHEPREFIX` set there; nothing written inside
  `09_nemotron` except this report):
  - `python -m unittest discover -s tests -p "test_*.py"` from
    `C:/Users/suraj/Downloads/Tanuki/09_nemotron` → **80 tests, OK, 0.267 s.**
    The packet's "80 tests OK" claim is reproduced. I read both test files
    before running them; they open no device and write only under `tempfile`.
  - `python tools/check_audio.py` (no flags) → `capture_available=False`,
    `playback_available=True`, 8 PASS + 2 NOT_RUN, exit 0. Reproduces the
    packet's inventory row and the "no default input device" warning. I read
    `main()` first and confirmed that without flags it calls only `inventory()`
    (queries devices, opens no stream) and `synthetic_checks()` (fake backend,
    `tempfile`), and writes no file without `--out`.
- **Explicit NOT_RUN by me:** `--playback`, `--survey`, `--commit-trials`,
  `--duplex` (prohibited by the packet; I did not run them and do not
  re-derive their numbers by execution). I also did **not** execute any
  reproduction script of my own, because the packet permits exactly two
  commands. Every finding below marked "static trace" is derived by reading the
  code and the author's own recorded JSON output, with the arithmetic shown so
  the Elephant can confirm or refute it in one run. Nothing here rests on a
  guessed execution result.

## My understanding

The protocol's independent variable is a silence threshold: after the
participant stops speaking for the assigned interval, the controller may play
one short fixed encouragement clip, once per recall trial, and only after the
participant has actually spoken. This checkpoint builds the layer underneath
that decision — nothing of the experiment state machine itself. `timing.py`
keeps all protocol time on a monotonic controller clock plus device sample
positions: a `CaptureTimeline` maps written-file sample indices back to
controller time piecewise, so that frames the device failed to deliver become
recorded, flagged gaps instead of invented silence; a `SpeechSegmenter` turns
per-frame detector probabilities into onset/offset boundaries dated where they
happened, with the detector's confirmation delay carried separately; and a
single `PauseTimer` computes the eligibility deadline as *last speech offset +
configured threshold*, so the hangover is never charged twice. `audio_io.py`
owns the devices: one continuous microphone file per attempt, written by a
separate thread and published by rename so an attempt that never finalised is
detectable, and one session-long output stream that plays silence when idle.
Story and instruction clips start immediately; the encouragement is *armed*
against its deadline and is handed to the device only inside the audio callback
that first sees `now >= deadline` and whose controller-supplied guard still
permits it — making "never early" a structural property rather than a matter of
timer accuracy, at the price of always being late by the device latency. Every
time value derived from a device latency report is tagged `estimated`; the code
has no path that produces `measured`, because an acoustic measurement needs a
reference channel this PC cannot provide (it has no input device at all). The
claim under review is bench feasibility plus honest evidence, not acoustic
validation and not any research decision.

## Findings

Six Major, seven Minor. No Blocker: the architecture is the right shape for M3,
the commit-boundary design (D1) is sound, and none of the defects below changes
the checkpoint's engineering conclusions — but F01 mis-attributes the headline
timing evidence, and F02-F06 sit directly on the recording-integrity and
consumed-allowance contracts M3 would be built on.

What I traced and found **sound**, so the Elephant knows this is not an
unexamined pass: no interleaving produces audio before the deadline (the
deadline is tested against `timing.entry_time` while the samples become audible
at `timing.first_frame_time = entry + output latency`, so the audible onset is
necessarily later than the deadline — `audio_io.py:1139-1147`); the configured
interval is added exactly once and only to `event_time`, never to
`confirmed_time` (`timing.py:688-691`, `known_at()` is report-only); `arm()`,
`play()`, `cancel_candidate()`, `stop()`, `position()` and `_maybe_commit()` all
mutate the player under one `RLock`, so a cancel cannot interleave *inside* a
commit; a guard veto and a guard exception both stay silent
(`audio_io.py:1130-1143`); no code path can construct an `Estimate` with
`method="measured"` (the constant is only exported and tested); `os.replace` in
`finalize()` is genuinely atomic and `start()` refuses to record over an
existing `.partial`; and `load_clip` refuses a hash or rate mismatch rather
than adapting. The packet's "80 tests OK" and device-inventory rows reproduce
exactly.

---

### M1-audio-001-R02-F01 — Major — the reported "estimated onset delay" is inflated by a fixed 50 ms probe artifact, and the spike's explanation of the latency discrepancy is wrong

- **Location.** `tools/check_audio.py:391` (`clip = silence_clip(clip_s, …)`)
  and `:410`; `audio_io.py:1144-1149` (`seconds=timing.first_frame_time +
  clip.leading_silence_s`); `audio_io.py:257` (`_leading_silence_s` returns the
  *whole duration* when no block exceeds the −45 dB floor);
  `validation/audio_spike.md` Finding 3 (table + note 2); `decisions.md` D5;
  packet "Acceptance checks" rows "§7 playback delay after the deadline" and
  "§7 same, default device"; `validation/audio_check_commit_wasapi.json` and
  `audio_check_commit_default.json`.
- **Requirement.** `goal.md` §7: "Audible onset measurement or calibrated
  estimate, **its method and uncertainty**… Report all observations and maxima";
  `EGM_WORKFLOW.md` §5, M1: "Is acoustic onset measured or estimated?";
  `AGENTS.md`: "Do not turn … timer timestamps into acoustic measurements."
  The packet's invariant "a scheduling timestamp is never presented as an
  acoustic measurement" **holds**; what fails is the accuracy and attribution of
  the estimate itself.
- **Evidence (static trace over the author's own JSON).** The commit probe is
  `silence_clip(0.05)`. Because every 5 ms block of an all-zero clip is below
  the floor, `_leading_silence_s` returns `mono.size / samplerate` = **0.050 s**,
  and the onset estimate adds that to the block time. In
  `audio_check_commit_wasapi.json` the onset figures exceed the commit figures
  by **exactly 60.0000 ms at the median (5.9409 → 65.9409), at p95 (10.1303 →
  70.1303) and at the max (10.8046 → 70.8046)**; in
  `audio_check_commit_default.json` by 220.15-220.18 ms throughout. A difference
  constant to four decimal places across 40 trials is not a device observation.
  It decomposes as 50 ms of probe-clip "leading silence" plus a constant
  per-block DAC offset — and the single-shot `--playback` run, which used
  `tone_clip` (leading silence 0.0), pins that offset: commit 0.3682 ms → onset
  10.3682 ms, i.e. exactly **10.00 ms = one 480-frame block at 48 kHz**
  (`audio_check_wasapi.json`), and 18.41 → 189.45 ms, i.e. ~170.2 ms, on MME
  (`audio_check_playback.json`).
- **Concrete consequences.**
  1. `audio_spike.md` Finding 3 note 2 — "the steady-state per-block DAC offset
     implies about 60 ms" — is wrong; it is ~10 ms on WASAPI. The two latency
     reports (22.0 ms `stream.latency` vs ~10 ms per-block) differ by ~12 ms,
     as `decisions.md` D5 correctly says — so the spike and D5 state mutually
     inconsistent figures for the same quantity.
  2. The stated justification is therefore backwards: the spike says the ~70 ms
     p95 "uses the per-block figure, which is the larger and therefore the
     safer of the two for planning". Once the 50 ms artifact is removed, the
     per-block figure is the *smaller* of the two, so the reported number is not
     conservative with respect to the other available estimate — it is a
     different quantity inflated by a clip property.
  3. The `estimated_onset_delay_distribution` check adds no device information
     beyond `commit_delay_distribution`: it is the same distribution shifted by
     a constant. Presenting it as a second measured spread overstates the
     evidence.
  4. Conversely, `decisions.md` D5 quotes "the estimated onset was 189 ms"
     (default) and "On WASAPI the same check estimated 10.4 ms" — the two
     single-shot figures that `audio_spike.md` Finding 3 note 3 explicitly says
     "must not be quoted as the result". The decision record quotes the
     retracted numbers; the spike quotes the inflated ones. Neither states the
     corrected pair.
  5. Corrected values: WASAPI estimated onset p95 ≈ **20.1 ms** (10.13 commit +
     10.0 device), default MME ≈ **182.8 ms**. **No conclusion flips** —
     WASAPI still clears the 100 ms candidate target, the default device still
     fails it, and D5's choice of WASAPI stands. That is why this is Major and
     not Blocker; but the number that will be carried into the acoustic
     calibration M6 depends on it, and the calibration is supposed to resolve
     exactly the discrepancy that is here explained incorrectly.
- **Proposed correction.** (a) Probe with a clip that has a real acoustic onset
  (`tone_clip(…, lead_silence=L)` with a known `L`), or report
  `commit_delay_ms`, `device_offset_ms` and `clip_leading_silence_ms` as three
  separate fields that are summed explicitly, so no single number mixes a clip
  property with a device property. (b) Make `Clip`/`_leading_silence_s` report
  "no onset detected" (e.g. `leading_silence_s=None`) instead of the full
  duration, and make `_maybe_commit` refuse to synthesise an audible-onset
  estimate for a clip with no detectable onset. (c) Correct
  `audio_spike.md` Finding 3 note 2, `decisions.md` D5, the packet acceptance
  table and `DEVELOPMENT_STATUS.md` to the recomputed figures, keeping the
  original numbers visible as superseded.
- **Verification.** Re-run `--commit-trials 40 --device 8` with a tone probe and
  assert `onset_delay − commit_delay` ≈ one block ± jitter rather than a
  constant 60 ms; add unit tests that (i) `silence_clip(0.05)` does not report
  0.05 s of *leading* silence, and (ii) for a clip with lead `L` the onset
  estimate equals `block_time + L` exactly.
- **Scope blocked.** The M1 evidence narrative, and the baseline that M6's
  acoustic calibration will be compared against.

### M1-audio-001-R02-F02 — Major — when audio is actually lost (queue full, or writer thread dead) the capture timeline still counts those frames as written: `continuous: true` and a silently wrong sample→time mapping

- **Location.** `audio_io.py:748-764` (`_callback`: `note_block` at 750 runs
  *before* `put_nowait` at 753; `queue.Full` → `dropped_blocks += 1`, fault,
  `return`); `audio_io.py:766-779` (`_drain` returns and the thread dies on the
  first write exception); `timing.py:291-298` and `:370`
  (`"continuous": not self.gaps`).
- **Requirement.** `goal.md` §13 "Full participant audio survives encouragement
  overlap; clock/sample mapping and dropped-frame detection are verified"; §6
  "Log the mapping back to original audio sample indices"; packet invariant
  "The recording keeps exactly the frames the device delivered; sample indices
  map back to controller time across a gap"; `decisions.md` D3 ("Ignoring the
  gap makes every later sample index map to the wrong time, which would
  silently shift annotated speech boundaries" — exactly what happens here).
- **Evidence and failure case (static trace).** `note_block` has already done
  `self.frames_written += frames`, `self.device_frames += frames` and anchored
  the timebase by the time the enqueue fails, and the `queue.Full` branch
  returns without telling the timeline anything. So for every block lost to
  writer backlog: the WAV is short by `frames`, `timeline.frames_written`
  counts them as present, **no `TimelineGap` is created**, `gaps` stays empty,
  `integrity()["continuous"]` stays `true`, `frames_lost_estimate` stays `0`,
  and `sample_to_time(i)` for every subsequent `i` returns a time earlier than
  the truth by `dropped_frames / rate`. The same divergence occurs after
  `recording_write_failed`: `_drain` exits, later blocks enqueue successfully
  and are never written, and the timeline keeps counting them.
  The suite does not catch this: `test_a_queue_overrun_is_reported_as_a_fault_
  not_a_silent_short_file` (tests/test_audio_io.py:222-234) asserts only
  `dropped_blocks > 0` and the fault kind, and
  `test_a_write_failure_is_a_fault_and_what_survived_is_published` (:198-220)
  asserts `result.frames == 2*BLOCK` — neither asserts `continuous is False`,
  compares `integrity["frames_written"]` with `result.frames`, or checks the
  mapping after the loss. The gap machinery that D3 is built around covers the
  case where the *device* dropped frames and not the case where the *recorder*
  did.
- **Proposed correction.** Tell the timeline when a block did not reach the
  file: add `CaptureTimeline.note_not_persisted(frames, at, kind=…)` that
  appends a `TimelineGap` and opens a new segment with `file_start` unchanged
  (i.e. subtract the frames from `frames_written`), or move `note_block` to
  after a successful enqueue and record a gap on failure. Then add
  `frames_persisted` to `integrity()` and make `continuous` false whenever
  `frames_written != frames_persisted`, so a consumer cannot read a lossy
  attempt as continuous.
- **Verification.** Extend both existing tests to assert
  `integrity["continuous"] is False`, a gap whose `frames_lost` equals the
  dropped frames, and `sample_to_time(last_sample)` equal to the real controller
  time within one block; add a case where the loss happens mid-recording and
  the mapping on both sides is checked, mirroring
  `test_mapping_stays_correct_on_both_sides_of_a_gap`.
- **Scope blocked.** The "recording/storage integrity" claim for M3/M6; any
  annotation that maps audio samples to controller time after a backlog event.

### M1-audio-001-R02-F03 — Major — an out-of-order device timestamp raises inside the input callback; the stream dies and the trial continues with no fault until `finalize()`

- **Location.** `timing.py:150-156` (`StreamTimebase.anchor` raises `ValueError`
  on a non-monotonic position or time), reached from `timing.py:297`
  (`note_block`), called unguarded from `audio_io.py:748-752`
  (`ContinuousRecorder._callback` has a `try` only around the enqueue);
  `audio_io.py:408-431` (`SoundDeviceBackend._timing`: two different formulas
  for `first_frame_time` — `entry + (adcTime − currentTime)` under
  `"device_time"`, `entry − nominal` under `"fallback"`).
- **Requirement.** `goal.md` §6 "Any unexpected recording, playback, clock,
  device or disk failure stops prompt output, finalizes what is recoverable and
  flags the attempt. **Do not continue a trial while recording is broken**";
  §13 "Device loss, disk error … produce flagged recoverable attempts".
- **Evidence.** The author's own survey records a real host API that alternates
  between the two formulas inside one stream:
  `audio_check_survey.json` → `output_survey[Windows WDM-KS]`,
  `"block_timing_method": ["device_time", "fallback"]`. For an input stream the
  two formulas differ by `nominal + |adcTime − currentTime|` ≈ one block plus the
  input latency. A switch in one direction fabricates a `TimelineGap` of tens of
  ms of "lost frames" (drift > `gap_tolerance_s` = 2 ms, i.e. one fifth of a
  block); a switch back makes `first_frame_time + frames/rate` smaller than the
  previous anchor time and `anchor` raises **inside the PortAudio callback**.
  `note_block` has already mutated `frames_written`/`device_frames`/`segments`
  before the raise, and the exception escapes before the enqueue, so the block is
  lost too. sounddevice does not deliver the frames and does not call back
  again; the recorder records **no `FaultRecord`, no `audio_fault` ledger entry
  and never calls `on_fault`**, keeps `self._stream` set and keeps reporting
  itself started. The failure surfaces only when `finalize()` calls
  `stream.stop()` and catches the stored exception — logged under the misleading
  kind `stream_close_failed` (`audio_io.py:790-797`) — by which time the attempt
  has run to its end recording nothing. There is no callback-liveness watchdog.
  Note that the only input-capable endpoints on this PC are WDM-KS Bluetooth
  devices (`audio_spike.md` Finding 1), i.e. the mixed-method host API, and that
  real capture is **BLOCKED**, so no input callback in this code has ever run
  against a real device.
- **Proposed correction.** (a) Never raise from the audio path: wrap the whole
  body of `ContinuousRecorder._callback` so any exception becomes a
  `FaultRecord` plus an `on_fault` signal, and have `StreamTimebase.anchor`
  clamp a non-monotonic anchor and report a `clock_anomaly` fault instead of
  raising (keep the strict raise for the controller-thread API if you want it).
  (b) Treat a change of `BlockTiming.method` within one stream as a fault rather
  than as a time source — a stream that starts on `device_time` must not
  silently fall back. (c) Add a liveness check (last callback time vs now) that
  faults an attempt whose capture callback has stopped, while the trial is still
  running. (d) Revisit `gap_tolerance_s = 0.002` against measured device
  timestamp jitter before trusting the gap count.
- **Verification.** A `FakeStream` case that delivers a `method="fallback"`
  block after `device_time` blocks, and a block whose `first_frame_time`
  precedes the previous one: assert that no exception escapes the callback, that
  a fault is recorded and `on_fault` is called at that moment (not at
  finalize), and that the published attempt is flagged. Then one real
  `--duplex --allow-microphone` run once a suitable input device exists (M1
  hardware gate).
- **Scope blocked.** The "capture is continuous and faults are flagged" claim
  on real hardware; this is the main reason the fake-backend pass cannot be
  read as a device-layer pass.

### M1-audio-001-R02-F04 — Major — `OutputPlayer._committed` is never cleared, so one committed prompt contaminates every later trial's cancellation and stop records

- **Location.** `audio_io.py:1150-1151` (`self._committed = cand`), read at
  `:1022` (`cancel_candidate`) and `:1070-1071` (`stop`). It is cleared
  nowhere — not in `stop()` (`:1049-1072`), not in `close()` (`:915-927`) — and
  there is no per-trial/per-attempt reset API on the player at all.
- **Requirement.** `goal.md` §6 one-use encouragement flag, the rearming rule
  ("a cancellation before commitment does not consume the one-prompt
  allowance"), "Log every candidate and cancellation separately", and the
  precedence table (Stop → "Stop output … `ABORTED` with reason"); packet
  invariant "after commitment the attempt is consumed and reported as such".
- **Evidence and failure cases.** `decisions.md` D2 keeps exactly one
  `OutputPlayer` for the whole session, so `_committed` is session-scoped state
  read by per-trial operations.
  1. After trial 1's prompt commits, in trial 5 — nothing armed, nothing
     committed in that trial — `cancel_candidate("speech_resumed")` takes the
     `cand is None` branch, finds trial 1's candidate in `_committed`, logs
     `prompt_cancel_too_late` **carrying `trial_id` of trial 1** and returns
     `False`. A controller following the documented contract ("`False` means it
     was already committed", `audio_io.py:1012-1016`) records a consumed
     allowance and an overlap deviation for a trial in which nothing was
     spoken. The author's own bench tool already drives this path: it calls
     `player.cancel_candidate("probe_cleanup")` after each of the 40 trials
     (`tools/check_audio.py:414`).
  2. `stop()` computes `interrupted = clip_id is not None and self._committed
     is not None and self._committed.committed`. So pressing Stop while *any*
     clip is playing — the story, the instruction — in any trial after the first
     committed prompt reports `interrupted_committed_prompt=True`. That is a
     false deviation record attached to a withdrawal/distress Stop, which §6
     precedence 1 makes the most consequential event in the protocol.
  The suite never crosses an attempt boundary: `OutputPlayerTest` builds a fresh
  player per test (`setUp`), so neither case is reachable in the current tests.
- **Proposed correction.** Add an explicit `begin_attempt(trial_id,
  attempt_id)` that asserts an idle state and clears `_committed`, `_candidate`,
  `_candidate_clip`, `_guard` and `_finished`, and have `arm()` refuse a
  candidate whose `trial_id` does not match the current attempt. Decide
  `interrupted` by identity (was the clip being stopped the committed prompt's
  clip, or compare `generation`) rather than by a sticky flag.
- **Verification.** A test that arms and commits in attempt 1, calls
  `begin_attempt` for attempt 2, then calls `cancel_candidate` with nothing
  armed and asserts no `prompt_cancel_too_late` record and a "nothing armed"
  result; a test that `stop()` during a story clip in attempt 2 reports
  `interrupted_committed_prompt=False`.
- **Scope blocked.** The one-prompt allowance and the deviation log for every
  trial after the first encouragement — i.e. the M3 contract this layer exists
  to support.

### M1-audio-001-R02-F05 — Major — a guard-vetoed (never spoken) prompt makes `cancel_candidate` return `False` with no record, which the documented contract means "already committed"

- **Location.** `audio_io.py:1011-1037` (`cancel_candidate`), specifically
  `:1020-1022` and the `if cand is None: if committed is None: return False`
  path at `:1030-1032`; interacts with `_maybe_commit`'s veto branch at
  `:1136-1142`, which sets `self._candidate = None` without setting
  `_committed`.
- **Requirement.** `goal.md` §6: "a cancellation before commitment does not
  consume the one-prompt allowance. Return to listening and calculate a fresh
  deadline from the next detected speech offset. **Commitment consumes the
  allowance**"; "Log every candidate and cancellation separately"; packet
  invariant "A cancellation before commitment removes the clip; after
  commitment the attempt is consumed and reported as such".
- **Evidence and failure case.** The documented return contract is "``False``
  means it was already committed… the caller must log the overlap rather than
  retry" (`:1012-1016`). But `False` is also returned when nothing is armed and
  nothing has committed — including the reachable race the guard exists for:
  resumed speech arrives in the same instant as the deadline callback, the guard
  vetoes, `_maybe_commit` cancels the candidate and clears the armed slot
  (`:1136-1142`), and the controller's own `cancel_candidate("speech_resumed")`
  then lands on an empty slot, returns a bare `False` **and logs nothing at
  all**. A controller honouring the documented contract consumes the one-prompt
  allowance and records an overlap for a prompt that was never audible —
  precisely inverting the rearming rule. `audio_spike.md` Finding 4 lists this
  defect class as already found and fixed ("a cancellation request after
  commitment returning a bare `False` so the controller could not distinguish
  'nothing armed' from 'too late, already audible'"); the fix covered the
  post-commit case only. The tests assert the committed case
  (`test_a_committed_prompt_stays_reportable_after_the_clip_ends`) and never the
  veto-then-cancel sequence.
- **Proposed correction.** Replace the boolean with three explicit outcomes —
  `REMOVED` / `ALREADY_CANCELLED` (with the reason, not consuming the
  allowance) / `TOO_LATE_COMMITTED` (consuming it) / `NOTHING_ARMED` — and log a
  record in every branch, including the no-op one. Keep "too late" reserved for a
  candidate of the current attempt that actually committed (see F04).
- **Verification.** A test that arms with a vetoing guard, pumps past the
  deadline, then calls `cancel_candidate` and asserts the outcome is
  "already cancelled, allowance intact" with a ledger record and **no**
  `prompt_cancel_too_late`; and a test that an unarmed player returns
  "nothing armed" with a record.

### M1-audio-001-R02-F06 — Major — a speech offset can be dated arbitrarily far in the past while the detector sits in the hysteresis band, so the configured interval can expire before the controller is told, and `validate_detector_profile` does not bound this

- **Location.** `timing.py:602-612` (in-speech branch: `if p >=
  prof.exit_threshold: if p >= prof.speech_threshold: self._last_speech_frame =
  idx` then `self._quiet_frames = 0; return` — a frame in
  `[exit_threshold, speech_threshold)` keeps the segmenter in speech and resets
  the quiet counter but never updates `_last_speech_frame`);
  `timing.py:466-492` (`validate_detector_profile`); `decisions.md` D4.
- **Requirement.** `goal.md` §6: "Define silence onset from the end of the most
  recent detected participant speech frame"; "At the assigned threshold,
  re-check that speech has not resumed"; and D4's claim that
  `validate_detector_profile` "**therefore refuses any profile** whose hangover
  plus decision budget reaches the shortest threshold, rather than letting that
  configuration run and be late".
- **Evidence (static trace; arithmetic checkable by hand against the suite's
  own profile — `frame_ms=32`, `min_speech_ms=96`, `hangover_ms=160`,
  `exit=0.35`, `speech=0.5`, `frame_time = i * 0.032`).** Push
  `[0.9]*4 + [0.4]*20 + [0.0]*5`. Frames 0-3 open speech with
  `_last_speech_frame = 3`. Frames 4-23 are in the hysteresis band: in speech,
  quiet counter reset, `_last_speech_frame` unchanged. Frames 24-28 are below
  the exit threshold, so at frame 28 an offset is emitted with
  `frame_index = 3`, `event_time = 0.128` and `confirmed_time = 0.928`
  (verifiable against `test_offset_is_the_end_of_the_last_speech_frame`, which
  uses the same profile and the same indexing). At the 0.5 s condition the
  deadline is `0.128 + 0.5 = 0.628 s` — **0.300 s in the past** when the
  controller first learns of it. `PauseTimer.eligible(now)` is therefore true
  immediately and the prompt commits at the very next callback, after ~0.160 s
  of actual below-exit quiet rather than 0.500 s. The band dwell is unbounded,
  so the overshoot is unbounded, and `validate_detector_profile`'s
  `hangover + decision_budget < shortest threshold` test does not bound it —
  the guarantee D4 advertises does not hold in this path. The existing
  `test_hysteresis_keeps_a_dip_inside_one_speech_run`
  (tests/test_timing.py:245-248) asserts only that no event is emitted during
  the dip; it never checks where the subsequent offset lands.
- **Note on direction.** This is the *opposite* of the double-counting `goal.md`
  §6 warns about. The configured interval is added exactly once — that invariant
  holds, and `test_threshold_is_added_once_to_the_real_speech_offset` plus the
  `pause_deadline_*` checks genuinely demonstrate it. The defect is that the
  interval can be consumed by time the detector itself was treating as speech,
  so the participant can receive the prompt after materially less silence than
  the assigned threshold. Since the threshold *is* the manipulation, a silent
  shortening is a protocol-level problem, not a cosmetic one.
- **Proposed correction.** Either (a) set `_last_speech_frame = idx` for any
  in-speech frame at or above `exit_threshold`, so the offset is the end of the
  in-speech run (the reading of "most recent detected speech frame" that matches
  the segmenter's own state), or (b) keep the current definition and refuse to
  act on a deadline already past by more than a configured budget — commit
  nothing, emit a `deadline_already_past` deviation and let the controller
  rearm. In both cases record band-dwell time as its own field next to
  `detector_delay_s`, and extend `validate_detector_profile` (or a runtime
  check) to cover it. Which of (a)/(b) is correct is research-owned (see Open
  decisions below); the code must make the choice explicit either way.
- **Verification.** A test over the exact sequence above asserting the intended
  relationship between `event_time`, `confirmed_time` and the deadline, and a
  test that a deadline already past by more than the budget produces a flagged
  deviation instead of an immediate commit.
- **Scope blocked.** The meaning of the pause threshold once a real VAD is
  attached in M3; it does not block synthetic M3 work, but it must be settled
  before any timing tolerance is frozen.

### M1-audio-001-R02-F07 — Minor — `TimingLedger` is written from the audio callback and the controller thread with no synchronisation; `seq` can duplicate

- **Location.** `timing.py:855-868` (`record`: `self._seq += 1` then
  `records.append`), called from the PortAudio thread via
  `ContinuousRecorder._log`/`_fault` (`audio_io.py:728-744`) and
  `OutputPlayer._log`/`_fault`/`_maybe_commit`, and from the controller thread
  for everything else. `tools/check_audio.py:136-145` already shares one ledger
  between a recorder and a player.
- **Requirement.** `goal.md` §10 "ordered event records with trial/attempt IDs";
  §5 "append-only JSONL events".
- **Evidence.** `self._seq += 1` is a read-modify-write with no lock, so two
  threads can observe the same value and emit two records with the same `seq`;
  ordering by `seq` then becomes ambiguous. Low probability under the current
  GIL, but it is the sequence authority for the audio layer, and the project's
  measured environment is Python 3.13 where a free-threaded interpreter is a
  realistic future.
- **Proposed correction.** `itertools.count()` (its `__next__` is atomic) or a
  `threading.Lock` around the increment and append.
- **Verification.** A test with N threads each recording M events asserting
  `len({r["seq"] for r in ledger.records}) == N*M`.

### M1-audio-001-R02-F08 — Minor — three different detector profiles are in use and the evidence record names a fourth combination

- **Location.** `timing.py:408-416` (`DetectorProfile` defaults: frame 32 ms,
  `min_speech_ms=120`, `hangover_ms=150`); `tests/test_timing.py:209-211` and
  `tests/test_audio_io.py` (32 / 96 / 160); `tools/check_audio.py:106-107`
  (32 / 96 / 150); `validation/audio_spike.md` "Limitations to carry forward"
  describes "the detector profile (32 ms frames, 96 ms minimum speech, 150 ms
  hangover)".
- **Requirement.** `goal.md` §6 "Document frame size, thresholds, smoothing,
  minimum speech length and detector hangover"; §12 "Configuration must record
  … detector settings"; §14 the profile is part of the frozen manipulation.
- **Evidence.** The spike's stated profile matches the bench tool but neither
  the library default an M3 implementer inherits (120 ms minimum speech) nor the
  profile that produced the PASS rows in the suite (160 ms hangover). Nothing
  reconciles them, and there is no configuration file yet.
- **Proposed correction.** One named `DEFAULT_PROFILE` (or no defaults at all,
  forcing the caller to supply the frozen profile) referenced by the tool, the
  tests and the record; state the single profile in the spike.
- **Verification.** A test asserting the tool, the suite and the documented
  profile are the same object/values.

### M1-audio-001-R02-F09 — Minor — a zero-frame recording reports `continuous: true` and `finalized: true`, and a failed `start()` can publish an empty WAV at the final path

- **Location.** `audio_io.py:702-721` (`start()` creates the sink and writer
  thread *before* `backend.open_input`, and does not tear them down if opening
  the device raises); `audio_io.py:781-845` (`finalize()` renames whatever
  `.partial` exists and sets `finalized=True`); `timing.py:370`
  (`"continuous": not self.gaps` — true when there are no frames at all).
- **Requirement.** `goal.md` §10 "Detect incomplete attempts after crashes;
  never silently mark them complete"; §13 "produce flagged recoverable
  attempts, not false completion".
- **Evidence.** If the device disappears between validation and `open_input`,
  `start()` raises but leaves a writer thread and an open sink, and the
  header-only `.partial` on disk. A controller cleanup that then calls
  `finalize()` renames it to the final path and returns
  `finalized=True, frames=0`, with `integrity.continuous=True`, no segments and
  **no fault recorded**. On disk the attempt is indistinguishable from a
  successful empty one.
- **Proposed correction.** Tear down the sink and writer on a `start()` failure
  (and record the fault); record a fault in `finalize()` when `frames == 0` or
  `timeline.segments` is empty; make `continuous` false when nothing was
  captured.
- **Verification.** A test with a backend whose `open_input` raises: assert
  `start()` raises, that a later `finalize()` does not create the final path (or
  creates it carrying a fault), and that no thread is left running.

### M1-audio-001-R02-F10 — Minor — after an abrupt kill the `.partial` file's WAV header reports zero frames, so "recoverable" needs a repair step that does not exist

- **Location.** `audio_io.py:656-683` (`WaveSink` uses `wave.open(…, "wb")`,
  which patches the RIFF/`data` sizes only on `close()`); `decisions.md` D6;
  packet "publishes by rename so an attempt that never finalised stays
  detectable".
- **Requirement.** `goal.md` §6 "Crash recovery reconstructs the unfinished
  finalization rather than inventing success"; §13 "service crash produce
  flagged recoverable attempts"; §10 "Write incrementally and finalize
  atomically".
- **Evidence.** The *detectability* claim is true and tested
  (`test_refuses_to_start_over_an_unfinalized_attempt`), and `os.replace` is
  genuinely atomic — I found no defect in the rename itself. But after a
  `taskkill`/power loss the `.partial` holds the PCM bytes under a header whose
  `nframes`/`data` size are still 0, so every standard reader (including
  `wave`, which the project uses everywhere) reports an empty file. Recovering
  the audio requires rewriting the header from the file length, and no such
  helper exists; nor is any sidecar written at `start()` recording rate and
  channels. The packet's own invariant list stops at "detectable", so this is a
  gap between the two documents rather than a false claim.
- **Proposed correction.** Add a documented recovery helper that rebuilds the
  header from the on-disk length (optionally rewriting the size fields
  periodically during capture), plus a small JSON sidecar written at `start()`
  with rate, channels, dtype and the attempt identity. Flag explicitly as an M3
  `storage.py` dependency if it is deferred.
- **Verification.** A test that abandons a `.partial` without closing the sink
  and then recovers the expected N frames and sample values from it.

### M1-audio-001-R02-F11 — Minor — the bench tool's JSON `verdict` is `PASS` while checks are `NOT_RUN`/`BLOCKED`

- **Location.** `tools/check_audio.py:544-550`
  (`report["verdict"] = FAIL if counts.get(FAIL) else PASS`).
- **Requirement.** `EGM_WORKFLOW.md` §6: "Mark each check `PASS`, `FAIL`,
  `NOT_RUN` or `BLOCKED`; **missing evidence is not PASS**."
- **Evidence.** `audio_check_wasapi.json` and `audio_check_playback.json` carry
  `"verdict": "PASS"` with `acoustic_onset` = NOT_RUN and capture BLOCKED;
  `audio_check_survey.json` and `audio_check_commit_wasapi.json` likewise with
  two NOT_RUN each. The prose in `audio_spike.md` and the packet handle this
  correctly, but the JSON is the quotable artifact and its top-level field reads
  as a clean pass.
- **Proposed correction.** Emit `INCOMPLETE` (or `PASS_WITH_NOT_RUN`) whenever
  any check is not PASS, and include the NOT_RUN/BLOCKED counts in the printed
  summary line.
- **Verification.** Re-run `python tools/check_audio.py` and confirm the verdict
  is no longer `PASS` while two checks are NOT_RUN.

### M1-audio-001-R02-F12 — Minor — more than byte-copying happens on the PortAudio thread, and `CaptureTimeline` is read from the controller thread with no synchronisation

- **Location.** `audio_io.py:748-764` (callback calls
  `CaptureTimeline.note_block` → `dataclasses.replace` allocation plus list
  appends at `timing.py:294-308`, then `TimingLedger.record` for each gap or
  overflow, then `_fault` → the controller-supplied `on_fault(...)`
  synchronously, `audio_io.py:734-744`); `audio_io.py:1077-1107`
  (`OutputPlayer._callback` holds the `RLock` while calling `self._guard()`,
  `self._log(...)` and `_fault` → `on_fault` on every underrun);
  `timing.py:302-308` (`_open_segment` appends to `segments` and *then* to
  `_starts`) versus `timing.py:316-346` (`_segment_for_sample` /
  `time_to_sample`, called from the controller thread).
- **Requirement.** `goal.md` §6 "Serialize decisions in one controller";
  `decisions.md` D6 "Disk I/O inside an audio callback risks underruns" and D7
  "The guard … must not lock, allocate or block".
- **Evidence.** No disk I/O happens in a callback — that specific claim holds.
  But: D7's non-blocking constraint is stated for `guard` only, while
  `on_fault` is invoked inline from the audio thread (and, in the output player,
  while holding the lock) with no such constraint documented, nothing measuring
  either, and an underrun storm calling it once per block. And
  `CaptureTimeline` is mutated from the audio thread while `sample_to_time`,
  `time_to_sample` and `integrity()` are read from the controller thread with no
  lock: because `_open_segment` appends to `segments` before `_starts`, a reader
  interleaved between those two statements resolves a sample belonging to the
  new segment against the previous segment's mapping and returns a **silently
  wrong controller time** (off by the gap). The window is microseconds and
  self-correcting, hence Minor, but the wrong value is evidence.
- **Proposed correction.** Time the guard and the callback body and fault on
  overrun rather than relying on a docstring; hand fault notifications to the
  writer/controller thread (a queue) instead of calling `on_fault` inline;
  document `on_fault`'s audio-thread constraint in D7; give `CaptureTimeline` a
  lock for its reader methods or derive `_starts` from `segments` so there is a
  single mutation point.
- **Verification.** A test that reads `sample_to_time` from a second thread
  while blocks (including a gap) are delivered, asserting no torn result; a test
  that a slow guard/`on_fault` is detected and faulted rather than silently
  stalling the stream.

### M1-audio-001-R02-F13 — Minor — `requirements.txt` specifies ranges, not pins, while the packet describes it as "pinned dependencies"

- **Location.** `requirements.txt` (`numpy>=1.24,<3`,
  `sounddevice>=0.4.6,<0.6`; measured versions appear only in comments); packet
  file table ("`requirements.txt` | pinned dependencies with the measured
  environment"); `goal.md` §5 "choose and **pin** compatible versions after the
  spike"; §12 M1 exit evidence "Select/pin audio/VAD dependencies".
- **Evidence.** The ranges admit numpy 1.24 through 2.x and sounddevice 0.4.6
  through 0.5.x, i.e. different PortAudio bindings and bundled PortAudio builds
  than the ones every timing number in `audio_spike.md` was produced with. The
  comment block records the measured set honestly, but a fresh install
  reproduces none of it deterministically.
- **Proposed correction.** Add exact `==` pins (or a `constraints.txt`) for the
  measured set, keep the ranges only as a documented compatibility note, and
  record the PortAudio version as an asserted runtime check rather than a
  comment. Soften the packet wording if ranges are deliberate.
- **Verification.** Fresh virtual environment install reproduces numpy 2.3.5 /
  sounddevice 0.5.5 / PortAudio V19.7.0-devel, and `check_audio.py` records them.

## Open research decisions / evidence gaps

Listed separately from the defects above; none of these is a code defect and
none blocks synthetic M3 work, but each blocks the release gate named with it.

1. **Measured acoustic onset — the central evidence gap.** Every onset figure in
   this checkpoint is `estimated` from PortAudio's own latency reporting, and
   F01 shows the one reported figure is also mis-decomposed. `goal.md` §7
   requires a recorded playback reference. Status NOT_RUN, correctly recorded.
   *Gate: "device models, measured timing tolerance and calibration method"
   (§14) and the M6 research-release checklist.*
2. **No input device on this PC.** Capture is BLOCKED, so every
   microphone-side claim rests on the fake backend, and F03 in particular has
   never been exercised against real device timestamps. The spike's Finding 1 is
   accurate and appropriately blunt, including the judgement that a Bluetooth
   hands-free endpoint is unsuitable. *Gate: same as (1); blocks M1 closure on
   hardware and the M6 dry session, not synthetic M3 work.*
3. **The 100 ms onset target is a proposal.** Both the tool and the spike label
   it so, and the `meets_candidate_onset_target` check is deliberately separated
   from the measurement checks — that separation is well done. *Gate: timing
   tolerance freeze (§14).*
4. **Detector profile values and the meaning of a hysteresis-band frame.** F06
   is a code defect, but *which* correction is right ((a) extend the speech run
   to the exit threshold, or (b) refuse a stale deadline) is an operational
   definition of the manipulation. *Gate: "recall-cap origin, completion
   procedure, event precedence, rearming, early-speech and overlap policies"
   (§14).*
5. **Rearming and overlap policy.** The code implements the proposed rule
   (cancel-before-commit does not consume the allowance; commitment does) —
   F04/F05 are defects *against that proposal*, not challenges to it. *Gate:
   §14 event precedence/rearming.*
6. **VAD integration, controller, server, UI, stimulus manifest, transcription.**
   Absent, and correctly scoped out by the packet. Not defects in this
   checkpoint: `goal.md` §12 places them in M3-M5, and the packet says so
   plainly.
7. **Durable attempt records.** The `TimingLedger` is explicitly in-memory and
   M3 owns `storage.py`; after a clean but faulted attempt the only on-disk
   evidence next to the WAV is its name. Expected at this stage; worth naming so
   it is not forgotten alongside F10.
8. **Checks I did not execute** (packet-prohibited; re-run by the coordinator if
   any finding is contested): `--playback`, `--survey`, `--commit-trials`,
   `--duplex`. F01 would be confirmed or refuted by one `--commit-trials` run
   with a tone probe.

## Verdict

**NEEDS_FIXES**

Scope of this verdict: the two files in the manifest plus the bench tool and the
evidence records, at the digests listed above, against `goal.md` v0.3 §§4, 5, 6,
7, 10, 12, 13, reviewed through the critic lens for timing/state-machine
correctness, concurrency and cancellation, recording/storage integrity and
evidence honesty.

On the readiness question: the *architecture* is sound and is the right thing to
build M3 on. Committing inside the callback that first observes the deadline
(D1), one session-long output stream (D2), gaps instead of padding (D3), the
threshold added only to the real offset (D4), a guard evaluated at the commit
instant (D7) and a fake backend with a manual clock (D8) are all good choices,
and I could not find any interleaving that makes prompt audio audible before the
eligibility deadline, nor any path that applies the configured interval twice,
nor any path that can label a scheduling timestamp `measured`. But three Major
defects sit on contracts M3 would consume directly — lost audio that leaves the
sample→time mapping silently wrong while reporting `continuous: true` (F02), an
uncaught exception in the input callback that kills capture mid-trial with no
fault until finalisation (F03), and session-sticky prompt state plus an
ambiguous cancellation return that can consume the one-prompt allowance for a
prompt that never played (F04, F05) — and one (F06) can silently shorten the
study's independent variable. On the second half of the question: the evidence
is unusually honest in structure (NOT_RUN and BLOCKED items are listed, the
fake-backend limit is stated repeatedly, the retracted single-shot figure is
flagged), but the headline onset numbers are mis-attributed and three documents
give mutually inconsistent accounts of the same device figure (F01). The
executed checks I could reproduce reproduced exactly.

What this verdict does **not** cover: participant readiness or any approval
(none is available from this review); acoustic timing of any kind — a
fake-backend pass is not hardware validation, and no onset here was measured;
microphone behaviour on real hardware, which is BLOCKED on this PC; behaviour
under system load, device drift over a session, echo and leakage; the renderer
adapter against the real browser; and any research-owned decision in `goal.md`
§14, all of which remain open. It also does not cover
`DEVELOPMENT_STATUS.md`, `README.md` or `reviews/INDEX.md`, which changed during
the review window and are not in the manifest.
