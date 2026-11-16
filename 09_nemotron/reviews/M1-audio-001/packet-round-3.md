# Fix-verification packet — M1-audio-001, round 3

A **recheck** of the round-2 findings, over the **complete** working tree.
Round 2's packet omitted three files that landed during the review window
(R03-F04); this manifest lists every Python, JSON and evidence file under
`09_nemotron`, verified against a `find` of the tree, and the session preflight
is in scope for the first time.

## Identity and requested review

- Checkpoint ID: `M1-audio-001`, round 3 (third and final iteration of the
  bounded loop in `EGM_WORKFLOW.md` section 8)
- Created: 2026-11-17, Asia/Tokyo
- Route/stage: focused route, **fix-verification** stage, with the session
  preflight added as a first-review scope under the "Audio feasibility, M1"
  and "Recording/storage, M3/M6" lenses
- Reviewer ID and output destination: `R04`,
  `reviews/M1-audio-001/goldfish-fix-verification-R04-round-3.md`
- Requested verdict scope, two questions answered separately:
  1. Are R03's four Majors and six Minors fixed by the mechanisms
     `resolution.md` (round 2 section) claims, without breaking the invariants
     R03 confirmed, and do the evidence records now state what was executed?
  2. Is `preflight.py` — an in-tree consumer of `timing.py` and `audio_io.py`
     that was never independently reviewed — sound in what it asserts to an
     operator, and does its contract with this layer hold?
- **Not** asked: participant readiness, acoustic validation, approval of any
  research decision, or whether M1 as a milestone is complete (it is not: the
  avatar clock-adapter checkpoint does not exist).
- Goal version and sections: `goal.md` v0.3; sections 4, 5, 6, 7, 10, 12, 13.
- Prior rounds: R01/R02 (round 1) and R03 (round 2) all returned
  `NEEDS_FIXES`. Reports preserved unedited in this directory.

## Map for this review

Read in this order:

1. [resolution.md](resolution.md), round 2 section — the findings, what was
   changed for each, and what was deferred.
2. [R03's report](goldfish-fix-verification-R03-round-2.md) — the original
   findings F01-F10 with their proposed fixes and verifications.
3. The code and tests named per finding below.

| R03 finding | Severity | Disposition | Where to check |
|---|---|---|---|
| F01 stale `_last_device_end` across fallback; unbounded `late_by` | Major | FIX | `timing.CaptureTimeline.note_block` (reset on no-device-time; `DEVICE_GAP_SANITY_S`); tests `test_a_fallback_run_between_device_timed_blocks_is_not_a_gap`, `test_a_device_clock_jump_is_an_anomaly_not_a_fabricated_loss` |
| F02 offset estimator steps backwards; wrong rationale; fake model | Major | FIX | `timing.CaptureTimeline` (`OFFSET_TRACK_RATE`, clamp to previous block *start*, `offset_steps`, `device_time_went_backwards`); `audio_io.FakeStream.start/deliver` (`_epoch`); tests `test_realistic_callback_jitter_is_not_a_gap` (reordered, monotonic), `test_a_device_clock_running_backwards_is_still_a_real_anomaly`, `test_a_large_offset_correction_is_noted_but_is_not_a_clock_fault`, drift and mapping tests |
| F03 `continuous` on an unsupported basis; shortfall index past EOF | Major | FIX | `timing.CaptureTimeline.integrity` (`continuity_supported_by_basis`, `undetectable_gap_s`), `note_tail_shortfall`; `audio_io.ContinuousRecorder.finalize`; tests `test_continuity_is_not_asserted_on_the_callback_time_basis`, `test_frames_after_a_writer_failure_are_recorded_as_lost` |
| F04 undeclared files; test count did not reproduce | Major | FIX (process) | this packet's manifest and verbatim `git status`; per-file counts below |
| F05 missing command; timestamp note; superseded JSONs read PASS | Minor | FIX | `validation/audio_spike.md` header and reproduce block; `superseded` keys in the two JSONs |
| F06 `on_fault` contract; `fsync` undispositioned | Minor | FIX + DEFER (C18) | `audio_io.ContinuousRecorder._fault` docstring; `decisions.md` D6, D7 |
| F07 `begin_attempt` opt-in | Minor | FIX | `audio_io.OutputPlayer._require_attempt`, `arm`, `play`; tests `test_arming_outside_an_attempt_is_refused`, `test_a_candidate_from_another_trial_is_refused` |
| F08 `too_late` unreachable; invalid-profile test | Minor | FIX | `timing.PauseTimer` docstring; `StaleDeadlineTest` (now `DEFAULT_PROFILE`, gap-driven case) |
| F09 origin hard-coded, recorded as analysis-only | Minor | FIX | `timing.PauseTimer(origin=...)`, `ORIGIN_RUN_END`/`ORIGIN_LAST_STRONG`; `SilenceOriginTest`; `decisions.md` D4 |
| F10 uncertainty, TeamViewer caveat, `or 0.0` | Minor | FIX | `audio_io.OutputPlayer._maybe_commit` (uncertainty, both readings); `audio_spike.md`; `tools/check_audio.commit_distribution` (skip-and-count) |
| C15 residual | Minor | FIX | `tools/check_audio.duplex_check(--input-device)` |

Deferred with owners and gates, unchanged by this round: **C12**, **C16**,
**C18** (all to the M3 storage/controller checkpoints; the M3/M6
crash-recovery gate stays unpassed).

## Behaviour that changed in round 2

1. `CaptureTimeline` drops its device-clock reference on any block without a
   device time and re-anchors on the next that has one. A `late_by` of
   `>= 1.0 s` is a `device_time_discontinuity` anomaly with the loss unknown.
2. The device-to-controller offset is a slow symmetric tracker; block time is
   clamped to be non-decreasing; a correction `> 5 ms` is an `offset_steps`
   note (not an anomaly); a device clock running backwards by more than the
   device tolerance is a `device_time_went_backwards` anomaly.
3. `integrity()["continuous"]` additionally requires the device-clock basis
   and reports `gap_basis`, `undetectable_gap_s`, `continuity_supported_by_basis`,
   `offset_steps`.
4. A finalisation shortfall gap sits at `frames_persisted` with no trailing
   segment.
5. `OutputPlayer.arm()`/`play()` raise outside `begin_attempt()`; `arm()`
   refuses a mismatched `trial_id`.
6. `PauseTimer(origin=...)` selects which offset reading the live deadline
   counts from and records it.
7. Onset `uncertainty_s >= |reported latency - per-block offset|`; both
   readings are in the record.
8. `FakeStream` in device-time mode derives `first_frame_time` from the device
   clock plus a fixed epoch, so entry jitter does not reach the mapping.

Invariants that must still hold (R03 confirmed all of these after round 1):
no output before the deadline and none before participant speech; the
interval added exactly once to the speech offset; cancellation semantics;
exact file bytes; atomic publication; no `measured` estimate anywhere.

## Snapshot identity

- Repository `C:/Users/suraj/Downloads/Tanuki`, branch `main`.
- Base commit: `01985465073499d211b1a00cae20935c0dd0dc9b` ("M1-fix"). Two
  commits (`b4fd62f M1-audio-001`, `0198546 M1-fix`) were made **by the
  user** since round 2; the coordinator made none. The round-2 code changes
  are inside `0198546`; the files below marked `M` were edited after it.
- `git status --porcelain` at packet time, verbatim:

  ```text
   M 09_nemotron/decisions.md
   M 09_nemotron/reviews/INDEX.md
   M 09_nemotron/reviews/M1-audio-001/resolution.md
   M 09_nemotron/tools/check_audio.py
   M 09_nemotron/validation/audio_check_commit_default.json
   M 09_nemotron/validation/audio_check_commit_wasapi.json
   M 09_nemotron/validation/audio_check_survey.json
   M 09_nemotron/validation/audio_spike.md
   M 09_nemotron/validation/preflight_wasapi.json
  ```

  No untracked files. `find 09_nemotron -name "*.py" -o -name "*.json"`
  (excluding `__pycache__` and `.preparation`) returns exactly the Python and
  JSON files in the manifest below.

| Path | Role | SHA-256 |
|---|---|---|
| `timing.py` | implementation | `d0b06c4773e797a2aad15bebdb6f3148e1dd3c076f54dba660440c5d754d1223` |
| `audio_io.py` | implementation | `b5392eef96d75ca02c9208c8f14ec2a942945fa1839a8a03083c43f8ee671f95` |
| `preflight.py` | implementation — **first review** | `945028976e7aefed33ac78412777b75a4e571dd941cfa6c24e03195fa7253359` |
| `tools/check_audio.py` | tool | `77d0ae011da842544a6aa21272a200f08d54d60fc2b1ceb869dc63d3c10206e6` |
| `config/experiment.json` | configuration — **first review** | `a1f3b16aceb0139b0e4fbbf7a84efad4913f34d3abd06788ee7fb15efe6c4bce` |
| `requirements.txt` | dependencies | `d1f186aabdb10aafa65a2bda5cbc5d0dec5b3931bf0bb260180e79517fa8d59a` |
| `decisions.md` | rationale | `2238f39d053eaca97de7d8c43529fabe34f014faa71a014f9fa8491c1a949b0f` |
| `.gitignore` | config | `64371dbd6c0b6e3b4aec314f7be3f2bd153e4185fc494721d06bc42bf20fab49` |
| `tests/test_timing.py` | test (74) | `2b43991fc93feab1c16315d4807b6fd47a03f820f7e6b436a51f54e56e46d11e` |
| `tests/test_audio_io.py` | test (53) | `7ba98c98537987e827ed633c24b24130532f4d6cb3cc20725f09ee723de7f9b7` |
| `tests/test_preflight.py` | test (26) — **first review** | `fc3fa3a94ac1c30a74d17b09a29f498092e44e6f608bf01dc80c154094240640` |
| `validation/audio_spike.md` | evidence | `d60bb74f8fd162a8988da2d2e4d3dc8e89526c01339535159f0a3c0cb3b55d47` |
| `validation/audio_check_survey.json` | evidence (re-run) | `9e146c5eae789024b7847d3bca89675358a8d52a3d09e5156b14b71e5cc16a90` |
| `validation/audio_check_commit_wasapi.json` | evidence (re-run) | `13366f9df18cdd5b80eb86d791b7b884160641c5d3a16be0c2d86d3dd318a698` |
| `validation/audio_check_commit_default.json` | evidence (re-run) | `1941d67b73bf96d7d09b46e3f394ddcbd23f65697ba3dc091be34faf0086007a` |
| `validation/audio_check_wasapi.json` | superseded evidence, now marked in-file | `bdadda1f23a96e3f023cc7fb74229805b45490735c8534c3a3e0e3f99960e47b` |
| `validation/audio_check_playback.json` | superseded evidence, now marked in-file | `8033cace27ec024cd45cbcabe69146dc215c44e25a29fb6dc6cd2b2513edbd6f` |
| `validation/preflight_wasapi.json` | evidence — **first review** | `1d186b1da1fce1920c1eaa634636eb5cbb625a1b832318c0deba1d297d243304` |
| `reviews/M1-audio-001/resolution.md` | fix record (rounds 1 and 2) | `61fb5861ca11443775d92ae63ba37e8234def508e5d85b15ab587a682b0618d4` |

Target edits are paused for the duration of this review. Recheck these digests
on return and mark affected coverage stale if any differ.

## Acceptance checks and actual evidence

Environment for every row: Windows 11 Education 10.0.26300 x64, Python 3.13.9
(Anaconda), numpy 2.3.5, sounddevice 0.5.5, PortAudio V19.7.0-devel, working
directory `C:/Users/suraj/Downloads/Tanuki/09_nemotron`. **All device
measurements were taken over a TeamViewer remote session** and must be
repeated at the physical machine.

| Requirement | Check | Status | Result | Limitations |
|---|---|---|---|---|
| Round-2 fixes regress-tested | `python -m unittest discover -s tests -p "test_*.py"` | PASS | **153 tests OK**, 0.40 s; per file, each run separately: 74 + 53 + 26 | Fake backend; no device |
| Tool honest about missing evidence | `python tools/check_audio.py` | PASS | 8 PASS, 2 NOT_RUN, verdict `INCOMPLETE` | Opens no stream |
| Corrected onset, WASAPI | `--commit-trials 40 --device 8` | PASS | 0/40 early; commit p95 9.61 ms; device offset 10.00; probe lead 10.00; onset p95 29.61 ms | Estimate, not acoustic; TeamViewer |
| Corrected onset, default | `--commit-trials 40` | FAIL vs candidate target | onset p95 192.88 ms; device offset 170.15 | Target is a proposal |
| Host-API comparison | `--survey` | PASS | WASAPI 22.0 / MME 180.0 / DirectSound 240.0 / WDM-KS 40.7 ms | 1 s each, silence, no load; TeamViewer |
| Session preflight on real hardware | `python preflight.py --config config/experiment.json --trials 20 --out validation/preflight_wasapi.json` | PASS (ran) | pinned WASAPI resolved; 0/20 early; verdict `INCOMPLETE_WITH_WARNINGS`; `may_start: true` | Capture check disabled; 5 checks NOT_RUN by configuration |
| Capture on this PC | `--duplex --allow-microphone` | **BLOCKED** | no default input; two WDM-KS Bluetooth endpoints; `--input-device` now exists but was not run | Hardware gap |
| Acoustic onset, last-speech-to-response, detector error on real speech, echo, completion suppression, renderer avatar clock, session drift, load | — | **NOT_RUN** | — | — |

Failed attempts during round 2, kept rather than hidden:

- A first version of the F02 clamp used the previous block's nominal *end*;
  the existing drift test immediately showed it erased device drift
  (measured 1e-7 ppm instead of 1000) and added 60 ms of mapping error. It was
  changed to clamp to the previous block's *start* before anything was
  recorded.
- The sanity threshold for a device-clock jump was `>` where the test used
  exactly 1.0 s; changed to `>=` and the test moved to 1.5 s.
- F07's enforcement caught the bench tool's own synthetic and `--playback`
  paths arming outside an attempt (the measurements failed until fixed) — the
  same omission R03 predicted a controller could make.
- The per-file test counts first written into the spike record (70/57/26)
  were wrong; they were corrected to the verified 74/53/26 before the record
  was saved.

## Reviewer permissions

- Default: read-only inspection of the manifest files, their imports,
  `goal.md`, `AGENTS.md`, `EGM_WORKFLOW.md`, the three earlier reports and
  `resolution.md`.
- Explicitly allowed, after you have inspected what they do:

  ```text
  python -m unittest discover -s tests -p "test_*.py"
  python -m unittest discover -s tests -p "test_timing.py"
  python -m unittest discover -s tests -p "test_audio_io.py"
  python -m unittest discover -s tests -p "test_preflight.py"
  python tools/check_audio.py
  ```

  From `C:/Users/suraj/Downloads/Tanuki/09_nemotron`, with
  `PYTHONPYCACHEPREFIX` pointing at your scratch directory. None opens an audio
  stream; the suite writes only into `tempfile` directories. **Do not** run
  `tools/check_audio.py` with `--playback`, `--survey`, `--commit-trials` or
  `--duplex`, and **do not** run `preflight.py` (it opens the output device
  and plays a faint tone). Ask the coordinator to re-run one if needed.
- Isolated scratch: your own directory under the system temp directory. Write
  nothing inside `09_nemotron` except your report file.
- Prohibited: editing any manifest file, installing dependencies, downloading,
  starting services, live microphone capture, real participant records (none
  exist).

## Questions this review should answer

1. For each of R03-F01..F10: fixed by the claimed mechanism? Would the named
   test fail if the fix were reverted?
2. Do the round-1 invariants R03 confirmed still hold after round 2?
3. F02 specifically: is the symmetric tracker plus start-clamp sound? Can the
   mapping ever run backwards now? Is a genuine backwards device clock still
   distinguishable from an estimator correction? Does the fake backend now
   model the real `device_time` path correctly?
4. F01/F03 specifically: on a WDM-KS-like stream that alternates bases, does
   the timeline neither fabricate gaps nor claim continuity?
5. The preflight: is anything it reports to an operator stronger than what it
   measured? Does its blocking/warning logic match `config/experiment.json`
   and the decision recorded in `DEVELOPMENT_STATUS.md` (warn and record on
   out-of-target timing; never open the microphone unless enabled)? Does it
   respect this layer's contracts (`begin_attempt`, `CancelOutcome`,
   `has_audible_onset`)?
6. Is this now a snapshot a fresh review covers in full, per
   `EGM_WORKFLOW.md` section 8?
