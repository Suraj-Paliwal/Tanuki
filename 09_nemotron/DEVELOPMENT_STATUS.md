# Development status

Updated: 2026-11-20 (Japan time).

## Current state

- `goal.md` version 0.3 describes the experiment-first system and the later
  isolated conversation mode. Research-owned decisions in §14 remain open.
- **M1 device/timing layer implemented and through two review rounds.** Round
  1 (R01/R02) found eight Majors, all fixed; round 2 (R03) verified seven of
  them, found the device-clock gap detector partially fixed with three new
  Majors plus a snapshot-drift process fault, all now fixed. Round 3 (R04) is
  the final iteration of the bounded loop.
- **Session preflight implemented** (`preflight.py`, `config/experiment.json`):
  the start-of-session validation and measurement step required by `goal.md`
  §6, now part of the application rather than a bench script.
- **The avatar clock adapter and renderer snapshot now exist**
  (`M1-avatar-002`): the piece `goal.md` §7 requires, whose absence R01, R02
  and R03 all gave as the reason M1 could not be complete.
- **R05 returned NEEDS_FIXES on both scopes; all 13 findings are fixed**
  (`reviews/M1-avatar-002/resolution.md`). Scope A: the probe loop is now one
  shared helper (`audio_io.run_commit_probe`) with loop-level tests. Scope B:
  the adapter has an explicit `arm()` lifecycle with latched stops and a
  staleness clock that starts at arm; the controller publishes a starting clip
  as playing and keeps publishing playing through the audible tail
  (`audible_end_s`, `OutputPlayer.audible_end`); the cross-language fixture
  is guarded against drift. The user chose one more fix cycle for scope A
  despite the bounded-loop cap.
- **210 tests pass**: 180 Python (77 timing, 65 audio I/O, 35 preflight,
  3 snapshot) and 30 JavaScript (avatar clock adapter, Node's test runner).
  Every R05 fix was also reverted in a scratch copy and its test failed.
  Executed evidence is in `validation/audio_spike.md`,
  `validation/avatar_clock.md` and `validation/preflight_wasapi.json`.
- The user committed `b4fd62f M1-audio-001` and `0198546 M1-fix`; the
  coordinator has made no commits. Round-2 code is inside `0198546`; the
  evidence and record edits after it are uncommitted.

### Files that exist

| Path | What it is |
|---|---|
| `timing.py` | Clocks, capture timeline, speech segmenter, pause timer, playback position, event ledger |
| `audio_io.py` | Device inventory, PortAudio and fake backends, continuous recorder, output player with the deadline-gated prompt slot |
| `preflight.py` | Session preflight: device pinning, timing measurement, disk, stimulus hashes, optional capture check |
| `config/experiment.json` | Development configuration; every proposal is labelled as one |
| `tools/check_audio.py` | Bench tool: inventory, synthetic checks, host-API survey, commit-timing distributions |
| `requirements.txt` | Exact pins (`numpy==2.3.5`, `sounddevice==0.5.5`) |
| `decisions.md` | Engineering decisions D1-D8 with alternatives and dependencies |
| `src/clock-adapter.js` | Browser clock adapter: drives `playTrack` from the controller's playback clock, with a stale-update fault and `stop()` on every ending |
| `src/` + `model/` + `vendor/` | Minimal renderer snapshot copied from the baseline; `asset-provenance.json` (tracked) records source paths and hashes, the 21 MB of assets are gitignored |
| `tools/verify_snapshot.py` | Verifies the snapshot against its provenance record |
| `tools/make_position_trace.py` | Records a real `OutputPlayer` trace so the JS adapter is checked against actual controller output |
| `tools/avatar_clock_check.html` | Bench harness for the real renderer. **Not yet opened** |
| `tests/` | 210 tests: 180 Python on the fake backend with a manual clock, 30 JavaScript on an injected clock |
| `validation/` | Executed evidence, including what was NOT_RUN and why |

### Measured facts about this PC, not worked around

- **No input device is attached.** PortAudio reports
  `default_input_device = -1` for MME, DirectSound and WASAPI; the only
  input-capable endpoints are two Bluetooth hands-free headsets on WDM-KS,
  which are unsuitable for a study that measures speech-offset boundaries.
  Capture is therefore `BLOCKED` and every microphone-side behaviour is
  verified only on the fake backend.
- **The Windows default output device misses the candidate timing target.**
  Estimated onset delay p95 ≈ 191 ms on MME against ≈ 30 ms on WASAPI
  (device 8), where the 100 ms figure in `goal.md` §7 is a proposal. WASAPI is
  the proposed output path (`decisions.md` D5).
- **These measurements were taken over a TeamViewer session,** which can
  redirect or claim audio endpoints. They must be repeated at the physical
  machine with the final speakers and microphone attached.
- An earlier version of this file and of `validation/audio_spike.md` reported
  onset figures inflated by 50 ms by a probe-clip artifact that independent
  review caught. The corrected figures are above; the superseded ones are kept
  and marked in the spike record.

## Active checkpoint

Fix verification of every R05 finding, both scopes, under one packet
(`reviews/M1-avatar-002/packet-round-2.md`):

- **Scope A — `M1-audio-001`.** R05-F01 (Major) and F02, F03. The bounded loop
  had reached its cap; on 2026-11-20 the user chose one more fix cycle over
  carrying F01 into M3.
- **Scope B — `M1-avatar-002`.** R05-F04 … F12; F13 (packet hygiene) is met by
  the packet itself.

Reviewer `R06` dispatched 2026-11-20, fresh context, **two separate verdicts
requested**. Target files must not be edited until the report is in; the
digests in the packet are the authority.

- R05's report: `reviews/M1-avatar-002/goldfish-combined-R05-round-1.md` →
  scope A **NEEDS_FIXES** (1 Major, 2 Minor), scope B **NEEDS_FIXES**
  (4 Major, 6 Minor).
- Findings, fixes and revert checks: `reviews/M1-avatar-002/resolution.md`;
  pointer from round 4 of `reviews/M1-audio-001/resolution.md`.
- Earlier rounds of `M1-audio-001` (R01-R04) are unchanged in
  `reviews/M1-audio-001/`.
- Unresolved, deferred to M3 with the developer as owner: **C12** (`.partial`
  reports zero frames after an abrupt kill), **C16** (nothing binds
  `PromptCandidate.deadline` to the `PauseTimer`), **C18** (publication is
  atomic but not `fsync`-durable). All three leave the M3/M6 crash-recovery
  gate unpassed. Also for M3/M4's transport design: nothing binds the
  adapter's 250 ms `staleAfterMs` to a required snapshot cadence.

## Next action

1. Collect R06's report
   (`reviews/M1-avatar-002/goldfish-fix-verification-R06-round-2.md`), recheck
   the packet digests, and record the outcome in
   `reviews/M1-avatar-002/resolution.md` and `reviews/INDEX.md`. Mark a scope
   complete only if its verdict passes. If scope A fails again, it is the
   user's call whether to carry it into M3. The loop is past its cap.
2. Open `tools/avatar_clock_check.html` in a browser on this PC and record the
   result in `validation/avatar_clock.md`. It is the only check that exercises
   the adapter against the real renderer, it needs an operator, and it plays no
   audio. Serve the folder over `http://127.0.0.1` rather than `file://`, or
   the module imports and the glTF fetch will be blocked.
3. Re-run `tools/check_audio.py --commit-trials 20` and `preflight.py` on the
   real device, at the physical machine rather than over TeamViewer. Both now
   go through the shared probe helper and have not been executed on hardware
   since the refactor.
4. Then M2 (stimulus preparation against the local AivisSpeech engine, writing
   only into `.preparation/`) or M3 (the experiment state machine), whichever
   the user prefers. M3 has the larger dependency on decisions still open, and
   it is where `OutputPlayer.audible_end` gets used as the recall time zero.
5. Raise the microphone with the user as a hardware decision.

Do not install Nemotron; M7/M8 come after the experiment's engineering
acceptance.

## Avatar clock adapter behaviour

- The renderer plays **no audio**. The controller owns playback; the browser
  gets position snapshots and drives `playTrack(track, getTime)`, which is
  audio-free by design.
- `getTime` returns **file time** — seconds from the start of the complete WAV
  including its leading silence — because that is how the mouth track is
  indexed.
- The adapter extrapolates from **snapshot arrival**, not from the
  controller's clock, because the two processes do not share a time base
  (`decisions.md` D9). The cost is a mouth that lags by the transport latency;
  that bias is stated and never subtracted out.
- A **stale clock is a fault**: past 250 ms with no update the adapter stops
  and reports it, rather than extrapolating forever and holding the mouth open
  on a silent Tanuki. An external-clock track has no end event of its own.
- The controller publishes two things the renderer cannot infer
  (`decisions.md` D10): `pre_roll_s`, so the mouth does not move during the
  output latency before a clip is audible, and `ended_reason`, so clip end is
  distinguishable from an operator stop on an idle snapshot where `file_time`
  and `duration` are both zero. Both were found by the cross-language trace
  check, not by inspection.
- **Visual synchronisation is unverified and NOT_RUN.** Nothing here plays
  audio, so no claim about the mouth matching speech follows from any test
  passing.

## Session preflight behaviour

Implements the recorded operating decision: **measure the configuration at the
start of every session, store the measurements with the session, and let
development proceed** rather than waiting for a frozen tolerance.

- Devices are pinned by identity (`DeviceIdentity.key()`), never by index. A
  pinned device that is absent or ambiguous **blocks** the session; the
  preflight does not fall back to another device, because a session's timing is
  a property of its devices.
- Timing worse than the configured target records a `WARN`, surfaces to the
  operator and goes into the session record — it does not refuse the session.
  `timing_policy.blocking` flips that for participant collection once a
  tolerance is frozen.
- `no_early_output`, the detector profile, disk space, stimulus hashes and a
  missing data root are blocking checks.
- **The microphone is not opened unless `preflight.check_capture` is explicitly
  enabled.** It is off in `config/experiment.json`. A disabled check reports
  `NOT_RUN`, never `PASS`.
- A report containing any `NOT_RUN` or `BLOCKED` check never calls itself a
  pass; `verdict` and `may_start` are separate questions.
- `acoustic_onset` is permanently `NOT_RUN` until a reference channel exists,
  and no code path can label a value `measured`.

Run it with:

```text
python preflight.py --config config/experiment.json --out <report.json>
python preflight.py --config config/experiment.json --check-capture   # opens the mic
```

## Milestone ledger

| Milestone | Status | Evidence / pending condition |
|---|---|---|
| M0 specification/review | Development draft reviewed; research-owned decisions open | `goal.md`, historical design review |
| M1 audio feasibility | Device/timing layer, preflight and avatar adapter all built; one combined review in flight | `validation/audio_spike.md`, `validation/avatar_clock.md`, `reviews/`; capture BLOCKED, acoustic onset and visual synchronisation NOT_RUN |
| M2 materials/tooling | Candidate text only | No final ten-story manifest, frozen recordings or approved allocation. The preflight will hash-verify a manifest once one exists |
| M3 controller | Not started | Device layer, guard contract and preflight now exist for it to build on; C12 and C16 land here |
| M4 interface | Not started for new system | Reusable baseline exists in `08_avisspeech` |
| M5 analysis/export | Not started | No implementation evidence |
| M6 experiment validation | Not started | Final-hardware tests and research gates pending |
| M7 model feasibility | Not started | RTX 2080 Ti compatibility/performance unverified |
| M8 conversation | Not started | No local conversation pipeline |

## Open gates

`goal.md` §14 is the decision list. Sharpened or added by M1 evidence and by
round-1 review:

- **Microphone and output device models.** No capture device is attached, and
  the default output device fails the candidate target. Developer + research
  director, M1/M6.
- **Measured timing tolerance and calibration method.** Every onset figure is
  an estimate from PortAudio latency reporting; an acoustic reference channel
  is required before any tolerance can be verified. The preflight now
  accumulates per-session measurements that a tolerance could be frozen from.
- **Detector profile** (`timing.DEFAULT_PROFILE`: 32 ms frames, 96 ms minimum
  speech, 150 ms hangover). Shapes where a speech offset lands; part of the
  frozen manipulation.
- **Which reading of "where speech ended" the live deadline counts from** —
  `run_end` (the in-speech run including hysteresis-band frames) or
  `last_strong` (the last frame above the speech threshold). This is now a
  `PauseTimer` configuration option recorded with each trial, default
  `run_end`. Both readings are recorded per event; they differ by the band
  dwell, which directly changes how much silence a participant received before
  the prompt. It governs the manipulation, not only the analysis.
- **The lateness budget** beyond which a deadline becomes a
  `deadline_already_past` deviation rather than a prompt (engineering default
  50 ms).
- **Whether a trial containing a counted recorder-side gap is analysable.**

Final materials and allocation, operational policies, scoring boundaries, data
governance and reconciled research approvals remain as in §14. None of these
block unrelated synthetic engineering. Live conversation is a later milestone
and cannot alter experiment behaviour.

## Resume contract

On each handoff update this file with the active checkpoint, actual changed
files, checks run (including failures), review packet/verdict, unresolved
finding IDs, owned running processes and the exact next action. Re-read actual
files before trusting a stale status entry. Preserve history in
review/validation records rather than appending duplicate status prose here.

No long-running process is owned by this session: every check is a short-lived
command that exited on its own. No file outside `09_nemotron` has been
modified; `08_avisspeech` is untouched.
