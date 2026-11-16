# Fix-verification packet — M1-audio-001, round 2

This is a **recheck**, not a fresh review. It supplies the round-1 findings and
their claimed fixes so a fresh reviewer can trace each one through the changed
code and its regression evidence.

## Identity and requested review

- Checkpoint ID: `M1-audio-001`, round 2
- Created: 2026-11-17, Asia/Tokyo
- Route/stage: focused route, **fix-verification** stage
  (`EGM_WORKFLOW.md` sections 4 and 8)
- Reviewer ID and output destination: `R03`,
  `reviews/M1-audio-001/goldfish-fix-verification-R03-round-2.md`
- Requested verdict scope: are the eight consolidated Major findings from
  round 1 actually fixed, did the fixes introduce new defects or unnecessary
  complexity, and do the corrected evidence records now state what was
  executed? Specifically **not** asked: participant readiness, acoustic
  validation, approval of any research decision, or whether M1 as a milestone
  is complete (it is not — see below).
- Goal version and sections: `goal.md` v0.3; sections 4, 5, 6, 7, 10, 12, 13.
- Prior round: both round-1 reviewers returned `NEEDS_FIXES`.

## What changed since round 1

Round-1 reports, preserved unedited:

- [R01, focused](goldfish-focused-R01-round-1.md) — 6 Major, 6 Minor
- [R02, critic](goldfish-critic-R02-round-1.md) — 6 Major, 7 Minor

Consolidated findings, dispositions and the full description of each fix are in
[resolution.md](resolution.md). Read that first: it is the map for this review.

| ID | Round-1 reviewers | Severity | Disposition | Where to check |
|---|---|---|---|---|
| C1 | R01-F01, R02-F01 | Major | FIX | `audio_io._leading_silence_s`, `Clip.has_audible_onset`, `OutputPlayer._maybe_commit`, `timing.PromptCandidate.onset_delay_s`, `tools/check_audio.commit_distribution`; tests `OnsetEstimateComponentsTest` |
| C2 | R01-F02, R02-F02 | Major | FIX | `ContinuousRecorder._callback_body`, `_drain`, `finalize`; `timing.CaptureTimeline.note_not_persisted`/`note_persisted`/`integrity`; tests `RecorderLossAccountingTest` |
| C3 | R02-F03 | Major | FIX | `timing.StreamTimebase.anchor`, `ContinuousRecorder._callback`, `check_liveness`; tests `CaptureFaultContainmentTest` |
| C4 | R01-F03, R02-F04 | Major | FIX | `OutputPlayer.begin_attempt`, `_playing_candidate`; tests `AttemptScopingTest` |
| C5 | R02-F05 | Major | FIX | `audio_io.CancelOutcome`, `cancel_candidate`, `_vetoed`; test `test_a_vetoed_prompt_does_not_consume_the_allowance` |
| C6 | R01-F06, R02-F06 | Major | FIX | `timing.SpeechSegmenter.push` in-speech branch, `SpeechEvent.band_*`, `PauseTimer.discovery_lateness`/`too_late`/`eligible`; tests `HysteresisOffsetOriginTest`, `StaleDeadlineTest` |
| C7 | R01-F04 | Major | FIX | `audio_io.BlockTiming.device_time`, `SoundDeviceBackend._timing`, `FakeStream.deliver`, `timing.CaptureTimeline.note_block`; four new gap tests |
| C8 | R01-F05, R02-F13 | Major | FIX | `requirements.txt` |
| C9-C11, C13-C15, C17 | both | Minor | FIX | see resolution.md |
| C12 | R01-F12, R02-F10 | Minor | **DEFER** to M3 | `.partial` header reports zero frames after an abrupt kill |
| C16 | R01-F10 | Minor | **DEFER** to M3 | nothing binds `PromptCandidate.deadline` to `PauseTimer` |

Accepted and **not** addressed in this round, by design: both reviewers noted
that M1 as a milestone also requires the avatar clock-adapter demonstration
(`goal.md` section 7). That is a separate future checkpoint (`M1-avatar-002`)
and does not exist yet. This review covers only whether the device/timing layer
is now sound.

## Behaviour that changed, and the invariants that must still hold

New or changed observable behaviour:

1. A clip with no detectable sound reports `leading_silence_s = None`, and no
   audible-onset estimate is produced for it. The onset estimate is the explicit
   sum of commit delay, device offset and clip lead, each recorded separately.
2. Gap detection and the sample/time mapping run on PortAudio's own block clock
   when the host API provides it (2 ms tolerance), falling back to
   callback-entry time with an 80 ms tolerance and recording which basis was
   used.
3. Audio the recorder could not persist is recorded as a `counted` gap and is
   never added to the timeline's written-frame count; delivered and persisted
   counts are reconciled at `finalize()`.
4. `integrity()["continuous"]` is true only when frames exist, no gap exists,
   no clock anomaly occurred, and delivered equals persisted.
5. Nothing in the input callback can raise; a non-monotonic device timestamp is
   clamped and reported, a mid-stream change of timing method is a fault, and
   `check_liveness` lets a stalled capture be faulted during the trial.
6. `OutputPlayer.begin_attempt()` scopes prompt bookkeeping per attempt, and
   `cancel_candidate()` returns a four-way `CancelOutcome` whose
   `allowance_consumed` is true only for a committed prompt.
7. A hysteresis-band frame moves the silence origin; `PauseTimer` refuses to be
   eligible for a deadline discovered more than `lateness_budget_s` late.

Invariants that must still hold (round-1 reviewers confirmed all of these held
before the changes; the question is whether they still do):

- No output before the eligibility deadline, and none before participant speech
  has been detected.
- The configured waiting interval is added exactly once, to the speech offset
  and never to the confirmation time.
- A cancellation before commitment removes the clip; commitment consumes the
  allowance and is reported as such.
- The recording keeps exactly the frames the device delivered; sample indices
  map back to controller time across a gap.
- No code path can produce an `Estimate` with `method="measured"`.
- `os.replace` publication stays atomic; `start()` refuses to record over an
  existing `.partial`.

## Snapshot identity

- Repository: `C:/Users/suraj/Downloads/Tanuki`, branch `main`.
- Base commit: `eeb0f0e2f4da98cf1e2cfade27a3c49a4b840479`. **Nothing is
  committed.** The reviewed files are staged-but-uncommitted or untracked, so
  the commit hash captures none of this work; use the digests below.
- `git status --porcelain` at packet time shows `A`/`AM` entries for the
  reviewed files, `M` for `DEVELOPMENT_STATUS.md`, `README.md` and
  `reviews/INDEX.md`, and `??` for `reviews/M1-audio-001/resolution.md`. The
  staging was not performed by the coordinator (see the snapshot note in
  resolution.md) and the index was deliberately left as found.

| Path | Role | SHA-256 |
|---|---|---|
| `timing.py` | implementation | `3a8240561b68780196a303d074c6a9c477b360699045c172594ed21078667e3a` |
| `audio_io.py` | implementation | `9363bcc67ac03d61090c518f6cc665657a073accb1afbd3cc7280c6f812b97ed` |
| `tools/check_audio.py` | tool | `fed019d75fd5aab1bb30f82b001f0db21c52eecf43a17906785d68c13311c40e` |
| `requirements.txt` | dependencies | `d1f186aabdb10aafa65a2bda5cbc5d0dec5b3931bf0bb260180e79517fa8d59a` |
| `decisions.md` | rationale | `d6167795f402f52c2f05f4b30fb86ed2aa7fb0d9ba5cc711236f15e6497caeef` |
| `.gitignore` | config | `64371dbd6c0b6e3b4aec314f7be3f2bd153e4185fc494721d06bc42bf20fab49` |
| `tests/test_timing.py` | test | `822b9a1e565c82d1989e5e5d4536341036f109a7f34f39874afbded5830568b7` |
| `tests/test_audio_io.py` | test | `e23b928e2be169615f5ce3d8bed4a07be30f696362788377a0b52b6947e4e50d` |
| `validation/audio_spike.md` | evidence | `1b932493355b697a18c427c52394a2fcaed92aeec4e67709fc29b8d645f0b67a` |
| `validation/audio_check_survey.json` | evidence | `ab2f21b5804a6d61d4700b477acf6afba4de90de30b57a04edd1e9e8fd8f1fda` |
| `validation/audio_check_commit_wasapi.json` | evidence | `9029d6439b81354113f9a71ce14f3dae1cc77b429ee0addf4efae3c41501b1e6` |
| `validation/audio_check_commit_default.json` | evidence | `77f1934ff0291631b7640538e0e296fba1ff3a7d417adee261ffcd3d4a114cb4` |
| `validation/audio_check_wasapi.json` | superseded evidence | `bc7f70065e4475349d077d83a0b0fe18cb14d8d5f2f779222ca5e5b0724e546b` |
| `validation/audio_check_playback.json` | superseded evidence | `e203bf2e1069d8cacc320ed4f6788f60b472c4416a29aa659ca507d8e9b90ae3` |
| `reviews/M1-audio-001/resolution.md` | fix record | `36e474df9ea09aa4dbb86d27aa4f51330f66effb94933ec4e837452e09a3725d` |

The two `audio_check_wasapi.json` / `audio_check_playback.json` files are
**unchanged from round 1 and superseded**: they hold the single-shot
`--playback` runs whose figures must not be quoted as results. They are kept
for auditability and are listed so their digests can be confirmed as unchanged.

Target edits are paused for the duration of this review. Recheck these digests
on return and mark affected coverage stale if any differ.

## Acceptance checks and actual evidence

Environment for every row: Windows 11 Education 10.0.26300 x64, Python 3.13.9
(Anaconda), numpy 2.3.5, sounddevice 0.5.5, PortAudio V19.7.0-devel, working
directory `C:/Users/suraj/Downloads/Tanuki/09_nemotron`.

| Requirement | Check | Status | Result | Limitations |
|---|---|---|---|---|
| All round-1 fixes regress-tested | `python -m unittest discover -s tests -p "test_*.py"` | PASS | **113 tests OK**, 0.29 s (80 before; 33 added) | Fake backend, manual clock; no device |
| Tool honest about missing evidence | `python tools/check_audio.py` | PASS | 8 PASS, 2 NOT_RUN, verdict `INCOMPLETE` (was `PASS`) | Opens no stream |
| C1 corrected onset, WASAPI | `--commit-trials 40 --device 8` | PASS | 0/40 early; commit p95 10.32 ms; device offset 10.00 ms; clip lead 10.00 ms; onset p95 30.32 ms | Device-latency estimate, **not acoustic** |
| C1 corrected onset, default | `--commit-trials 40` | FAIL vs candidate target | onset p95 190.90 ms; device offset 171.03 ms | The device choice is the finding; target is a proposal |
| Host-API comparison | `--survey` | PASS | WASAPI 22.0 / MME 180.0 / DirectSound 240.0 / WDM-KS 40.7 ms | 1 s per device, silence only, no load |
| Capture on this PC | `--duplex --allow-microphone` | **BLOCKED** | no default input device; two non-default WDM-KS Bluetooth endpoints exist | Hardware gap |
| Measured acoustic onset | — | **NOT_RUN** | needs a recorded playback reference | Every onset figure is `estimated` |
| Detector boundary error on real speech | — | **NOT_RUN** | Silero VAD not integrated (M3) | Tests drive probabilities directly |
| Echo / leakage, completion suppression at 0.5 s, renderer avatar clock, drift over a session, behaviour under load | — | **NOT_RUN** | require hardware, M3 or M4 | — |

Raw tool output is in the `validation/audio_check_*.json` files above. The
reproduce commands are listed verbatim at the top of
`validation/audio_spike.md`.

Failed attempts during this round, kept rather than hidden:

- The first corrected probe used an amplitude below the onset-detection floor,
  so `commit_distribution` correctly refused to run (`probe clip has no
  detectable onset`) and the measurement had to be redone with a faintly
  audible tone. The refusal is the new guard working.
- A new test (`test_frames_after_a_writer_failure_are_recorded_as_lost`)
  initially failed, revealing a residual case the reviewers' proposed fix did
  not cover: blocks already queued when a writer dies have already been
  counted. `finalize()` now reconciles delivered against persisted frames and
  records the shortfall as a counted gap plus a `recording_shortfall` fault.
- Two existing tests failed by design after the stricter contracts landed
  (`continuous` now requires persistence confirmation; `anchor` no longer
  raises) and were rewritten to the new behaviour.

## Reviewer permissions

- Default: read-only inspection of the manifest files, their imports,
  `goal.md`, `AGENTS.md`, `EGM_WORKFLOW.md`, the round-1 reports and
  `resolution.md`.
- Explicitly allowed, after you have inspected what it does:

  ```text
  python -m unittest discover -s tests -p "test_*.py"
  python tools/check_audio.py
  ```

  Run from `C:/Users/suraj/Downloads/Tanuki/09_nemotron` with
  `PYTHONPYCACHEPREFIX` pointing at your own scratch directory. Neither opens
  an audio stream; the suite writes only into a `tempfile` directory.
  **Do not** run `tools/check_audio.py` with `--playback`, `--survey`,
  `--commit-trials` or `--duplex`: those touch real devices and `--playback`
  makes sound. Ask the coordinator to re-run one if you need it.
- Isolated scratch: your own directory under the system temp directory. Do not
  write inside `09_nemotron` except your report file.
- Prohibited: editing any manifest file, installing dependencies, downloading
  anything, starting services, live microphone capture, real participant
  records (none exist).

## Questions this review should answer

1. Is each of C1-C8 actually fixed, by the mechanism `resolution.md` claims,
   and does its named test genuinely fail without the fix?
2. Did any fix break an invariant that held in round 1 — particularly the
   no-early-output guarantee, the add-the-interval-once guarantee, and
   atomic publication?
3. C7 replaced a tolerance change with a clock-domain change. Is the
   device-clock basis sound, is the minimum-biased offset estimator safe
   against a monotonicity violation in the mapping, and is the 80 ms fallback
   tolerance honest about what it cannot detect?
4. C6 corrects the silence origin *and* adds a staleness guard. Is that
   redundant, or do both carry weight? Does either change what the 0.5/1.0/2.0 s
   conditions mean in a way that should be a research decision rather than an
   engineering one?
5. Does `validation/audio_spike.md`, `decisions.md` or `resolution.md` still
   overstate anything, and are the superseded figures clearly marked as
   superseded rather than quietly removed?
6. Are the two deferrals (C12, C16) legitimately deferrable with the owners and
   affected gates named, or does either block the M3 controller work that would
   build on this layer?
