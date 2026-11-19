# Combined review packet — M1-avatar-002 (first review) + M1-audio-001 round-3 fixes

Two scopes in one packet, deliberately, and they must be verdicted
**separately**:

- **Scope A — fix verification.** The five round-3 findings R04 raised against
  `M1-audio-001` (`R04-F01` … `R04-F05`) and the fixes applied to them. This
  closes the bounded loop in `EGM_WORKFLOW.md` section 8, which is at its
  three-iteration cap.
- **Scope B — first review.** `M1-avatar-002`: the minimal renderer snapshot
  and the browser clock adapter that drives
  `TanukiLipSync.playTrack(track, getTime)` from the controller's native
  playback clock. Never independently reviewed. This is the piece
  `goal.md` §7 requires and whose absence R01, R02 and R03 all noted as the
  reason M1 could not be complete.

They were batched at the user's explicit direction, to spend one reviewer
dispatch instead of two. Please keep the two verdicts distinct: a problem in
the avatar work should not reopen the audio checkpoint, and vice versa.

## Identity

- Checkpoint IDs: `M1-audio-001` (round 4 of review, scope A) and
  `M1-avatar-002` (round 1, scope B)
- Created: 2026-11-17, Asia/Tokyo
- Route/stage: focused route — **fix-verification** for scope A,
  **comprehension + critic** for scope B
- Reviewer ID and output: `R05`,
  `reviews/M1-avatar-002/goldfish-combined-R05-round-1.md`
- Goal version and sections: `goal.md` v0.3; §4-7, §9, §10, §12, §13
- Prior reports, all preserved unedited in `reviews/M1-audio-001/`:
  `R01` focused, `R02` critic (round 1), `R03` fix-verification (round 2),
  `R04` fix-verification (round 3). All four returned `NEEDS_FIXES`.
- Findings and fixes for every round: `reviews/M1-audio-001/resolution.md`.

## Scope A — the five round-3 findings

R04 verified **all ten** round-2 findings fixed (F02 partially: correct but
untested) and confirmed every round-1 invariant still held. It raised five new
findings. What was done:

| ID | Severity | R04's finding | Fix | Where to check |
|---|---|---|---|---|
| R04-F01 | Major | A timed-out commit probe left an armed candidate, so the *next* probe's `begin_attempt()` raised an unhandled `AudioFault` instead of a clean FAIL — in both `preflight.py` and `tools/check_audio.py` | Both loops now `cancel_candidate("probe_timeout")` and count timeouts; the existing "only N/M committed" check reports it with the count | `preflight.measure_output`, `check_audio.commit_distribution`; test `test_an_armed_candidate_must_be_released_before_the_next_attempt` |
| R04-F02 | Major | The round-2 clamp was exercised by no test; reverting it alone would not fail the suite | A test that isolates it, **verified by actually reverting the clamp and observing the failure** | `tests/test_timing.py::test_the_clamp_alone_keeps_the_mapping_monotonic` |
| R04-F03 | Minor | `is_participant_session` was read by no code | Now a blocking check requiring participant-grade configuration, with four tests | `preflight.check_participant_configuration`, `ParticipantConfigurationTest` |
| R04-F04 | Minor | The `FakeStream` epoch model and the F01 fallback round-trip had no `audio_io`-level coverage | Two integration tests through the real recorder | `DeviceClockIntegrationTest` |
| R04-F05 | Minor | `decisions.md` D8 still said 113 tests | Corrected | `decisions.md` D8 |

Found while fixing F01 and also fixed: `preflight.py` still contained the
`(cand.device_offset_s or 0.0)` pattern that R03-F10c removed from the bench
tool. It is now a skip-and-count, and `onset_delay_target` reports `NOT_RUN`
with the skipped count when no probe yields an onset estimate.

**The F02 revert experiment, since it is the one claim worth checking.** The
clamp was disabled (`if False and …`), the suite re-run, and two tests failed:
`test_the_clamp_alone_keeps_the_mapping_monotonic` and
`test_a_fallback_run_between_device_timed_blocks_is_not_a_gap`. `timing.py` was
then restored and confirmed byte-identical by SHA-256. So R04's gap is closed,
and its assessment that *every* scenario reaching the clamp was covered
elsewhere was slightly pessimistic — the fallback test does reach it — but it
was right that nothing isolated it.

## Scope B — the avatar clock adapter

### What it is for

The controller owns playback (`goal.md` §5): audio leaves the PC through
PortAudio and the browser never plays the same clip. So the mouth has no local
`<audio>` element to read a time from. It receives `timing.PlaybackPosition`
snapshots and animates against them through
`TanukiLipSync.playTrack(track, getTime)`, which plays no audio itself.

`goal.md` §7 sets the requirements: `getTime` returns the audible position in
seconds relative to the start of the complete frozen WAV *including any file
offset*; updates are timestamped with bounded interpolation and an explicit
stale-update fault; and the adapter must call `stop()` on clip end, abort,
fault and disconnect, because an external-clock track does not finish by
itself. Existing mouth lead/offset settings are frozen and no browser
AudioContext compensation is added.

### The renderer snapshot

Copied from `../08_avisspeech`, which was **not modified**. 23 assets, 21.0 MB.
`model/` and `vendor/` are excluded by `.gitignore`; `asset-provenance.json` is
tracked and records source path, SHA-256 and byte count for each, so the
snapshot is verifiable and rebuildable without committing the bytes:

```text
python tools/verify_snapshot.py --baseline
```

The three.js addon closure was resolved by following relative imports from the
six addons `app.js` uses: 11 files, 158 KB, instead of the 29 MB vendor tree.

### Three design decisions, and two of them were forced by a test

`decisions.md` **D9** records that the adapter extrapolates from *snapshot
arrival*, not from `controller_time` — that field is a `perf_counter` reading
in another process, and mapping the clocks would mean estimating an offset
across the very transport whose latency is unknown. The cost is a mouth that
lags by the transport latency; it is stated, never subtracted out, and
currently unmeasured because no transport exists yet.

**D10** records two fields added to `PlaybackPosition` *because a
cross-language check caught the renderer guessing*:

- `pre_roll_s` — frames handed to the device are not audible until they clear
  its buffer, so the audible position stays zero for the first
  output-latency of a clip. Linear extrapolation moved the mouth through that
  window, running ~20 ms ahead of the sound at the start of **every** clip.
- `ended_reason` — an idle snapshot carries no clip, so `file_time` and
  `duration` are both zero whether the clip finished or was stopped. The
  adapter had been inferring completion from `file_time ≈ duration`, which
  cannot work. An absent reason now maps to "stopped", never "completed".

### The cross-language check

`tools/make_position_trace.py` drives the real `OutputPlayer` on the fake
backend, samples `position()` every 10 ms, and writes a trace in which only
every fifth sample is delivered to the adapter. The rest are assertions the
adapter must reach by extrapolating, with the controller's own position as the
expected value. Current fixture: 52 frames, 12 delivered, 44 asserted.

It failed twice on first run, and both failures were the real contract defects
above rather than test bugs. Hand-written fixtures on both sides would have
agreed with each other and been wrong together. **Please check whether this
construction actually earns that claim** — specifically whether
`expect_file_time` is genuinely independent of the adapter's own formula.

## Snapshot identity

- Repository `C:/Users/suraj/Downloads/Tanuki`, branch `main`.
- Base commit: `ae435bf31fd6b5256a99ee00e2e95737e1597fa5` ("m1: avatar
  render"). The user has been committing throughout
  (`a2db26f round1fixes`, `51f6fe0 m1: avatar`, `ae435bf m1: avatar render`);
  the coordinator has made no commits.
- `git status --porcelain`, verbatim:

  ```text
   M 09_nemotron/decisions.md
  ?? 09_nemotron/validation/avatar_clock.md
  ```

  Those two carry the D9/D10 record and the avatar validation record, written
  after the last commit. Everything else in the manifest is committed.
- `find 09_nemotron -name "*.py" -o -name "*.js" -o -name "*.mjs" -o -name "*.json" -o -name "*.html"`
  (excluding `__pycache__`, `model/`, `vendor/`) returns exactly the files
  below. `model/` and `vendor/` are covered by `asset-provenance.json`.

| Path | Role | SHA-256 |
|---|---|---|
| `timing.py` | implementation | `81d7c9ff71d4fff403c17c2af14b997d6e8401b855d1b46cdcdae9b4f0a84599` |
| `audio_io.py` | implementation | `5d10d9f20eff72284da517a8b90de1e8ccfdbd37eaa2a99b142277b57638cbf9` |
| `preflight.py` | implementation | `7deaa6c93609c438096a67d534a16d13eb8b96e2ad32a2c838f472c790240b8d` |
| `src/clock-adapter.js` | implementation — **scope B, new** | `0a7e75725a6b8b3da1662f28bf959183a4853f1f600314c03fc1eb8eb89ed455` |
| `asset-provenance.json` | snapshot provenance — **new** | `f7bec2554d8d911acdf5dc269786dd5e639aa385b236f42b8ca90b550d4f82d2` |
| `config/experiment.json` | configuration | `a1f3b16aceb0139b0e4fbbf7a84efad4913f34d3abd06788ee7fb15efe6c4bce` |
| `requirements.txt` | dependencies | `d1f186aabdb10aafa65a2bda5cbc5d0dec5b3931bf0bb260180e79517fa8d59a` |
| `decisions.md` | rationale (D1-D10) | `9661d04a47804de98316fd1d53ce49de6609a7f85863e63ece25bde15a531004` |
| `.gitignore` | config | `64371dbd6c0b6e3b4aec314f7be3f2bd153e4185fc494721d06bc42bf20fab49` |
| `tools/check_audio.py` | tool | `9c4f7bf8e72064fb28246c427b56f1a48696f718c8ab0b7ab843d2684046f61a` |
| `tools/verify_snapshot.py` | tool — **new** | `a31def7deff2d5c89756e472a871e8bdab68a36e5e65efa0a15936b823621555` |
| `tools/make_position_trace.py` | tool — **new** | `2e87995137007dccf1145046234db7406a61c2e0d2635f5c7920f9484f9b3d36` |
| `tools/avatar_clock_check.html` | bench harness — **new, NOT RUN** | `05328009a1c529e9b80476ba2ec453ea310e2d9541c3e58fbe9752c2d9f52909` |
| `tests/test_timing.py` | test (75) | `60e0aeaf7fc9209952f8917637e8dcdc989bdb014462d129d79e8c4ee055297d` |
| `tests/test_audio_io.py` | test (56) | `2ebb3857be394b6a6ab770f73e2670eded12a2765c6cd51a69767435e0bb9330` |
| `tests/test_preflight.py` | test (30) | `ce8f9cd25a90a2f1eb42baed957606c103001393e96d95ec6b86b27ede58851d` |
| `tests/test_clock_adapter.mjs` | test (21) — **new** | `2fcf6195b93421b5f3ce23c6a2759ee0cecba3c6e35ddb21b2471c220b02d86c` |
| `tests/fixtures/position_trace.json` | generated fixture — **new** | `29854058020ce491be1e6a4ad2b0e4076796dd48bc8a94204d14baa907d83fcf` |
| `validation/audio_spike.md` | evidence | `d60bb74f8fd162a8988da2d2e4d3dc8e89526c01339535159f0a3c0cb3b55d47` |
| `validation/avatar_clock.md` | evidence — **new** | `1cfac8858f1c988e5425566aab6b339cf2d983aa1b02f53f94dad7ff5c43540c` |
| `validation/preflight_wasapi.json` | evidence | `bbf7b5f0e009bde57ab08c3c1f553024f64a6fc49427a4d3d1f9724c8e9d2529` |
| `validation/audio_check_survey.json` | evidence | `9e146c5eae789024b7847d3bca89675358a8d52a3d09e5156b14b71e5cc16a90` |
| `validation/audio_check_commit_wasapi.json` | evidence | `13366f9df18cdd5b80eb86d791b7b884160641c5d3a16be0c2d86d3dd318a698` |
| `validation/audio_check_commit_default.json` | evidence | `1941d67b73bf96d7d09b46e3f394ddcbd23f65697ba3dc091be34faf0086007a` |
| `validation/audio_check_wasapi.json` | superseded, marked in-file | `bdadda1f23a96e3f023cc7fb74229805b45490735c8534c3a3e0e3f99960e47b` |
| `validation/audio_check_playback.json` | superseded, marked in-file | `8033cace27ec024cd45cbcabe69146dc215c44e25a29fb6dc6cd2b2513edbd6f` |
| `reviews/M1-audio-001/resolution.md` | fix record, rounds 1-3 | `d31ef3dacd93480406a791a6b8ef90ac64ce54234a0b1ac430cde9ed747a7ff0` |

Renderer sources copied from the baseline and **not modified** by this work;
listed so you can confirm they are untouched baseline code rather than
something edited in passing:

| Path | SHA-256 |
|---|---|
| `src/tanuki-lipsync.js` | `98e9a9a91cde2f4fe12d66784fa78cb4e0ecffe23b8e051d7c3d04a5aa1f5b32` |
| `src/body.js` | `af2a91110dd962ad7192da4d5ccf66b8b3a0e87c69886dede9d8590173789060` |
| `src/bands.js` | `c7642c898e7b2233618750b5a52c0433c5146c67ca0dbfa7591a9dc1f775f140` |
| `src/formants.js` | `f06e20d86b53a044aa134826239d35b888e96ed1b6acb5b7371d0a4517d5ec05` |
| `src/quality.js` | `429e5de262c5a6b5291e7928bf618abd766d4814df32c1a8fad97d00a8f31a9c` |

Target edits are paused for this review. Recheck these digests on return and
mark affected coverage stale if any differ.

## Acceptance checks and actual evidence

Environment: Windows 11 Education 10.0.26300 x64, Python 3.13.9, numpy 2.3.5,
sounddevice 0.5.5, PortAudio V19.7.0-devel, **Node v24.14.0**, from
`09_nemotron`. All device measurements were taken over a TeamViewer remote
session and must be repeated at the physical machine.

| Requirement | Check | Status | Result |
|---|---|---|---|
| Scope A regress-tested | `python -m unittest discover -s tests -p "test_*.py"` | PASS | **161 tests OK**; per file 75 + 56 + 30 |
| Scope B adapter logic | `node --test tests/test_clock_adapter.mjs` | PASS | **21 tests OK** |
| F02 clamp genuinely covered | clamp disabled, suite re-run, `timing.py` restored and hash-checked | PASS | 2 tests fail with the clamp out; hash identical after restore |
| Snapshot provenance | `python tools/verify_snapshot.py --baseline` | PASS | 23/23 assets match, 21.0 MB; 5 tracked, 18 hash-only |
| Cross-language contract | `python tools/make_position_trace.py` then the JS suite | PASS | 52 frames, 12 snapshots, 44 asserted positions |
| Tool honest about missing evidence | `python tools/check_audio.py` | PASS | 8 PASS, 2 NOT_RUN, verdict `INCOMPLETE` |
| Preflight on real hardware | `python preflight.py --config config/experiment.json --trials 20` | PASS (ran) | pinned WASAPI resolved; onset p95 30.90 ms; `participant_configuration` NOT_RUN; mic not opened |
| §7 adapter against the **real renderer** | `tools/avatar_clock_check.html` | **NOT_RUN** | Needs an operator with a browser. Not opened |
| §7 visual synchronisation | — | **NOT_RUN** | Nothing here plays audio; no claim follows from a pass |
| §7 acoustic onset | — | **NOT_RUN** | No acoustic reference channel; no input device |
| Real transport latency and jitter | — | **NOT_RUN** | No server yet (M3/M4); snapshots came from a file |
| `playTrack` under a real frame loop | — | **NOT_RUN** | Node tests call `getTime()` directly |
| Microphone capture | `--duplex --allow-microphone` | **BLOCKED** | No default input device; two WDM-KS Bluetooth endpoints |

Failed attempts during this work, kept rather than hidden:

- The cross-language trace failed on first run at frame 1 (adapter 0.01,
  controller 0.0) — the pre-roll defect. Fixed by publishing `pre_roll_s`.
- It then failed on the stop reason (`requested` vs `clip_end`) — the
  `ended_reason` defect. Fixed by publishing `ended_reason`.
- `node --test tests/` tried to load the Python test files as modules; the
  command is `node --test tests/test_clock_adapter.mjs`.
- The probe amplitude for `commit_distribution` was once set below the
  onset-detection floor, so the tool correctly refused to run.

## Reviewer permissions

- Default: read-only inspection of the manifest files, their imports,
  `goal.md`, `AGENTS.md`, `EGM_WORKFLOW.md`, the four earlier reports and
  `resolution.md`. `../08_avisspeech` is read-only baseline and may be
  inspected to confirm the snapshot is untouched.
- Explicitly allowed, after inspecting what they do:

  ```text
  python -m unittest discover -s tests -p "test_*.py"
  python -m unittest discover -s tests -p "test_timing.py"
  python -m unittest discover -s tests -p "test_audio_io.py"
  python -m unittest discover -s tests -p "test_preflight.py"
  node --test tests/test_clock_adapter.mjs
  python tools/check_audio.py
  python tools/verify_snapshot.py --baseline
  ```

  From `09_nemotron`, with `PYTHONPYCACHEPREFIX` pointing at your own scratch
  directory. None opens an audio device or records anything;
  `verify_snapshot.py` only hashes files.
- **Do not** run `tools/check_audio.py` with `--playback`, `--survey`,
  `--commit-trials` or `--duplex`; **do not** run `preflight.py` (it opens the
  output device and plays a faint tone); **do not** run
  `make_position_trace.py` (it would rewrite a manifest fixture under review).
  Ask the coordinator to re-run any of those.
- Isolated scratch: your own directory under the system temp directory. Write
  nothing inside `09_nemotron` except your report.
- Prohibited: editing any manifest file, installing dependencies, downloading,
  starting services, live microphone capture, real participant records (none
  exist).

## Questions this review should answer

**Scope A:**

1. Are R04-F01 … F05 fixed by the mechanisms described, and would each named
   test fail on revert?
2. Does the F01 fix actually close the crash, or merely move it? Can a probe
   still leave the player in a state the next `begin_attempt()` rejects?
3. Do the invariants hold that R03 and R04 both confirmed — no output before
   the deadline, the interval added exactly once, atomic publication, no
   `measured` estimate?
4. Is `check_participant_configuration` honest? It must not read as research
   authorisation, and it must not let a participant session run on development
   defaults.

**Scope B:**

5. Does the adapter meet §7 — file-time `getTime`, bounded interpolation,
   explicit stale fault, and `stop()` on clip end, abort, fault *and*
   disconnect? Is there any path where the mouth is left open or moving while
   the controller is silent or stopped?
6. Is D9 (extrapolate from arrival) sound, and is its unmeasured transport bias
   disclosed everywhere it matters?
7. Are `pre_roll_s` and `ended_reason` correctly computed on the Python side,
   and correctly consumed on the JS side? Does the pre-roll handling behave at
   the boundaries (zero, longer than the snapshot interval, mid-clip)?
8. Is the cross-language trace a real cross-check, or does
   `expect_file_time` restate the adapter's own formula?
9. Is the snapshot provenance mechanism adequate given `model/` and `vendor/`
   are untracked? Can a reader establish what bytes are in use?
10. Does anything in `validation/avatar_clock.md` or `decisions.md` D9/D10
    overstate what was executed — particularly around visual synchronisation,
    which is NOT_RUN?

## Still deferred, unchanged

**C12** (`.partial` reports zero frames after an abrupt kill), **C16**
(nothing binds `PromptCandidate.deadline` to `PauseTimer`) and **C18**
(publication atomic but not `fsync`-durable) — all to M3 with the developer as
owner. The M3/M6 crash-recovery gate stays unpassed. Research-owned decisions
are listed in `resolution.md`; none is settled here and no reviewer can settle
them.
