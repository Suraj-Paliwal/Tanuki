# Goldfish review — M1-avatar-002 / combined (fix-verification for M1-audio-001 round 3 + first review of the avatar clock adapter) / R05 / round 1

**Two verdicts, one per scope, at the bottom. A defect in one scope does not
reopen the other.**

## Provenance and scope

- **Fresh context: yes.** No development-chat history. Everything below comes
  from the packet, the named sources, the code, and the seven explicitly
  permitted commands. Isolation mechanism: a fresh agent session with no
  inherited conversation; the only file I wrote inside `09_nemotron` is this
  report. Per `EGM_WORKFLOW.md` §6 a fix-verification packet may carry earlier
  finding IDs, so reading `resolution.md` and R01-R04 was in scope for scope A;
  for scope B (`M1-avatar-002`, never reviewed before) there was no prior
  verdict to see.
- **Snapshot — unchanged.** Packet `reviews/M1-avatar-002/packet.md`, base
  commit `ae435bf31fd6b5256a99ee00e2e95737e1597fa5`.
  - I independently recomputed **all 32 SHA-256 digests** in the packet
    manifest (27 implementation/evidence files + the 5 baseline renderer
    sources) **before** my checks and **again after** them. **All 32 matched
    exactly, both times.** Nothing under review moved while I inspected it.
  - My own `find 09_nemotron \( -name __pycache__ -o -name model -o -name
    vendor \) -prune -o -type f \( -name "*.py" -o -name "*.js" -o -name
    "*.mjs" -o -name "*.json" -o -name "*.html" \)` returns exactly **26**
    files, and **every one of them is in the manifest**. Nothing is missing.
    (`.preparation/` contains no files at all.)
  - **The five `src/*.js` renderer sources are byte-identical to the
    baseline.** Verified two ways: `sha256sum` of
    `../08_avisspeech/src/{tanuki-lipsync,body,bands,formants,quality}.js`
    equals the packet's digests, and `cmp` reports IDENTICAL for all five.
    (The packet's instruction text names `../08_avisspeight`; the baseline that
    exists and that `asset-provenance.json` records is `../08_avisspeech`.) The
    snapshot did **not** quietly edit baseline renderer code.
  - Working tree: the packet's "verbatim" `git status --porcelain` is
    incomplete — see **F13**. No manifest file is affected; digests re-matched
    after my checks, so **no coverage is stale**.
- **Stage/lenses.** Scope A: fix-verification of `R04-F01…F05`. Scope B:
  comprehension + critic of the renderer snapshot and browser clock adapter.
  Lenses: timing and state-machine correctness; concurrency and cancellation;
  recording/storage integrity; evidence honesty; and `EGM_WORKFLOW.md` §5 row
  "Audio feasibility, M1", specifically *"Does the avatar use `playTrack`
  without duplicate audio?"*
  Readiness question: are the five round-3 findings actually fixed, and does
  the avatar work meet `goal.md` §7?
- **Files inspected.** `packet.md`; `EGM_WORKFLOW.md`; `reviewers/GOLDFISH.md`;
  `reviews/M1-audio-001/{resolution.md, goldfish-fix-verification-R04-round-3.md}`
  (R01-R03 consulted for the invariant list); `goal.md` §§4-7, 9, 10, 12, 13;
  `AGENTS.md`; `src/clock-adapter.js`; `src/tanuki-lipsync.js` (update/
  playTrack/stop/_finish/timeShift/measureLatency); `timing.py`
  (`PlaybackPosition`, `interpolate`, `PauseTimer`, the offset clamp);
  `audio_io.py` (`OutputPlayer.position/play/stop/_callback/_maybe_commit/
  begin_attempt/arm/cancel_candidate`, `tone_clip`); `preflight.py`
  (`measure_output`, `check_participant_configuration`, `check_disk_space`,
  the verdict ladder, `run`, `main`); `tools/{check_audio.py,
  verify_snapshot.py, make_position_trace.py, avatar_clock_check.html}`;
  `tests/test_{timing,audio_io,preflight}.py`, `tests/test_clock_adapter.mjs`,
  `tests/fixtures/position_trace.json`; `asset-provenance.json`;
  `config/experiment.json`; `decisions.md` D8-D10;
  `validation/avatar_clock.md`; `.gitignore`; the baseline
  `../08_avisspeech/src/app.js` (import list only).
  No referenced source was unavailable.
- **Executed checks.** Scratch directory
  `C:/Users/suraj/AppData/Local/Temp/r05scratch`, with
  `PYTHONPYCACHEPREFIX` pointing there (confirmed: all my bytecode landed in
  the scratch tree). Run from `09_nemotron`:

  | Command | Result |
  |---|---|
  | `python -m unittest discover -s tests -p "test_*.py"` | **161 tests OK** |
  | `python -m unittest discover -s tests -p "test_timing.py"` | **75 OK** |
  | `python -m unittest discover -s tests -p "test_audio_io.py"` | **56 OK** |
  | `python -m unittest discover -s tests -p "test_preflight.py"` | **30 OK** |
  | `node --test tests/test_clock_adapter.mjs` | **21 pass, 0 fail** |
  | `python tools/check_audio.py` | **8 PASS, 2 NOT_RUN, verdict `INCOMPLETE`**, exit 0 |
  | `python tools/verify_snapshot.py --baseline` | **23/23 assets match (21.0 MB); 5 tracked, 18 hash-only; PASS**, exit 0 |

  So the packet's test split (75 + 56 + 30 Python = 161, plus 21 JS) is
  **reproduced exactly**, as are the tool verdicts and the provenance result.
  I also independently confirmed the fixture counts (52 frames, 12 delivered
  snapshots, 44 asserted positions) by parsing
  `tests/fixtures/position_trace.json`, and the size claims (baseline
  `vendor/` 29 MB vs 1.5 MB copied; `model/` 19 MB) with `du`.
- **NOT_RUN by me, deliberately.** `tools/check_audio.py` with
  `--playback/--survey/--commit-trials/--duplex`; `preflight.py`;
  `tools/make_position_trace.py` (it would rewrite a fixture under review);
  `tools/avatar_clock_check.html` (needs a browser and an operator). I did not
  edit any file to test a revert — every "would it fail on revert?" judgement
  below is static reasoning, and I say so each time. I did not drive
  `OutputPlayer` myself (not a permitted command), so the two Python-side
  runtime defects in **F05** and **F06** are established by code trace plus the
  committed fixture's own numbers, not by execution.

## My understanding

The controller, not the browser, owns playback: audio leaves the PC through
PortAudio, and the browser must never play the same clip (`goal.md` §5). The
mouth therefore has no local `<audio>` element to read a time from. It receives
`timing.PlaybackPosition` snapshots and drives
`TanukiLipSync.playTrack(track, getTime)` — which plays no audio — where
`getTime` must return the *audible* position in seconds from the start of the
complete frozen WAV **including any file offset**, interpolated between
timestamped updates with a bound on how far it may extrapolate, with an
explicit fault when updates go stale, and with `stop()` called on clip end,
abort, fault **and** disconnect, because an externally clocked track has no end
event of its own (`goal.md` §7). The existing 30 ms anticipatory mouth lead is
frozen and no browser `AudioContext` latency compensation may be added. Scope A
is the separate question of whether the five defects R04 raised against the
audio controller were actually fixed, and whether the invariants R03 and R04
both confirmed — no output before the deadline, none before participant speech,
the configured interval added exactly once, atomic publication, no `Estimate`
labelled `measured` — still hold on this snapshot.

---

# Scope A — fix verification of R04-F01 … F05

## Per-finding status

| R04 ID | Severity | Fix present and correct? | Would the **named** test fail on revert? | Status |
|---|---|---|---|---|
| **F01** | Major | **Yes.** `preflight.py:705-712` and `tools/check_audio.py:426-431` both `cancel_candidate("probe_timeout")` and count the timeout before `continue`; the existing "only N/M committed" check reports it with the count (`preflight.py:727-734`, `check_audio.py:456-460`). I traced `cancel_candidate` (`audio_io.py:1310-1345`) against `begin_attempt` (`:1226-1245`) in every outcome: after any `cancel_candidate` call `self._candidate` is either `None` or a cancelled/committed candidate, and `begin_attempt` only raises on an *armed, uncancelled, uncommitted* candidate — so **the specific crash is genuinely closed, including the TOO_LATE race** (if the probe commits between the check and the cancel, `_maybe_commit` has already set `_candidate = None` and `cancel_candidate` returns `too_late_committed` without re-arming anything). | **No.** `test_an_armed_candidate_must_be_released_before_the_next_attempt` (`tests/test_audio_io.py:280-298`) pins the `audio_io` *contract* (arm → `begin_attempt` raises → cancel → next attempt works). It never drives `measure_output` or `commit_distribution`. Deleting both `cancel_candidate("probe_timeout")` lines leaves all 161 tests passing — I confirmed no test in `tests/test_preflight.py` touches the timeout path (`grep` for `timed_out`/`probe_timeout`/`commit_timing` returns nothing). | **PARTIALLY FIXED** — crash closed, but unverified by test, and an adjacent crash path remains: **F01 → see finding F01 below** |
| **F02** | Major | **Yes.** `tests/test_timing.py:440-471` isolates the clamp exactly as claimed. | **Yes.** Static arithmetic: the first block is observed with a 2.0 s epoch error (`note_block(480, 2.0, device_time=0.0)`) so `block_time = 2.0`; on the next block the tracker absorbs 1% of a −2.0 s error, giving `offset = 1.98` and an unclamped `block_time = 0.01 + 1.98 = 1.99 < 2.0`. With `timing.py:411-412` removed, `sample_to_time` decreases across that boundary and `assertEqual(times, sorted(times))` fails. The device clock in the test is strictly monotonic, so neither `device_time_went_backwards` nor `device_time_discontinuity` can mask it. | **VERIFIED FIXED** |
| **F03** | Minor | **Yes.** `preflight.check_participant_configuration` (`preflight.py:514-566`) is a real blocking check wired into `run()` (`:915`), requiring blocking timing, capture enabled *and* blocking, both devices pinned by identity, a configured data root and a frozen stimulus manifest; a development session reports `NOT_RUN`. | **Yes.** `ParticipantConfigurationTest` (`tests/test_preflight.py:361-414`): `test_a_participant_session_on_development_defaults_is_blocked` asserts `FAIL`, `blocks_session`, `may_start is False` and the specific unmet items; it fails immediately if the check is removed or downgraded. | **VERIFIED FIXED** |
| **F04** | Minor | **Yes.** `DeviceClockIntegrationTest` (`tests/test_audio_io.py:836-901`) drives jitter and the fallback round-trip through `FakeStream` + `ContinuousRecorder`, not `CaptureTimeline` alone. | **Yes.** `test_callback_lateness_does_not_reach_the_mapping` passes `jitter_s=0.030` on alternate blocks and asserts `gaps == []`, `clock_anomalies == []`, `gap_basis == "device_clock"`; routing jitter back into `first_frame_time` makes it fail. `test_a_fallback_run_through_the_recorder_is_not_lost_audio` asserts `frames_lost_estimate == 0`, `gap_basis == "mixed"` and `continuous is False`; reverting the `_last_device_end = None` reset fabricates a gap. | **VERIFIED FIXED** |
| **F05** | Minor | **Partly.** The stale "113" is gone, but `decisions.md:263-264` now reads **"All 153 current tests use it"** while the suite is **161**. | n/a (documentation). | **PARTIALLY FIXED — see finding F03 below** |

**Is `check_participant_configuration` honest?** Yes, on the two tests the
packet names. It states in-code and in its `data["note"]` that "passing this
check is not authorisation to collect: the research gates in goal.md section 14
are separate and are not represented here", and
`test_a_fully_configured_participant_session_passes_the_gate` asserts that
sentence survives. Its seven required conditions are the right ones for the
R04-F03 complaint: a participant session can no longer run with
`timing_policy.blocking` false, the capture check off, an unpinned device, no
data root or no frozen manifest — each of which was reachable before. The
verdict ladder keeps the two questions apart correctly (`verdict()`
`preflight.py:141-161`: `PASS` requires every check to have *run*, so with
`acoustic_onset` permanently `NOT_RUN` a session can at best read `INCOMPLETE`,
while `may_start` is governed only by blocking checks). I note — not as a
defect — that a fully configured participant session would read
`INCOMPLETE` + `may_start: True`: the gate is explicitly a *configuration*
gate, and nothing in the module claims otherwise.

**Do the invariants R03 and R04 both confirmed still hold?** Yes, all five, on
this snapshot:

| Invariant | Evidence on this snapshot |
|---|---|
| No output before the eligibility deadline | `_maybe_commit`: `now = timing.entry_time; if now < cand.deadline: return` (`audio_io.py:1437-1441`). Commitment still happens inside the callback under the player lock. Reproduced live by `check_audio.py`'s `no_prompt_before_deadline` PASS. |
| No output before participant speech | `PauseTimer.note_offset` returns early when `not self.armed` (`timing.py:1111-1116`); `armed` is set only by `note_onset` (`:1105-1109`). |
| The configured interval added exactly once, to the speech offset | `deadline = self.silence_since + self.threshold_s` (`timing.py:1121-1125`), `silence_since` from `origin_time(event)`, never from `confirmed_time`; `known_at()` takes a `max`, never a sum. Reproduced live: `pause_deadline_0.5s/1.0s/2.0s` PASS (offset 0.320 + threshold). |
| Atomic publication | `os.replace(self.partial_path, self.path)` remains the sole publication step (`audio_io.py:1024`). `recording_finalized_atomically` PASS. Durability is still the deferred **C18**. |
| No `Estimate` with `method="measured"` | Exactly one `Estimate(` call site in all production code (`audio_io.py:1480`), with `method=ESTIMATED`. `MEASURED` appears only as the constant, in `_METHODS` and in `is_measurement`. |

## Scope A findings

### M1-avatar-002-R05-F01 — Major — the probe loops still take an unhandled `AudioFault`, now from `arm()` instead of `begin_attempt()`, and no test drives either fixed loop

- **Location:** `preflight.py:694-725` (`measure_output`'s commit-trials loop,
  specifically the idle-wait at `:723-724` and the timeout branch at
  `:705-712`); the identical shape at `tools/check_audio.py:417-451`; the guard
  it collides with is `audio_io.py:1298-1299`
  (`arm()`: `if self.state == _PLAYING: raise AudioFault("cannot arm a prompt
  while output is playing")`).
- **Requirement:** the same one R04-F01 cited — `EGM_WORKFLOW.md` §6 ("missing
  evidence is not PASS") and `preflight.py`'s own purpose require that a
  hardware failure during the measurement loop produce a reported `FAIL`, not
  an unhandled traceback with no report. Also `EGM_WORKFLOW.md` §8, which does
  not accept a fix whose claimed verification does not verify it.
- **Evidence (static trace).** Both loops bound the *idle* wait by the **same**
  `limit` as the commit wait:
  ```python
  limit = deadline + clip.duration + 0.5
  while not cand.committed and self.clock.now() < limit:   # commit wait
      self._sleep(0.002)
  ...
  while player.state != "idle" and self.clock.now() < limit:  # idle wait
      self._sleep(0.002)
  player.cancel_candidate("preflight_cleanup")
  ```
  If a probe commits at any instant `c > limit − clip.duration` — i.e. in the
  final 50 ms before the limit, precisely the stalled-callback scenario
  R04-F01 was about — then `now >= limit` already holds when the idle wait is
  reached, so it **exits immediately without waiting for the clip to finish**.
  `cancel_candidate` returns `too_late_committed` (accepted at
  `check_audio.py:449`), the loop continues, the next iteration's
  `begin_attempt` succeeds (the candidate slot is empty), and then `arm()`
  raises `AudioFault` at `audio_io.py:1299` because `state` is still
  `_PLAYING`. `measure_output` has `try: … finally:` with **no `except`**
  (`preflight.py:671`/`:828`), `SessionPreflight.run()` (`:904-940`) and
  `main()` (`:943-980`) catch nothing — so this is again a raw traceback
  instead of the clean `commit_timing` FAIL the loop was taught to report.
  A second, narrower variant exists on the timeout branch: if the commit lands
  between the `if not cand.committed:` test (`:705`) and the
  `cancel_candidate` call (`:710`), the clip starts playing, the trial is
  counted as `timed_out` although it actually committed and was audible, and
  the next `arm()` raises for the same reason.
  **No test can catch any of this**, because — as recorded in the table above —
  no test drives `measure_output` or `commit_distribution` at all; the named
  regression test only pins the `audio_io` contract, so reverting the whole
  F01 fix leaves 161/161 passing.
- **Proposed fix.** (a) Give the idle wait its own bound, e.g.
  `idle_limit = self.clock.now() + clip.duration + 0.5`, so the loop always
  waits out a clip it actually started; (b) on the timeout branch, inspect the
  returned `CancelOutcome` and, when it is `too_late_committed`, treat the
  trial as committed-late (or at minimum wait for idle) rather than counting it
  as a timeout; (c) wrap the per-trial body so that an unexpected `AudioFault`
  becomes a `commit_timing` FAIL naming the trial index, which is what the
  module promises.
- **Verification.** A `test_preflight.py` test that drives
  `SessionPreflight.measure_output` on the fake backend with a stream that
  stalls past `limit` and then delivers one block, asserting the call returns a
  blocking `commit_timing` FAIL whose detail names the timeout count — and
  that it does **not** raise. The same test with the `cancel_candidate(
  "probe_timeout")` lines removed must fail, which is what closes the R04-F01
  coverage gap properly.
- **Scope blocked:** confidence that `preflight.py`'s and `check_audio.py`'s own
  FAIL paths are reachable on the marginal hardware this project has already
  documented (TeamViewer-redirected endpoints, Bluetooth WDM-KS). Blocks
  nothing in `timing.py`/`audio_io.py`, which do not contain this bug.

### M1-avatar-002-R05-F02 — Minor — the new skip-and-count path in `preflight.py` cannot report: it raises `StatisticsError` one check earlier, and the branch is unreachable anyway

- **Location:** `preflight.py:751-756` (the `device_offset` CheckResult:
  `statistics.median(offset)` and `max(offset)`, both unguarded) versus
  `:758-764` (`if not onset: … onset_delay_target NOT_RUN` with the skipped
  count); the skip branch itself at `:718-722`.
- **Requirement:** the packet's own claim — *"It is now a skip-and-count, and
  `onset_delay_target` reports `NOT_RUN` with the skipped count when no probe
  yields an onset estimate"* — plus `EGM_WORKFLOW.md` §8 on not describing
  behaviour the code does not have.
- **Evidence.** `offset` and `onset` are appended in the *same* `else` branch
  (`:720-722`), so `onset == []` implies `offset == []`. The `device_offset`
  result two statements **before** the `if not onset:` guard calls
  `statistics.median(offset)` on that empty list, which raises
  `statistics.StatisticsError` — so the `NOT_RUN` path can never execute: the
  preflight would die exactly where R04-F01 said it must not. Separately, the
  branch is unreachable in the first place: the skip condition is
  `cand.device_offset_s is None or cand.onset_delay_s is None`;
  `device_offset_s` is always set at commit (`audio_io.py:1489`), and
  `onset_delay_s` is `None` only when `audible_onset is None`
  (`timing.py:1217-1228`), which happens only when `clip.leading_silence_s is
  None` — impossible for the `tone_clip` this function builds
  (`audio_io.py:358-376`), and the function already FAILs earlier if the probe
  has no audible onset (`preflight.py:685-690`). `tools/check_audio.py` has the
  same dead branch but orders it safely (`_percentile([])` returns `None` at
  `:363-368`, and the `if not onset_delays:` guard at `:477-482` precedes every
  `median`), so the crash is `preflight.py`-only.
- **Proposed fix.** Move the `if not onset:` guard above the `device_offset`
  result (or guard that result with `if offset:`), and either delete the dead
  skip branch or state in a comment that it is defence-in-depth for a future
  non-`tone_clip` probe. Trim the packet/`resolution.md` claim to what the code
  does.
- **Verification.** A unit test that calls the reporting half with an empty
  `offset`/`onset` and asserts a `NOT_RUN` `onset_delay_target` plus no
  exception; or a construction test that the branch is unreachable, documented
  as such.
- **Scope blocked:** none beyond F01's.

### M1-avatar-002-R05-F03 — Minor — `decisions.md` D8 went stale again inside the same round: it says 153, the suite is 161

- **Location:** `decisions.md:263-264` — "All **153** current tests use it".
- **Requirement:** `EGM_WORKFLOW.md` §8 evidence honesty; this is the third
  round in which the same sentence has carried a stale number (113 → 153 →
  161), and R04-F05's own proposed fix asked for a non-numeric phrasing for
  exactly this reason.
- **Evidence.** My own run: 161 tests (75 + 56 + 30). `resolution.md` round 3
  says "D8 corrected to 153 (now 161)" — so the author knew the figure had
  already moved when the correction was written, and the packet nevertheless
  reports F05 as "Corrected". A reader of `decisions.md` alone sees 153.
  (`README.md` and `validation/avatar_clock.md` both say 161 correctly.)
- **Proposed fix.** Replace the number with "the current suite" (or "every test
  in `tests/`"), as R04 suggested, and correct the packet's F05 row to
  "corrected, then superseded by the 161-test suite".
- **Verification.** Re-read the sentence against `python -m unittest discover`
  output; a non-numeric phrasing needs no re-verification next time.
- **Scope blocked:** none; documentation accuracy only.

---

# Scope B — first review of the avatar clock adapter and renderer snapshot

## What I verified positively, before the findings

- **`playTrack` with no duplicate audio — the §5 row's question — is satisfied.**
  `src/clock-adapter.js` has no DOM, no `Audio`, no `AudioContext` and no
  timer; it is pure arithmetic over injected `now`. In the (unmodified)
  renderer, every `new Audio(...)`/`AudioContext` construction sits on the
  `speak()` / `_attachAnalyser()` / `measureLatency()` path
  (`src/tanuki-lipsync.js:320, 359, 410, 444, 155`), and `playTrack`
  (`:294-301`) touches none of them: it sets `_track`, `_getTime`,
  `_audio = null`, `mode = 'track'`. `measureLatency` is called only from
  `speak()` and only when `autoLatency` is true, which defaults to **false**,
  so `timeShift()` is `lead + offset = 0.030 + 0 = 0.030` — the frozen
  anticipatory lead, with **no** browser `AudioContext` output-latency
  compensation, as §7 requires. `tools/avatar_clock_check.html` creates a
  WebGL renderer and a `GLTFLoader` only, and says so on its face ("No audio is
  played and no device is opened"). `grep` across `src/`, `tools/` and the JS
  test finds no other audio-output construction.
- **`stop()` really closes the mouth.** `stop()` → `_finish()`
  (`src/tanuki-lipsync.js:459-469`) sets `mode = 'idle'`, `_track = null` and
  zeroes the mouth channels; `update()` then stops consulting `getTime` because
  its guard is `mode === 'track' && this._track` (`:198`), and clears all
  channels every frame (`:196`). So a wired `onStop` does close the mouth —
  the adapter's end-of-clip contract is sound *when it fires at the right
  time*, which F05 and F06 are about.
- **`pre_roll_s` is computed correctly, including the boundaries the packet
  asks about.** `OutputPlayer.position` (`audio_io.py:1513-1543`) publishes
  `pre_roll = max(0.0, self._started_at - now)` — the *remaining* pre-roll, not
  a constant latency. So: zero pre-roll behaves as a plain linear
  extrapolation; **a mid-clip snapshot correctly carries `pre_roll_s = 0`**
  (once `_started_at < now`), which is the right answer to "should it even be
  non-zero there?"; and a pre-roll **longer than the snapshot interval** works
  because every snapshot republishes the shrinking remainder, so the adapter
  holds `file_time` at 0 across as many snapshots as the window spans. The
  committed fixture shows this directly (frame 0: `file_time 0.0`,
  `pre_roll_s 0.01`; by frame 40: `pre_roll_s 0.0`).
- **`interpolate()` and the JS adapter now agree on the arithmetic.**
  `timing.interpolate` (`timing.py:1326-1350`) and
  `PlaybackClockAdapter.fileTime` (`src/clock-adapter.js:163-194`) compute the
  same `effective_age = max(0, age − pre_roll)`, the same
  `t = file_time + effective_age × rate`, the same `[0, duration]` clamp, and
  the same 250 ms staleness limit. Three *intended* differences: the time base
  (controller clock vs arrival, by D9), the stale response (raise vs
  fault + stop + hold), and the monotonic guard, which only JS has — see F12.
- **The cross-language trace is a genuine cross-check, with one real limit.**
  `expect_file_time` does **not** restate the adapter's formula: it is
  `OutputPlayer.position().file_time`, i.e.
  `max(0, min(now − _started_at, _pos/samplerate, clip.duration))` computed
  from the fake device clock and the frames actually emitted
  (`audio_io.py:1530-1537`), on the Python side, with the adapter's own
  extrapolation nowhere in the loop. That is ground truth, and it genuinely
  caught two defects. Its limits, stated precisely: (i) within a 4-frame
  undelivered run both sides are linear with rate 1.0, so what it really
  pins is the slope plus the pre-roll offset and the clamps; (ii) only frames
  where `record["playing"]` is true are asserted (`make_position_trace.py:
  76-77`), so **everything after the clip-end flip is outside the assertion
  window** — which is exactly where F06 lives; (iii) the expectation inherits
  the controller's own definition of "audible", so a systematic error in that
  definition cannot be detected by construction; and (iv) arrival time equals
  `controller_time` in the replay, so it says nothing about D9's transport
  bias. Claim substantially earned, with (ii) and (iii) worth stating in
  `validation/avatar_clock.md`.
- **Snapshot provenance is sound as far as it goes.**
  `verify_snapshot.py --baseline` re-hashes both the copy and the recorded
  source, reports 23/23 and `WARN`s (exit 0) if the baseline drifted while the
  snapshot is intact — a correct distinction. I confirmed the 23 recorded
  assets are exactly the 18 files present under `model/` + `vendor/` plus the 5
  tracked `src/*.js`; the byte counts sum to 20,980,187 (21.0 MB), and the
  addon-closure claim checks out against the baseline (`../08_avisspeech/src/
  app.js` imports exactly the six named addons; the baseline `vendor/` is 29 MB
  against 1.5 MB copied). Gap: **F11**.
- **`validation/avatar_clock.md` is, with the exceptions in F12, unusually
  honest.** Visual synchronisation, acoustic onset, the real transport, the
  un-opened `avatar_clock_check.html` and `playTrack` under a real frame loop
  are each listed `NOT_RUN` with a reason; the "182 total, all passing" figure
  is correct; the bench page itself prints what it cannot establish. I found no
  claim there that a pass implies visual or acoustic synchronisation.

## Scope B findings

### M1-avatar-002-R05-F04 — Major — the staleness clock does not start until the first snapshot, so the mouth can be left in a speaking pose indefinitely with no fault

- **Location:** `src/clock-adapter.js:164` (`if (this.stopped ||
  !this.snapshot) return this.lastFileTime;`), `:214-221` (`age()` returns
  `null` and `isStale()` returns `false` while `snapshot === null`); enshrined
  by `tests/test_clock_adapter.mjs:224-230`.
- **Requirement:** `goal.md` §7 — "timestamped updates with bounded
  interpolation and an **explicit stale-update fault**"; and the adapter's own
  stated reason for existing ("If the controller stops sending snapshots
  (crash, disconnect, hung Wi-Fi), a naive adapter would keep extrapolating
  forever and hold the mouth open on a Tanuki that is silent",
  `src/clock-adapter.js:28-33`).
- **Evidence (concrete failure case).** The natural sequence is: the UI learns
  a clip started and calls `tanuki.playTrack(track, adapter.getTime)`;
  snapshots follow. If the transport dies *before the first snapshot arrives* —
  the server crashes between starting playback and its first publish, the
  socket drops, the page was loaded against a controller that then went away —
  then `accept()` is never called, `fileTime()` returns `0` forever, and
  **no fault is ever raised and `stop()` is never called**. Meanwhile
  `TanukiLipSync.update` is live (`mode === 'track'`, `_track` set, `_getTime`
  set) and samples the track at `0 + timeShift() = 0.030` s every frame, so the
  mouth freezes in whatever shape the track holds 30 ms in — with the
  project's own bench track (`tools/avatar_clock_check.html:151-159`,
  `A = 0.5 + 0.5·sin(0.9·i)`) that is a nearly fully open mouth, on a Tanuki
  that is making no sound. That is precisely the failure the stale fault was
  written to prevent; it is merely one step earlier in the lifecycle than the
  implemented check. Nothing in the suite covers it, and the test named
  "before any snapshot the position is zero and nothing has stopped" asserts
  the current behaviour as correct.
- **Proposed fix.** Start the staleness clock when the adapter is armed, not
  when the first snapshot lands: record `this.armedAt = this._now()` in the
  constructor and in an explicit `arm()`/`expectSnapshots()` the UI calls
  immediately before `playTrack`, and in `fileTime()` treat
  `!this.snapshot && (now − armedAt) > staleAfterMs` as `stale_clock` →
  `_fault` + `_stop`. `age()`/`isStale()` should then measure from `armedAt`
  when no snapshot has arrived.
- **Verification.** A Node test that creates the adapter, never calls
  `accept()`, advances the injected clock past `staleAfterMs`, calls
  `getTime()` and asserts one `stale_clock` fault and one `STOP_STALE` stop.
  It must fail against the current file.
- **Scope blocked:** the §7 "explicit stale-update fault" requirement is only
  half met; this is a disconnect case `goal.md` §9 also cares about ("Losing
  the controlling UI must produce a defined fault/stop"). Does not block the
  rest of the adapter.

### M1-avatar-002-R05-F05 — Major — between `play()` and the first audio callback the controller publishes a snapshot the adapter reads as a stop, which kills the mouth for the whole clip

- **Location:** `audio_io.py:1521-1526` — `position()`'s idle branch fires when
  `clip is None **or** self._started_at is None`, returning
  `playing=False, rate=0.0, duration=0.0, ended_reason=self._ended_reason`;
  `play()` sets `_clip` but leaves `_started_at = None` and
  `_ended_reason = None` (`:1270-1274`), and `_started_at` is only filled by
  the next callback (`:1409-1410`). Consumed at
  `src/clock-adapter.js:146-149` via `endedReasonToStop(null) →
  STOP_REQUESTED` (`:61-66`).
- **Requirement:** `goal.md` §7 (the adapter must stop on *clip end, abort,
  fault and disconnect* — not on a clip that is starting) and §6 (terminal
  reasons must stay distinct; a pending start is not a terminal reason).
  `decisions.md` D10's own principle: the controller publishes what the
  renderer cannot infer, rather than leaving it to guess.
- **Evidence (static trace).** The window is one output callback wide
  (`blocksize/samplerate` = 10 ms at the configured 480/48000) but it opens the
  instant `play()` returns — which is exactly when a publisher naturally takes
  its first snapshot ("start the clip, then start streaming positions"). In
  that window the snapshot already carries the **new** clip's generation
  (`play()` increments it at `:1270` before returning), so the adapter takes
  the `snapshot.generation > this.generation` branch
  (`src/clock-adapter.js:128-134`), resets, then hits
  `if (!snapshot.playing || snapshot.rate === 0)` and calls
  `_stop(STOP_REQUESTED)` → `onStop` → `tanuki.stop()` → `_finish()` clears
  `_track`. The *next* snapshot (same generation, `playing: true`) silently
  clears `this.stopped` (see F08) so the adapter believes it is live again, but
  the renderer's track is gone and `getTime` is no longer consulted: **the
  story or instruction clip then plays with a motionless mouth**, and the UI
  gets a spurious `requested` stop it may log as an operator action. The
  cross-language trace cannot catch this because
  `make_position_trace.py:65-67` pumps a block *before* sampling, so frame 0 is
  already past the window; and `audio_io`'s own test of this flip
  (`tests/test_audio_io.py:517-523`) only pumps *after* `play()`.
- **Proposed fix (controller side, preferred).** Give the pending-start state
  its own published shape: when `clip is not None and _started_at is None`,
  return `file_time=0.0, rate=1.0, playing=True, duration=clip.duration`, with
  `pre_roll_s` set to the best available latency estimate (e.g. `latency_s`)
  so the adapter holds position at 0 instead of animating — which is exactly
  what the pre-roll mechanism already exists to do. Keep the `clip is None`
  branch as the only "not playing" answer. **Adapter side (defence in
  depth):** do not honour a stop from a snapshot that has never been preceded
  by a `playing` snapshot of the same generation, or distinguish
  `duration === 0 && ended_reason == null` as "no clip yet" rather than
  "stopped".
- **Verification.** A Python test that calls `play()` and asserts
  `position()` *before* any pump reports a clip that is starting (not a stop),
  with `duration == clip.duration`; plus a Node test that feeds
  `{playing:false, duration:0, ended_reason:null}` as the **first** snapshot of
  a generation and asserts no `onStop`. Both must fail against the current
  files.
- **Scope blocked:** the §7 adapter demonstration end-to-end. Note the failure
  direction is a silent mouth, not a mouth moving while silent, so it is a
  correctness/usability defect rather than a participant-safety one.

### M1-avatar-002-R05-F06 — Major — the clip-end flip precedes the audible end by one output latency, and nothing publishes the audible end; this is the untreated twin of the `pre_roll_s` defect

- **Location:** `audio_io.py:1416-1429` — on `self._pos >= clip.frames` the
  callback immediately sets `_clip = None`, `_started_at = None`,
  `_ended_reason = "clip_end"`, `state = _IDLE`, so the next `position()` is
  the idle snapshot; consumed at `src/clock-adapter.js:146-149` →
  `STOP_CLIP_END` → `tanuki.stop()`. Asserted as correct by
  `tests/test_audio_io.py:517-523`
  (`test_clip_end_flips_the_position_to_stopped_so_the_mouth_closes`).
- **Requirement:** `goal.md` §7 — `getTime` returns the **audible** playback
  position, and "Never label a scheduling timestamp as a measured acoustic
  onset" (the same honesty applies to an end); `goal.md` §6 item 4 — "Define
  recall time zero as the instruction's **audible end**", which
  `config/experiment.json` already encodes as
  `"recall_cap_origin": "instruction_audible_end"`; and `decisions.md` D10's
  own reasoning, which treats the symmetric error at the *start* of a clip as a
  real contract defect worth a new field.
- **Evidence (arithmetic, from the committed fixture).** Frames reach the DAC
  one output-latency before they are audible — the exact fact `pre_roll_s`
  exists to express — but the flip happens when the last frame is *handed to
  the device*, not when it is audible. In
  `tests/fixtures/position_trace.json` (`output_latency_s: 0.02`,
  `clip.duration: 0.45`, `_started_at = 0.020`): the last asserted position is
  `expect_file_time 0.42` at `controller_time 0.44`; the flip to
  `playing: false, ended_reason: "clip_end", duration: 0.0` is published at
  `controller_time 0.45`; but file time 0.45 is not audible until
  `0.020 + 0.450 = 0.470`. So the controller declares the clip finished
  **20 ms — one output latency — before the sound ends**, the last ~20-30 ms of
  the mouth track is never animated, and the adapter is handed an
  `ended_reason` it will faithfully report as "completed". The player already
  computes the correct value and throws it away into a side list:
  `_finished[-1]["end_block_time"] = timing.first_frame_time + take /
  samplerate` (`audio_io.py:1421-1423`) **is** the audible end. The
  cross-language trace cannot catch this because only `playing` frames are
  asserted (`make_position_trace.py:76-77`), and the Python unit test above
  asserts the early flip as the desired behaviour.
  Two consequences of different weight: (i) *visually*, on this bench
  configuration the error is masked by the frozen 30 ms anticipatory lead (at
  the flip the mouth is already sampling track time ≈ 0.46 s), and it only
  becomes visible as a mouth that closes early on a device whose output latency
  exceeds that lead — e.g. the Bluetooth endpoints this PC actually offers;
  (ii) *protocol-wise* it is unmasked — any M3 consumer that takes the
  playing→false flip, or `ended_reason == "clip_end"`, as the instruction's
  audible end gets a recall time zero biased **early by the output latency**,
  silently, on every trial.
- **Proposed fix.** Either keep the snapshot `playing` until
  `clock.now() >= end_block_time` (publishing the tail with
  `file_time = min(clip.duration, now − _started_at)` so the mouth finishes the
  track), or — minimally and symmetrically with D10 — add an
  `audible_end_in_s` / `post_roll_s` field to the clip-end snapshot and let the
  adapter defer its `stop()` by that much. Record whichever is chosen in D10
  alongside `pre_roll_s`, since it is the same fact at the other end of the
  clip.
- **Verification.** A Python test that pumps a clip to completion and asserts
  the controller does **not** report the clip finished before
  `_started_at + clip.duration` (and that the published audible-end value
  equals `_finished[-1]["end_block_time"]`); a regenerated trace whose
  assertion window extends through the tail; and a Node test that the adapter
  does not stop while audio remains audible. Also rename
  `test_clip_end_flips_the_position_to_stopped_so_the_mouth_closes`, whose
  current name asserts the defect.
- **Scope blocked:** the §7 claim that `getTime` is the audible position holds
  only up to the flip; and the §6 "instruction audible end" definition cannot
  be implemented from the published contract as it stands. M3's controller
  gate, not this checkpoint's synthetic work.

### M1-avatar-002-R05-F07 — Major — `pre_roll_s`, this checkpoint's headline fix, has no test that would fail on revert: the committed fixture makes the cross-language check a one-way ratchet

- **Location:** `audio_io.py:1537` (`pre_roll = max(0.0, self._started_at −
  now)`) and `timing.py:1345` (`effective_age = max(0.0, age −
  snapshot.pre_roll_s)`); the only assertion anywhere is
  `tests/test_clock_adapter.mjs:130-144`, which exercises the **JS** side with
  a hand-written snapshot.
- **Requirement:** `EGM_WORKFLOW.md` §8 (a fix needs change *and* verification)
  and the precedent R04 set in R04-F02 for exactly this defect class; plus
  `decisions.md` D10's claim that "both `interpolate()` and the browser adapter
  hold position through it".
- **Evidence.** `grep -c pre_roll` over the Python tests returns **0, 0, 0**
  (`test_timing.py`, `test_audio_io.py`, `test_preflight.py`); the only
  occurrences in the whole test tree are the three in
  `tests/test_clock_adapter.mjs`. Consequently:
  (a) deleting `pre_roll_s=pre_roll` from `OutputPlayer.position` leaves all
  161 Python tests passing, **and** leaves the 21 JS tests passing, because the
  trace test reads the **committed** `tests/fixtures/position_trace.json`,
  which still contains `pre_roll_s: 0.01` at frame 0 — the regression only
  surfaces if someone re-runs `make_position_trace.py`, and nothing requires or
  checks that;
  (b) deleting `− snapshot.pre_roll_s` from `timing.interpolate` fails nothing
  at all, since `PlaybackPositionTest` (`tests/test_timing.py:710-737`) never
  passes a non-zero `pre_roll_s` and `interpolate` has no production consumer
  (only tests and the docstring's "mirrors what the browser adapter must do").
  So the mechanism the packet presents as its strongest result — a contract
  defect found by a cross-language check — is currently protected on the Python
  side by a generated artifact that no check keeps in sync with the code.
- **Proposed fix.** (i) A `test_audio_io.py` test that asserts
  `position().pre_roll_s > 0` before the first audible frame and `== 0.0`
  mid-clip; (ii) a `test_timing.py` test that `interpolate` holds position
  through a non-zero pre-roll and advances after it; (iii) a test that
  regenerates the trace into a temp directory (`build_trace()` is already a
  pure function returning a dict) and compares it to the committed fixture, so
  a drifted fixture fails the suite instead of masking a regression.
- **Verification.** Each new test must fail with its corresponding line
  reverted — the (iii) test is what converts the trace from a one-time
  discovery into a standing regression guard.
- **Scope blocked:** the durability of D10's two fields across future edits; the
  current behaviour is correct, so nothing is wrong *today*.

### M1-avatar-002-R05-F08 — Minor — a stop is not latched: any later same-generation `playing` snapshot silently un-stops the adapter, so a fault or abort is not terminal and `onStop` can fire twice

- **Location:** `src/clock-adapter.js:151-152` (`this.stopped = false;
  this.stopReason = null;` at the end of a successful `accept`) against
  `:237-238` (`_stop`'s `if (this.stopped) return;` once-only guard).
- **Requirement:** `goal.md` §6 event precedence — Stop (priority 1) and
  fault (priority 2) are *terminal* for the attempt, and "If Stop and a fault
  coexist, preserve the fault flag"; §7's requirement that the adapter stop on
  abort/fault/disconnect implies the stop sticks.
- **Evidence.** The four adapter-local stops — `stale_clock` (`:170-174`),
  `disconnected()` (`:197-200`), `fault()` (`:203-206`) and `stop()`
  (`:209-211`) — do not change the controller's generation. So the very next
  snapshot with the same generation and `playing: true` falls through to
  `:151-152` and clears `stopped`/`stopReason`, re-arming `_stop` to fire a
  second time for the same clip. Concrete sequences: a >250 ms transport
  hiccup mid-clip produces `stale_clock` + `tanuki.stop()`, then the resumed
  stream silently marks the adapter live again with a recorded fault and no
  re-arm; an operator Stop handled locally (`adapter.stop()`) is cleared by any
  snapshot already in flight from before the controller's own `stop()` bumped
  the generation. The existing test
  (`tests/test_clock_adapter.mjs:158-165`) only covers repeated triggers with
  no intervening `accept`, so it does not reach this.
- **Proposed fix.** Latch terminal stops: keep a `this.terminal = true` for
  `fault`, `disconnected` and operator `stop`, and require either a new
  generation or an explicit `arm()`/`reset()` before `accept()` may clear
  `stopped`. Keep the fault list as the record (§6's "preserve the fault
  flag"). A stale stop may legitimately be recoverable, but should recover
  only through that explicit re-arm.
- **Verification.** A Node test: `fault()`, then `accept()` a same-generation
  `playing` snapshot, and assert `stopped` stays true, `getTime()` does not
  advance, and `onStop` fires exactly once.
- **Scope blocked:** nothing in M1; it is a state-machine contract M3/M4 will
  rely on.

### M1-avatar-002-R05-F09 — Minor — no arm/reset, so the previous clip's position leaks into the next one; and a snapshot with no `generation` field is accepted as same-generation

- **Location:** `src/clock-adapter.js:164` (while `stopped`, `fileTime()`
  returns the previous clip's `lastFileTime`), `:131` (`lastFileTime` is reset
  only on a *higher* generation), `:110-118` (the malformed-snapshot check does
  not require `generation`), `:124-136` (`undefined < n` and `undefined > n`
  are both false, and `?? this.generation` then keeps the old value).
- **Requirement:** `goal.md` §6 — "a superseded clip must not drive the mouth";
  comprehension (`EGM_WORKFLOW.md` §4, "what would two implementers interpret
  differently?") — the required ordering between `playTrack` and the first
  `accept` of a new clip is nowhere stated.
- **Evidence.** After clip A ends at `lastFileTime = 0.43`, the adapter is
  `stopped`. If the UI calls `playTrack(trackB, adapter.getTime)` *before* B's
  first snapshot arrives — the natural order if the UI reacts to a "clip
  started" event, and the order F05 makes likely — then every frame until that
  snapshot samples track B at 0.43 s, animating the middle of B's track for a
  few frames. The adapter offers no `arm()`/`reset()` to prevent it and no
  documented rule that `playTrack` must follow the first accepted snapshot.
  Separately, a snapshot that omits `generation` entirely is accepted and
  treated as belonging to the current clip, so a late-delivered snapshot from a
  publisher that drops the field escapes the supersede check that
  `tests/test_clock_adapter.mjs:189-195` demonstrates.
- **Proposed fix.** Add `arm({generation} = {})` that clears `snapshot`,
  `lastFileTime`, `stopped` and starts the staleness clock (shares the fix with
  F04), and document that the UI calls it immediately before `playTrack`.
  Require `typeof snapshot.generation === 'number'` in the malformed check, or
  reject a snapshot with no generation once one has been seen.
- **Verification.** Node tests: after a `clip_end` stop, `arm()` then
  `getTime()` returns 0; and `accept()` of a generation-less snapshot returns
  false and increments `rejected`.
- **Scope blocked:** none; an interface contract M4 needs.

### M1-avatar-002-R05-F10 — Minor — the cross-language test silently passes when the fixture is missing, and its stop assertion is vacuous if the key is absent

- **Location:** `tests/test_clock_adapter.mjs:256-261` (`catch { return; }`)
  and `:279` (`assert.deepEqual(stops, trace.expect_stops ?? stops)`).
- **Requirement:** `EGM_WORKFLOW.md` §6/§8 — "missing evidence is not PASS";
  `AGENTS.md` ("Do not turn planned tests into completed tests").
- **Evidence.** Delete or rename `tests/fixtures/position_trace.json` (it is a
  *generated* file, excluded from no `.gitignore` rule today but regenerated by
  a tool reviewers are told not to run) and `node --test` still reports
  **21/21 pass**: the headline "Cross-language contract PASS" row in the packet
  and in `validation/avatar_clock.md` would then be a no-op that nobody can
  see. The `?? stops` fallback likewise turns the stop assertion into
  `deepEqual(stops, stops)` if `expect_stops` is ever absent or renamed.
- **Proposed fix.** Use `t.skip('fixture missing; run tools/
  make_position_trace.py')` so the runner reports a skip rather than a pass —
  or simply let the read throw, since the fixture is committed. Replace
  `?? stops` with an explicit `assert.ok(Array.isArray(trace.expect_stops))`
  before the comparison.
- **Verification.** Temporarily point the test at a non-existent path in a
  scratch copy and confirm the runner reports 1 skipped (or 1 failed), not 21
  passed.
- **Scope blocked:** the evidential weight of the "cross-language contract"
  row, not the current result (the fixture is present and the assertions do run
  — I confirmed 44 positions are actually checked).

### M1-avatar-002-R05-F11 — Minor — the provenance record is a list, not a closure: unlisted files under the untracked `model/`/`vendor/` are invisible to both Git and the verifier, and the file that justifies the addon set is absent from the snapshot

- **Location:** `tools/verify_snapshot.py:49-65` (iterates `manifest["assets"]`
  only; nothing walks the directories); `asset-provenance.json`
  `three_addon_closure.note`; `validation/avatar_clock.md` §"The renderer
  snapshot" ("`app.js` imports six three.js addons").
- **Requirement:** the packet's own question 9 ("Can a reader establish what
  bytes are in use?"); `goal.md` §12 (asset provenance for the snapshot) and
  §9 ("Restrict web routes to intended assets").
- **Evidence.** `model/` and `vendor/` are `.gitignore`d, so Git sees nothing
  there, and `verify_snapshot.py` only checks that each *listed* asset still
  matches — it never detects an **extra** file. Today the sets coincide (I
  confirmed `find model vendor -type f` returns exactly the 18 hash-only
  assets), so the current claim is true; but
  `tools/avatar_clock_check.html:66-69` maps `three/addons/` onto that
  directory wholesale, so any stray or hand-edited file dropped in later would
  be loadable, invisible to Git, and silently PASS the verifier. Separately,
  the closure's justification cites `app.js`, which is **not in the snapshot**
  (it is an M4 file per `goal.md` §12) and is not recorded in
  `asset-provenance.json`, so a reader inside `09_nemotron` cannot locate the
  file that defines the six entry points; the only in-snapshot consumer
  (`avatar_clock_check.html`) imports just `GLTFLoader`.
- **Proposed fix.** Walk `model/` and `vendor/` in `verify_snapshot.py`, report
  any path not in the manifest as `UNEXPECTED` and exit non-zero (the tool
  already advertises "Exits non-zero on any mismatch, so it can gate a release
  check"). Name the closure root as `../08_avisspeech/src/app.js` in both
  `asset-provenance.json` and `avatar_clock.md`, and say that it is baseline
  code deliberately not copied until M4.
- **Verification.** Drop a scratch file under `vendor/three/addons/` and
  confirm the tool fails; re-read the two documentation sentences.
- **Scope blocked:** "what bytes are in use" is answerable for the 23 recorded
  assets and not answerable for the directory as a whole.

### M1-avatar-002-R05-F12 — Minor — three disclosure inaccuracies around D9/D10 and the `interpolate` "mirror"

- **Location:** `decisions.md` D9 "Cost, stated rather than hidden";
  `validation/avatar_clock.md` §"Limitations to carry forward" bullet 4;
  `timing.py:1326-1334` (`interpolate`'s docstring vs its body).
- **Requirement:** `EGM_WORKFLOW.md` §8 and `AGENTS.md` ("Keep evidence with
  commands, results, environment and file identity"; do not overstate);
  `goal.md` §7 ("Record any mapping between browser display time and
  controller time").
- **Evidence.** (a) **The clip-start bias is twice the stated one.**
  `pre_roll_s` is defined relative to `controller_time`
  (`timing.py:1308-1310`), but the adapter subtracts it from an *arrival*-based
  age (`src/clock-adapter.js:182-183`). With transport latency L, the remaining
  pre-roll at arrival is `pre_roll_s − L`, so during the pre-roll window the
  mouth is held back by L **in addition** to D9's L of arrival lag — the
  mouth lags by ≈2L at the start of every clip, decaying to L thereafter. D9
  says only "the mouth lags by however long a snapshot took to arrive". The
  effect is sub-millisecond on loopback and the right remedy is one sentence,
  not a compensation (which D9 rightly refuses), but it should be the sentence
  that is true. (b) **`pre_roll_s` is attributed to the wrong estimator.**
  `avatar_clock.md` says it "is derived from the device's reported latency";
  it is actually derived from `BlockTiming.first_frame_time` (the per-block DAC
  time) via `_started_at`, i.e. the *other* of the two estimators D5 records as
  disagreeing by ~12 ms. The uncertainty claim survives; the attribution does
  not. (c) **`interpolate` is called a mirror but is not one.** Its docstring
  says it "Mirrors what the browser adapter must do", yet it has no monotonic
  guard, so unlike the adapter (`src/clock-adapter.js:191-192`) it can return a
  value below its previous answer when a snapshot lands slightly behind an
  extrapolated point. It has no production consumer today, so this is a parity
  and documentation issue rather than a behavioural one.
- **Proposed fix.** Add the ≈2L sentence to D9 and to `avatar_clock.md`;
  correct the pre-roll attribution to the per-block DAC time; either add the
  monotonic clamp to `interpolate` or soften its docstring to name the three
  intended differences (time base, stale response, monotonic guard).
- **Verification.** Re-read against the three code sites; if the clamp is
  added, a `test_timing.py` case that a late snapshot does not move the
  interpolated position backwards.
- **Scope blocked:** none; D9's central decision is sound (see below).

### M1-avatar-002-R05-F13 — Minor — the packet's "verbatim" `git status --porcelain` is incomplete (packet hygiene; affects neither scope's verdict)

- **Location:** `reviews/M1-avatar-002/packet.md` §"Snapshot identity".
- **Requirement:** `EGM_WORKFLOW.md` §6 — "Git base/current commit if
  available, **working-tree diff**, and SHA-256 hashes of all reviewed files
  (including untracked files). A commit hash alone is insufficient for a dirty
  tree."
- **Evidence.** The listing gives two entries and calls itself verbatim, but
  `?? 09_nemotron/reviews/M1-avatar-002/` must have been present when the
  packet was written (the packet file lives inside that still-untracked
  directory, mtime 19:08:41). During my review window the coordinator also
  modified `README.md` and `reviews/INDEX.md` (both mtime 19:09:38, i.e. after
  the packet) and then `DEVELOPMENT_STATUS.md` — it was clean at my first
  `git status` and modified at my last. None of the four is a manifest file or
  a dependency of the reviewed code; I re-verified all 32 digests afterwards
  and they were identical, so **no reviewed coverage is stale**, and
  `EGM_WORKFLOW.md` §3 step 4 permits unrelated edits. I checked the
  pre-written `reviews/INDEX.md` row for this checkpoint: it says "review
  dispatched … two separate verdicts requested", not a pass, which is correct
  per §10.
- **Proposed fix.** Paste the complete porcelain output (including untracked
  review directories), or state the filter applied; and note in the packet that
  status/index/README files may change during the review window, with digests
  as the authority for what is under review.
- **Verification.** Re-run `git status --porcelain` from the repository root at
  packet-assembly time and diff against the pasted block.
- **Scope blocked:** none.

## Open research decisions / evidence gaps

Separate from the code defects above.

- **Research-owned, unchanged and not settleable by any reviewer:** the
  `goal.md` §14 decisions listed in `resolution.md` — the prompt-after-threshold
  interpretation (D1), the frozen detector profile and the silence-origin
  reading (D4), the final hardware/speaker configuration and the frozen timing
  tolerance (D5), the event-precedence and rearming rules (D7), the overlap
  policy, the scored-interval boundary and `recall_cap_origin`. No approval
  exists; none is created here.
- **Deferred engineering gates, correctly scoped:** **C12** (`.partial` reports
  zero frames after an abrupt kill), **C16** (nothing binds
  `PromptCandidate.deadline` to `PauseTimer`) and **C18** (publication atomic
  but not `fsync`-durable) — all to M3 with the developer as owner. I treated
  them as gates on the M3/M6 crash-recovery release, not as blockers to
  synthetic work, and I found no new evidence that any has silently worsened.
- **NOT_RUN, confirmed accurate and material:** visual synchronisation (nothing
  here plays sound, so no claim follows from any pass — correctly stated in the
  packet, `validation/avatar_clock.md`, `decisions.md` D10 and on the bench
  page itself); acoustic onset anywhere; the adapter against the real renderer
  (`tools/avatar_clock_check.html` **has not been opened** — I did not open it
  either); the real transport and its jitter; `playTrack` under a real
  `requestAnimationFrame` loop; browser disconnect/refresh mid-clip. Microphone
  capture remains **BLOCKED** (no default input device; two WDM-KS Bluetooth
  endpoints). All device figures were taken over TeamViewer and must be
  repeated at the physical machine.
- **Contract gap for M3/M4, not a defect here:** nothing binds
  `staleAfterMs` (250 ms, matching `interpolate`'s `stale_after_s`) to a
  required snapshot publication cadence. The fixture's cadence is 50 ms; a
  future server publishing at 100 ms with jitter would have little headroom and
  one publishing more slowly would fault every frame. This is the same class as
  the deferred C16 (two settings that must agree with nothing enforcing it) and
  should be named in the M3/M4 transport design.
- **I cannot confirm the F02 revert experiment was performed**, only that its
  claimed outcome is the arithmetically correct one and that `timing.py`'s
  digest matches the packet. Editing code to re-run it was outside my
  permissions.
- **No participant-use approval and no universal safety guarantee follows from
  this review.** It covers the recorded snapshot only.

## Verdict

### Scope A — `M1-audio-001` round-3 fixes: **NEEDS_FIXES**

Four of the five round-3 findings are properly fixed (F02, F03, F04 verified
fixed with tests that would fail on revert; F01's underlying crash genuinely
closed, including the TOO_LATE race the packet asked about). All five invariants
R03 and R04 confirmed still hold, and I reproduced every executed check in the
packet exactly. What stops a pass is one unresolved Major in the same two probe
loops (**F01**: an unhandled `AudioFault` from `arm()` when a probe commits near
the wait limit, plus the fact that no test drives either fixed loop, so the fix
R04 asked for would not fail on revert), with two Minors alongside it (**F02**
an unreachable, crash-prone degradation path in `preflight.py`; **F03** D8's
test count stale again). The remedies are narrow and local — a separate idle
bound, a `CancelOutcome` check, one wrapper, one loop-level test and two
sentences. This verdict says nothing about the avatar work.

Note on the bounded loop: `EGM_WORKFLOW.md` §8 caps this scope at three
fix/review iterations and three have run. This review is the fourth round of
*review*, not a fourth fix iteration, and F01 is neither a reversal of an
accepted design decision nor a sign of non-convergence (8 → 4 → 2 → 1 Major).
Whether to spend one more fix/verify cycle on F01 or to carry it as a named
open Major into M3 is a scope decision for the user, not for me.

### Scope B — `M1-avatar-002` avatar clock adapter and renderer snapshot: **NEEDS_FIXES**

The architecture is right and the honesty is good: the browser plays no audio,
`playTrack(track, getTime)` is used exactly as §7 intends, the frozen 30 ms
mouth lead is untouched and no `AudioContext` compensation was added, the
renderer sources are byte-identical to the baseline, the provenance mechanism
works, D9 is a sound decision with its cost stated rather than subtracted out,
and `validation/avatar_clock.md` does not claim visual or acoustic
synchronisation anywhere. The cross-language trace is a genuine cross-check and
earns most of its claim. But four Majors stand between this and §7:
**F04** the staleness clock never starts if the first snapshot never arrives, so
the mouth can be left in a speaking pose on a silent Tanuki with no fault —
the exact hazard the stale fault exists to prevent; **F05** the controller
publishes a snapshot the adapter reads as a stop in the window between `play()`
and the first callback, which kills the mouth for the whole clip; **F06** the
clip-end flip precedes the audible end by one output latency and nothing
publishes the audible end, which is D10's pre-roll defect left untreated at the
other end of the clip and which also undermines
`recall_cap_origin: instruction_audible_end`; **F07** `pre_roll_s` itself has no
test that would fail on revert, because the Python side is guarded only by a
committed generated fixture. Five Minors (F08-F12) cover stop latching, the
missing arm/reset, a test that passes when its fixture is missing, the
provenance closure, and three disclosure inaccuracies.

**What neither verdict covers:** any acoustic or visual claim; the adapter
against the real renderer (`avatar_clock_check.html` is still unopened); the
real transport, its latency and its jitter; `playTrack` under a real frame loop;
microphone capture; the M3 controller, VAD, server, UI, stimulus manifest and
transcription, whose absence is a milestone boundary and not a defect here; the
deferred C12/C16/C18 gates, which remain gates on the M3/M6 release; and every
research-owned decision in `goal.md` §14. Measurements taken over TeamViewer
must be repeated at the physical machine. No participant-use approval follows
from this review.
