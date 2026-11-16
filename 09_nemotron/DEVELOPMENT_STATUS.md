# Development status

Updated: 2026-11-17 (Japan time).

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
- 153 tests pass (74 timing, 53 audio I/O, 26 preflight). Executed device
  evidence is in `validation/audio_spike.md` and
  `validation/preflight_wasapi.json`.
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
| `tests/` | 153 tests, all on the fake backend with a manual clock |
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

`M1-audio-001`, round 3 (fix verification over the complete tree, preflight
included for its first review).

- Round-1 packet: `reviews/M1-audio-001/packet.md`; reports from `R01`
  (focused) and `R02` (critic), both **NEEDS_FIXES**.
- Findings, dispositions and fixes: `reviews/M1-audio-001/resolution.md`.
- Round-2 packet and report: `packet-round-2.md`, `R03` → **NEEDS_FIXES**;
  findings F01-F10 and their fixes are the round-2 section of
  `resolution.md`.
- Round-3 packet: `reviews/M1-audio-001/packet-round-3.md`; reviewer `R04`
  dispatched 2026-11-17, **verdict pending**. Target files must not be edited
  until the report is in. If round 3 does not converge, the workflow says stop
  changing the disputed scope and present alternatives to the user.
- Unresolved, deferred to M3 with the developer as owner: **C12** (`.partial`
  reports zero frames after an abrupt kill), **C16** (nothing binds
  `PromptCandidate.deadline` to the `PauseTimer`), **C18** (publication is
  atomic but not `fsync`-durable). All three leave the M3/M6 crash-recovery
  gate unpassed.

## Next action

1. Collect the `R04` report; record its outcome as round 3 in
   `reviews/M1-audio-001/resolution.md`. If it passes for scope, mark
   `M1-audio-001` complete in `reviews/INDEX.md`; if not, stop editing the
   disputed scope and present the alternatives to the user.
2. (Folded into round 3: the preflight is reviewed in the same packet.)
3. Then `M1-avatar-002`: bring in the minimal renderer/asset snapshot with
   `asset-provenance.json` and drive `TanukiLipSync.playTrack(track, getTime)`
   from `OutputPlayer.position()` through the bounded-interpolation and
   stale-update rules in `timing.interpolate`. **M1 is not complete without
   this**; both round-1 reviewers noted its absence.
4. Raise the microphone with the user as a hardware decision, and re-run the
   device measurements at the physical machine.

Do not install Nemotron; M7/M8 come after the experiment's engineering
acceptance.

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
| M1 audio feasibility | Device/timing layer in fix-verification review; preflight built but unreviewed; avatar adapter not started | `validation/audio_spike.md`, `reviews/M1-audio-001/`; capture BLOCKED, acoustic onset NOT_RUN |
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
