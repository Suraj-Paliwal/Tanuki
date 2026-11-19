# Fix-verification packet — M1-avatar-002 round 2 (R05 findings, both scopes)

**This is a recheck.** It carries earlier finding IDs and their dispositions,
as `EGM_WORKFLOW.md` §6 permits for fix verification.

Two scopes, verdicted **separately**, as in round 1:

- **Scope A — `M1-audio-001`.** R05 findings `M1-avatar-002-R05-F01` (Major),
  `F02`, `F03` (Minor) against the probe loops in `preflight.py` and
  `tools/check_audio.py`. The bounded loop in `EGM_WORKFLOW.md` §8 had reached
  its cap; the **user chose on 2026-11-20 to spend one more fix cycle** on
  these rather than carry F01 into M3.
- **Scope B — `M1-avatar-002`.** R05 findings `F04`-`F07` (Major) and
  `F08`-`F12` (Minor) against the clock adapter, the controller's published
  position, the cross-language trace and the snapshot provenance. `F13`
  (packet hygiene) is addressed by this packet itself.

A defect in one scope should not reopen the other.

## Identity

- Checkpoint IDs: `M1-audio-001` (scope A, fix verification after the user's
  extra cycle) and `M1-avatar-002` (scope B, round 2)
- Created: 2026-11-20, Asia/Tokyo
- Route/stage: focused route, **fix-verification** for both scopes
- Reviewer ID and output: `R06`,
  `reviews/M1-avatar-002/goldfish-fix-verification-R06-round-2.md`
- Goal version and sections: `goal.md` v0.3; §4-7, §9, §10, §12, §13
- Prior report under recheck: [R05](goldfish-combined-R05-round-1.md),
  preserved unedited. Earlier `M1-audio-001` reports R01-R04 are in
  `reviews/M1-audio-001/`.
- Findings, dispositions, fixes and revert checks:
  [resolution.md](resolution.md). Pointer from the audio record: round 4 of
  `reviews/M1-audio-001/resolution.md`.
- Written rationale available to any implementer: `decisions.md` D8 (wording),
  D9 (≈2L bias) and D10 (extended: starting clip, audible end, adapter
  lifecycle).

## Readiness question

For each scope: are the R05 findings fixed by the mechanisms described, would
the named tests fail on revert, and did the fixes introduce anything new?

## Intended behaviour being rechecked

**Scope A.** `audio_io.run_commit_probe` is now the single probe loop, used by
both callers. It must never leave the player in a state where the next
probe's `begin_attempt()` or `arm()` raises, unless it returns
`PROBE_STUCK`. The finish wait has its own bound. A `too_late_committed`
timeout cancel is `PROBE_COMMITTED_LATE`, counted as committed and waited
out. Both callers turn `PROBE_STUCK` and any probe `AudioFault` into a
blocking FAIL naming the trial. `SessionPreflight._report_probes` guards every
statistic by its list's emptiness.

**Scope B.**

- `OutputPlayer.position()` publishes a clip that has not reached a callback
  as *playing* at file time 0, with the reported latency as `pre_roll_s`.
- It keeps publishing *playing* through the audible tail after the last block
  is written, with a new `audible_end_s` field.
- `OutputPlayer.audible_end` gives the controller-time audible end.
- An explicit stop reports stopped at once.
- The adapter has `arm()`. The staleness clock starts at arm, stops are
  latched until the next arm, `generation` is required, a not-playing
  snapshot before the armed clip is seen playing is ignored, and a newer
  playing generation is a `superseded` stop.

## Snapshot identity

- Repository `C:/Users/suraj/Downloads/Tanuki`, branch `main`.
- Base commit: `ae435bf31fd6b5256a99ee00e2e95737e1597fa5` ("m1: avatar
  render"), the same base as R05. The coordinator has made no commits.
- `git status --porcelain` from the repository root, **complete and
  unfiltered** (R05-F13), taken at packet assembly:

  ```text
   M 09_nemotron/DEVELOPMENT_STATUS.md
   M 09_nemotron/README.md
   M 09_nemotron/asset-provenance.json
   M 09_nemotron/audio_io.py
   M 09_nemotron/decisions.md
   M 09_nemotron/preflight.py
   M 09_nemotron/reviews/INDEX.md
   M 09_nemotron/reviews/M1-audio-001/resolution.md
   M 09_nemotron/src/clock-adapter.js
   M 09_nemotron/tests/fixtures/position_trace.json
   M 09_nemotron/tests/test_audio_io.py
   M 09_nemotron/tests/test_clock_adapter.mjs
   M 09_nemotron/tests/test_preflight.py
   M 09_nemotron/tests/test_timing.py
   M 09_nemotron/timing.py
   M 09_nemotron/tools/avatar_clock_check.html
   M 09_nemotron/tools/check_audio.py
   M 09_nemotron/tools/make_position_trace.py
   M 09_nemotron/tools/verify_snapshot.py
  ?? 09_nemotron/reviews/M1-avatar-002/
  ?? 09_nemotron/tests/test_snapshot.py
  ?? 09_nemotron/validation/avatar_clock.md
  ```

  `git diff ae435bf -- 09_nemotron` gives the full working-tree change.
  **`DEVELOPMENT_STATUS.md`, `README.md`, `reviews/INDEX.md` and this packet's
  directory may change during the review window** (status bookkeeping). None
  of them is a manifest file or a dependency of reviewed code; **the digests
  below are the authority** for what is under review.
- The `find` over `*.py *.js *.mjs *.json *.html` (pruning `__pycache__`,
  `model/`, `vendor/`, `.preparation/`) returns exactly the 27 code/data files
  below plus `requirements.txt`, `.gitignore` and the Markdown records listed.

| Path | Role | SHA-256 |
|---|---|---|
| `timing.py` | implementation (`audible_end_s`; `interpolate` floor) | `872a4d871e5e95d3739c537c476b2653d02ea15ed6dec36d27e6bcab448e60f4` |
| `audio_io.py` | implementation (`run_commit_probe`; position start/tail; `audible_end`) | `6aa1469289b1c1a007fc9acb32d10a2829fcfb7a9d00ac5db5ca967429586ea6` |
| `preflight.py` | implementation (loop via helper; `_report_probes`) | `a3d113b4945dcf3fce81ff9cc42842f0786965cce996ce1587a53f1497f9d8c7` |
| `src/clock-adapter.js` | implementation (lifecycle) | `aa627a0c2bb60391dde9a74c3f0e6c54637dffa41bbc2642ef1eac9cfbadf190` |
| `asset-provenance.json` | snapshot provenance (closure root named) | `a42d4ec30d6bca5fc80917c53f5738d3cf5e374f721db8a6ede73876c864575b` |
| `config/experiment.json` | configuration, unchanged | `a1f3b16aceb0139b0e4fbbf7a84efad4913f34d3abd06788ee7fb15efe6c4bce` |
| `requirements.txt` | dependencies, unchanged | `d1f186aabdb10aafa65a2bda5cbc5d0dec5b3931bf0bb260180e79517fa8d59a` |
| `decisions.md` | rationale D1-D10 | `247f81c1ff1244671a1f6148c4522186b7e658c753558122411b7abb666597e7` |
| `.gitignore` | config, unchanged | `64371dbd6c0b6e3b4aec314f7be3f2bd153e4185fc494721d06bc42bf20fab49` |
| `tools/check_audio.py` | tool (loop via helper) | `f3d683f044f24a0401faa0c636fab36904df4d53dff493e926a0762549831ad1` |
| `tools/verify_snapshot.py` | tool (closure check) | `5578e874f1476c98bf299ee996061de868cd135f1df063647627176a69b19f98` |
| `tools/make_position_trace.py` | tool (frame 0 pre-callback; tail; `render`) | `0625bc0384ec543d12f9162b84568b6e9280f58e3503704fc3ec0cd41e192580` |
| `tools/avatar_clock_check.html` | bench harness (`arm()`; F04 check) — **NOT RUN** | `19a25ffa4ca8d9580e5f4c6579a7466f0817ee7d9cd4e5a453ccc6afe9d2c1ca` |
| `tests/test_timing.py` | test (77) | `d62b853ebc10dd6a70e93952fab0279b4826b790b7b54def2011241fcda4eb7c` |
| `tests/test_audio_io.py` | test (65) | `10d930738ac1fc6b17b77e2c0b7976a85380712e89479c65233aaafe0839ef3c` |
| `tests/test_preflight.py` | test (35) | `81d3a1035f1bca92c189a4032084a423cdeb5b73db614cea300acbf90d3df608` |
| `tests/test_snapshot.py` | test (3) — **new** | `7515a1454a7e49649c49a6eb5d309904d2982ee7af737baf68c28d13fb8c844a` |
| `tests/test_clock_adapter.mjs` | test (30) | `9851a0c2579c9790b88ed192ed961d41f99478da451991c7ed6f50d6b7ae09bc` |
| `tests/fixtures/position_trace.json` | generated fixture, regenerated | `b5797c7aebbf2913bde0a540c93f08a4339c216bf9d0f2478323e06ede0943ae` |
| `validation/audio_spike.md` | evidence, unchanged | `d60bb74f8fd162a8988da2d2e4d3dc8e89526c01339535159f0a3c0cb3b55d47` |
| `validation/avatar_clock.md` | evidence, re-executed | `3c210eb1db9504f12b3ee6d6f8c07824ca49146179174fe84bd38275479169b7` |
| `validation/preflight_wasapi.json` | evidence, unchanged | `bbf7b5f0e009bde57ab08c3c1f553024f64a6fc49427a4d3d1f9724c8e9d2529` |
| `validation/audio_check_survey.json` | evidence, unchanged | `9e146c5eae789024b7847d3bca89675358a8d52a3d09e5156b14b71e5cc16a90` |
| `validation/audio_check_commit_wasapi.json` | evidence, unchanged | `13366f9df18cdd5b80eb86d791b7b884160641c5d3a16be0c2d86d3dd318a698` |
| `validation/audio_check_commit_default.json` | evidence, unchanged | `1941d67b73bf96d7d09b46e3f394ddcbd23f65697ba3dc091be34faf0086007a` |
| `validation/audio_check_wasapi.json` | superseded, marked in-file | `bdadda1f23a96e3f023cc7fb74229805b45490735c8534c3a3e0e3f99960e47b` |
| `validation/audio_check_playback.json` | superseded, marked in-file | `8033cace27ec024cd45cbcabe69146dc215c44e25a29fb6dc6cd2b2513edbd6f` |
| `reviews/M1-audio-001/resolution.md` | fix record, rounds 1-4 | `5f8f59158e197a5561779ee37745f718489e9b77d275e22248a0bee24fde7076` |
| `reviews/M1-avatar-002/resolution.md` | fix record for R05 | `1cf170479480c1a393733d8968055820264284116c2193a4c4c421920c2fd8a3` |

Renderer sources copied from the baseline, **still unmodified** (identical to
the R05 packet's digests):

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
sounddevice 0.5.5, Node v24.14.0, from `09_nemotron`, 2026-11-20. The PC is
reached over TeamViewer; no device measurement was repeated in this cycle.

| Requirement | Check | Status | Result |
|---|---|---|---|
| Python regression | `python -m unittest discover -s tests -p "test_*.py"` | PASS | **180 OK** (77 + 65 + 35 + 3) |
| JS adapter | `node --test tests/test_clock_adapter.mjs` | PASS | **30 pass, 0 fail** |
| Tests fail on revert | scratch-copy reverts, listed in `resolution.md` | PASS | every listed revert fails; reviewed `preflight.py` reproduces R05-F01's exact `AudioFault` |
| Snapshot provenance as a closure | `python tools/verify_snapshot.py --baseline`; scratch file in `vendor/three/addons/` | PASS | 23/23, PASS, exit 0; stray file → `UNEXPECTED`, exit 1 (file removed afterwards) |
| Fixture in sync with controller | fixture-guard test in `test_audio_io.py` | PASS | regeneration in memory equals the committed bytes |
| Tool honest about missing evidence | `python tools/check_audio.py` | PASS | 8 PASS, 2 NOT_RUN, `INCOMPLETE`, exit 0 |
| `check_audio.py --commit-trials` after the refactor, real device | — | **NOT_RUN** | plays a faint tone; the shared helper is covered by tests, the tool's wrapper is not executed |
| `preflight.py` on real hardware after the refactor | — | **NOT_RUN** | same reason; covered on the fake backend by `ProbeLoopTest` |
| §7 adapter against the real renderer | `tools/avatar_clock_check.html` | **NOT_RUN** | not opened |
| Visual synchronisation, acoustic onset, real transport, real frame loop | — | **NOT_RUN** | as in R05 |
| Microphone capture | — | **BLOCKED** | no default input device |

Failed attempts during this cycle, kept rather than hidden:

- The first stuck-clip preflight test stalled the stream one poll before the
  commit could land, so it exercised a timeout instead. Its stall start was
  moved later, with a comment giving the poll arithmetic.
- The first timeout-race test kept the stream stalled through the finish
  wait and so produced `PROBE_STUCK`. The race hook now restores the stream
  when the audio thread "wins".
- The old JS test `a new clip generation restarts file time from zero` passed
  against the new adapter only vacuously, because `fileTime()` had never been
  called. It was replaced by an explicit supersede-then-arm test.

## Reviewer permissions

- Default: read-only inspection of the manifest files, their imports,
  `goal.md`, `AGENTS.md`, `EGM_WORKFLOW.md`, R05's report, both
  `resolution.md` files and `git diff ae435bf -- 09_nemotron`.
  `../08_avisspeech` is a read-only baseline.
- Explicitly allowed, after inspecting what they do:

  ```text
  python -m unittest discover -s tests -p "test_*.py"
  python -m unittest discover -s tests -p "test_<name>.py"
  node --test tests/test_clock_adapter.mjs
  python tools/check_audio.py
  python tools/verify_snapshot.py --baseline
  git status --porcelain
  git diff ae435bf -- 09_nemotron
  ```

  From `09_nemotron`, with `PYTHONPYCACHEPREFIX` pointing at your own scratch
  directory. None opens an audio device or records anything. The fixture-guard
  test regenerates the trace **in memory** and does not write the fixture.
- Revert experiments are allowed **only on a copy of the tree in your own
  scratch directory**, never in place.
- **Do not** run `tools/check_audio.py` with `--playback`, `--survey`,
  `--commit-trials` or `--duplex`. **Do not** run `preflight.py`, which opens
  the output device and plays a faint tone. **Do not** run
  `make_position_trace.py`, which writes a manifest fixture. Ask the
  coordinator to re-run any of those.
- Write nothing inside `09_nemotron` except your report.
- Prohibited: editing any manifest file, installing dependencies,
  downloading, starting services, live microphone capture.

## Questions this review should answer

**Scope A:**

1. Are R05-F01, F02 and F03 fixed? Can any probe outcome still leave the
   player in a state the next `begin_attempt()` or `arm()` rejects without
   that being reported? Is `PROBE_COMMITTED_LATE` handled honestly in the
   reported distributions?
2. Do the loop-level tests (`ProbeLoopTest`, `CommitProbeTest`,
   `ProbeReportingTest`) fail on revert as `resolution.md` claims?
3. Do the invariants R03-R05 confirmed still hold: no output before the
   deadline, the interval added exactly once, atomic publication, no
   `measured` estimate?

**Scope B:**

4. Are F04-F12 fixed? In particular: is there still any path where the
   mouth is left open or moving while the controller is silent or stopped,
   or torn down while a clip is genuinely starting or still audible?
5. Is the audible-end design (keep `playing` through the tail and publish
   `audible_end_s`; explicit stop still immediate) sound for both the mouth
   and M3's `instruction_audible_end`? Is `OutputPlayer.audible_end`
   correct in every state (pending, playing, tail, idle after clip end, after
   stop)?
6. Is the adapter lifecycle coherent? Consider:
   - `arm()` with and without `generation`;
   - a stop snapshot whose generation was bumped;
   - supersession;
   - ignored versus rejected snapshots;
   - whether ignoring a not-playing snapshot before the clip has been seen
     playing can hide a genuine clip end. For example, a clip so short that
     its first snapshot is already `clip_end`: is that handled acceptably by
     the staleness fallback?
7. Does the fixture guard turn the cross-language trace into a standing
   regression check, and does the regenerated trace really cover both ends of
   the clip?
8. Does anything in `validation/avatar_clock.md`, `decisions.md` D9/D10 or
   `resolution.md` overstate what was executed?

## Still deferred, unchanged

**C12**, **C16**, **C18** remain deferred to M3 with the developer as owner;
the M3/M6 crash-recovery gate stays unpassed. Newly recorded for M3/M4 from
R05: nothing binds `staleAfterMs` to a required snapshot cadence. The
research-owned decisions in `goal.md` §14 are unchanged and not settleable by
review.
