# Review packet — M1-audio-001

## Identity and requested review

- Checkpoint ID: `M1-audio-001`
- Created: 2026-11-17, Asia/Tokyo
- Route/stage/lenses: focused route (`EGM_WORKFLOW.md` section 4) with a second
  independent specialist lens. Lenses from section 5: **"Audio feasibility,
  M1"** and **"Recording/storage, M3/M6"** (the recording path is implemented
  here even though the controller is not).
- Reviewer IDs and unique output destinations:
  - `R01`, stage `focused`, output
    `reviews/M1-audio-001/goldfish-focused-R01-round-1.md`
  - `R02`, stage `critic`, output
    `reviews/M1-audio-001/goldfish-critic-R02-round-1.md`
- Requested verdict scope: is this timing/device layer sound enough to build the
  M3 experiment controller on, and is the recorded evidence described
  accurately? Specifically **not** asked: participant readiness, acoustic
  validation, or approval of any research decision.
- Goal version and sections: `goal.md` v0.3; sections 4, 5, 6, 7, 10, 12 and
  13 (experiment release checklist).
- Actual implementation status: device/timing layer only. There is no
  experiment state machine, no VAD integration, no stimulus manifest, no
  server, no UI and no browser code in this checkpoint.
- Open research gates (deliberately unsettled, see `goal.md` section 14):
  recall-cap origin, completion procedure, event precedence, rearming,
  early-speech and overlap policies; detector profile values; measured timing
  tolerance and calibration method; device models. These block the material
  freeze and participant deployment, not this synthetic engineering slice.

## Expected behaviour and change boundaries

The requirement is `goal.md` section 1 "M1 — audio feasibility": select and pin
audio dependencies, and establish on this PC that native capture, playback,
clock mapping and completion handling can meet the protocol's timing rules.

Observable behaviour this checkpoint adds (previously nothing existed under
`09_nemotron` but documents):

1. A controller-time/sample-position timing core. A silence deadline is
   `end of the last detected speech frame + configured threshold`, computed in
   exactly one place, with the detector's confirmation delay recorded separately
   and never folded into the interval.
2. A continuous recorder that writes every frame the device delivered, surfaces
   dropped input frames as flagged timeline gaps rather than padding the audio,
   and publishes by rename so an attempt that never finalised stays detectable.
3. An output player holding one session-long stream, which starts story and
   instruction clips immediately and *arms* the encouragement against its
   deadline. The clip reaches the device only inside the callback that first
   observes `now >= deadline`, and only if a controller-supplied guard still
   permits it.
4. Every time value derived from device latency is tagged `estimated`; nothing
   in this code can produce a value tagged `measured`.

Invariants that must remain true:

- No output before the eligibility deadline, and none at all before participant
  speech has been detected.
- The configured waiting interval is added exactly once.
- A cancellation before commitment removes the clip; after commitment the
  attempt is consumed and reported as such, never retried.
- The recording keeps exactly the frames the device delivered; sample indices
  map back to controller time across a gap.
- A scheduling timestamp is never presented as an acoustic measurement.

Files created (all new; nothing was modified or deleted):

| Path | Role |
|---|---|
| `timing.py` | implementation — clocks, capture timeline, segmenter, pause timer, playback position |
| `audio_io.py` | implementation — device inventory, backends, recorder, output player |
| `tools/check_audio.py` | bench tool — inventory, synthetic checks, real-device measurements |
| `requirements.txt` | pinned dependencies with the measured environment |
| `decisions.md` | engineering decision record (D1–D8) |
| `.gitignore` | keeps recordings, runtimes, models and partial files out of Git |
| `tests/test_timing.py` | 43 tests |
| `tests/test_audio_io.py` | 37 tests |
| `validation/audio_spike.md` | executed evidence, including NOT_RUN/BLOCKED items |
| `validation/audio_check_*.json` | raw tool output for the runs cited in the spike record |

Read-only baseline dependencies (not modified, not required at runtime by this
checkpoint):

- `../08_avisspeech/src/tanuki-lipsync.js` — `playTrack(track, getTime)` and
  `stop()` are the contract `PlaybackPosition`/`interpolate` are designed to
  feed. Relevant lines: `playTrack` at 294, the track-mode branch of `update`
  at 198-204, `stop` at 459.
- `../08_avisspeech/requirements.txt`, `server.py` — prior-art only.

Out of scope for this review: the experiment state machine, Silero VAD
integration, stimulus preparation and manifests, the HTTP server and its access
control, the browser adapter and renderer snapshot, transcription/scoring, and
anything concerning Nemotron.

## Snapshot identity

- Repository: `C:/Users/suraj/Downloads/Tanuki`, branch `main`.
- Base commit: `eeb0f0e2f4da98cf1e2cfade27a3c49a4b840479`
  ("n2: updated elpehant and goldfish").
- Working-tree state: **every reviewed file is untracked.** `git status
  --porcelain` shows `?? 09_nemotron/.gitignore`, `?? 09_nemotron/audio_io.py`,
  `?? 09_nemotron/decisions.md`, `?? 09_nemotron/requirements.txt`,
  `?? 09_nemotron/tests/`, `?? 09_nemotron/timing.py`,
  `?? 09_nemotron/tools/`, `?? 09_nemotron/validation/`. The commit hash alone
  therefore captures none of this work; use the digests below.

| Path | Role | SHA-256 |
|---|---|---|
| `timing.py` | implementation | `d763a6906f975dbd7000e1d799f722b30e3642d2b4ef3ad77446fa145dad32a0` |
| `audio_io.py` | implementation | `5b674c2450f8eb83858842f9fe7a3a33263a0b67b80d762c468394c509944686` |
| `tools/check_audio.py` | tool | `e3025915624852e046bd0def70aa30641aa124074b8735a5d41ed16427b37a6f` |
| `requirements.txt` | dependencies | `5b95c1de73cbf0e8fcc7578a067787d82ad6bada8d97df185f3955876b179567` |
| `decisions.md` | rationale | `54b0fa7c754ef4e221888bed60583c7c194617a19ee683b571f902cc26cf270d` |
| `.gitignore` | config | `60945863813c1de2b96e82da83a98fe116bf73785154c15935c56f0fa9bd96f4` |
| `tests/test_timing.py` | test | `1c05c5a5ca50ea1547f624576f8c0f1cd03998c70653fd7afe58c76a6ea49dab` |
| `tests/test_audio_io.py` | test | `c531217a9efcf7d9a17742c0048c88ee52e5808f778470bd9270b0db5365bd36` |
| `validation/audio_spike.md` | evidence | `ce100336fb9dde30c87fa68053eb4a533edd98919a7f78c7c07f6dafbc034f48` |
| `validation/audio_check_survey.json` | evidence | `2443794c5086b9948ce6d4bb74bffc355c7cae4f8da1948905e7a61d181e4361` |
| `validation/audio_check_commit_wasapi.json` | evidence | `c2395aa3c9333ef4453a07451078c2129ad13bc8856f40a5987da278fb27b14c` |
| `validation/audio_check_commit_default.json` | evidence | `f00ea4131f7506ebbe5529f369c8ef27681a4a769eabdeb65925fb8689091f3e` |
| `validation/audio_check_wasapi.json` | evidence | `bc7f70065e4475349d077d83a0b0fe18cb14d8d5f2f779222ca5e5b0724e546b` |
| `validation/audio_check_playback.json` | evidence | `e203bf2e1069d8cacc320ed4f6788f60b472c4416a29aa659ca507d8e9b90ae3` |

Target edits are paused for the duration of this review. Recheck these digests
when you return and mark affected coverage stale if any differ.

## Acceptance checks and actual evidence

Runtime environment for every row: Windows 11 Education 10.0.26300 x64,
Python 3.13.9 (Anaconda), numpy 2.3.5, sounddevice 0.5.5, PortAudio
V19.7.0-devel, working directory `C:/Users/suraj/Downloads/Tanuki/09_nemotron`.

| Requirement | Check | Status | Evidence / result | Limitations |
|---|---|---|---|---|
| §6 no prompt before speech; §13 no pre-speech trigger | `python -m unittest discover -s tests -p "test_*.py"` | PASS | 80 tests OK in 0.142 s | Fake backend, manual clock; no device |
| §6 threshold added once, not hangover+timer | same suite, `test_threshold_is_added_once_to_the_real_speech_offset` | PASS | deadline = offset + threshold exactly | Synthetic probabilities, not real VAD output |
| §6 cancel before commit / consumed after commit | same suite, `OutputPlayerTest` | PASS | cancelled candidate emits only silence; post-commit cancel returns False and logs `prompt_cancel_too_late` | Fake backend |
| §6 terminal conditions re-checked at commitment | same suite, guard tests | PASS | guard veto and guard exception both stay silent | Guard contract is asserted, not yet used by a controller |
| §13 recording continuous through overlap | same suite, `RecordingContinuesThroughPromptTest` | PASS | 9600 frames, 0 gaps, speech present after commit sample | Synthetic constant-amplitude "speech" |
| §13 dropped-frame detection | same suite, gap tests | PASS | 0.25 s stall → one gap, 12000 frames lost (estimated), file still 9600 frames | Lost count is an estimate |
| §13 flagged recoverable attempt on storage failure | same suite, `test_a_write_failure_is_a_fault_...` | PASS | 960 frames published + `recording_write_failed` fault | Injected sink failure, not a real disk fault |
| §4 manifest-pinned audio, no substitution | same suite, `ClipTest` | PASS | hash and rate mismatches raise `AudioFault` | — |
| §7 avatar clock in file time with stale-update fault | same suite, `AvatarClockTest` | PASS | position clamps to written frames; stale snapshot raises | Not tested against the real renderer |
| §7 estimate vs measurement never conflated | same suite, `EstimateProvenanceTest` | PASS | no code path produces `method="measured"` | — |
| M1 device inventory | `python tools/check_audio.py` | PASS | `capture_available=false`, `playback_available=true`; 4 host APIs, 20 devices | Opens no stream |
| M1 capture on this PC | `--duplex --allow-microphone` | **BLOCKED** | no default input device (`sd.default.device == [-1, 1]`) | Hardware gap, see `audio_spike.md` Finding 1 |
| §7 playback delay after the deadline | `--commit-trials 40 --device 8` | PASS | 0/40 early; commit p95 10.13 ms; estimated onset p95 70.13 ms | Device-latency estimate, **not acoustic** |
| §7 same, default device | `--commit-trials 40` | **FAIL** vs candidate target | estimated onset p95 232.78 ms against a 100 ms candidate target | The target is a proposal; the device choice is the actionable finding |
| M1 host-API comparison | `--survey` | PASS | WASAPI 22.0 ms vs MME 180 ms, DirectSound 240 ms, WDM-KS 40.7 ms | 1 s per device, silence only, no load |
| §7 measured acoustic onset | — | **NOT_RUN** | requires a recorded playback reference; no input device | Every onset figure here is `estimated` |
| §7 last-speech-to-audible-response | — | **NOT_RUN** | requires capture | — |
| §7 detector boundary error on real speech | — | **NOT_RUN** | Silero VAD not integrated (M3) | Current tests drive probabilities directly |
| §7 echo / playback leakage | — | **NOT_RUN** | requires simultaneous capture and output | — |
| §6 completion suppression at 0.5 s | — | **NOT_RUN** | requires the controller (M3) and operator UI (M4) | — |

Raw tool output for every executed device measurement is in the
`validation/audio_check_*.json` files listed in the manifest. The commands are
reproduced verbatim at the top of `validation/audio_spike.md`.

Failed attempts during development, kept rather than hidden: four defects were
found by these tests and fixed before this packet (logging keyword collision
raising `TypeError` inside the audio path; post-commit cancellation
indistinguishable from "nothing armed"; fake-backend clock double-advancing
with two concurrent streams; unguarded ledger payload able to relabel an
event). One test assertion was itself wrong (a rounded sample count) and was
corrected. These are described in `validation/audio_spike.md`; the current
suite passes with no known failures.

## Reviewer permissions

- Default: read-only inspection of the files in the manifest, their imports,
  `goal.md`, `AGENTS.md`, `EGM_WORKFLOW.md`, and the read-only baseline files
  named above.
- Explicitly allowed test command, after you have inspected what it does:

  ```text
  python -m unittest discover -s tests -p "test_*.py"
  ```

  Run it from `C:/Users/suraj/Downloads/Tanuki/09_nemotron` with
  `PYTHONPYCACHEPREFIX` set to your scratch directory. It opens no device,
  uses no microphone, and writes only into a `tempfile` directory.
  `python tools/check_audio.py` (no flags) is also permitted: it opens no
  stream. **Do not** run it with `--playback`, `--survey`, `--commit-trials`
  or `--duplex`; those touch real devices and `--playback` makes sound. If you
  want one of those re-run, say so and the coordinator will run it.
- Isolated scratch/output/cache directory: your own under the system temp
  directory. Do not write inside `09_nemotron` except your report file.
- Prohibited: editing any file in the manifest, installing dependencies,
  downloading anything, starting services, live microphone capture, and real
  participant records (there are none; no research data exists yet).
- Requested report destination: the path listed against your reviewer ID above.
  If you cannot write, return the report text and the coordinator will store it
  unaltered.

## Questions the review should answer

Beyond the stage prompts in `reviewers/GOLDFISH.md`:

1. Is the deadline arithmetic right, and is there any path by which the
   configured waiting interval could be applied twice, or by which output could
   become audible before the deadline?
2. Is the commit boundary where `decisions.md` D1 claims it is? Can a
   cancellation race with commitment in a way that either speaks when it should
   not, or loses the record that it spoke?
3. Can the recording lose audio, or lose the sample-to-time mapping, without
   that being flagged? Is publish-by-rename actually crash-safe as claimed?
4. Does any claim in `validation/audio_spike.md` or `decisions.md` overstate
   what was executed — in particular the difference between estimated and
   measured onset?
5. Does anything here presuppose a research decision that `goal.md` section 14
   leaves open?

## Prior findings

None. This is the first implementation checkpoint and the first independent
review of code in `09_nemotron`. The earlier `ELEPHANT_GOLDFISH_REVIEW.md` is a
design review of the specification, and `reviews/WORKFLOW_VALIDATION.md` covers
the workflow documents; neither reviewed any code.
