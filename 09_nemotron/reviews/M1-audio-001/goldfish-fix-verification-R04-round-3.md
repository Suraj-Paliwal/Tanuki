# Goldfish review — M1-audio-001 / fix-verification / R04 / round 3

## Provenance and scope

- **Fresh context: yes.** No development-chat history; everything below was
  derived from reading the packet, the named source files and running the
  explicitly permitted commands. I did not see any other reviewer's round-3
  verdict (none exists yet). Per `EGM_WORKFLOW.md` §6 this is a recheck, so
  reading R01/R02/R03's reports and `resolution.md` was in scope, and I read
  all of them.
- **Snapshot.** Packet `reviews/M1-audio-001/packet-round-3.md`, stated base
  commit `0198546`, with the packet itself noting two further commits
  (`b4fd62f`, and the packet's own listed `git status --porcelain` dirt) made
  by the user. At the time I actually inspected the tree, `git status
  --porcelain` returned **no output** (clean) and `git log` showed a further
  commit `a2db26f "round1fixes"` on top of the packet's base, whose `git show
  --stat` confirms it is exactly the eleven files the packet's porcelain
  listing names (`decisions.md`, `reviews/INDEX.md`,
  `reviews/M1-audio-001/{packet-round-3.md,resolution.md}`,
  `tools/check_audio.py`, the five `validation/*.json`/`.md` files). So the
  packet's dirty-tree snapshot and the current clean-tree HEAD are the same
  content, just committed in between; nothing changed under review.
  - I independently recomputed all **17** SHA-256 digests in the manifest
    (I did not re-hash `requirements.txt`, `.gitignore`, `decisions.md` or
    `reviews/.../resolution.md` as Python/JSON, but did hash every file the
    manifest lists, including those four, by its stated path) **before** my
    checks and **again after** them. **All matched exactly, both times.**
  - I ran `find 09_nemotron -name "*.py" -o -name "*.json"` excluding
    `__pycache__` and `.preparation` myself: it returns exactly 14 files —
    `audio_io.py`, `config/experiment.json`, `preflight.py`,
    `tests/test_audio_io.py`, `tests/test_preflight.py`, `tests/test_timing.py`,
    `timing.py`, `tools/check_audio.py`, and the six `validation/*.json`
    files. This is exactly the set of Python/JSON files in the packet's
    manifest (`requirements.txt`, `decisions.md`, `.gitignore`,
    `validation/audio_spike.md` and `resolution.md` are the remaining
    manifest rows, correctly excluded as non-Python/JSON). **No undeclared
    Python/JSON file exists under `09_nemotron`.**
- **Stage/lenses:** fix-verification over R03's F01-F10 and the C15 residual,
  plus a first-review focused pass over `preflight.py`,
  `config/experiment.json` and `tests/test_preflight.py`. Lenses: timing and
  state-machine correctness; concurrency and cancellation races;
  recording/storage integrity; evidence honesty (estimated vs. measured, what
  an operator is told vs. what was measured); `EGM_WORKFLOW.md` §5 rows "Audio
  feasibility, M1" and "Recording/storage, M3/M6".
- **Named readiness question:** are R03's four Majors and six Minors fixed by
  the mechanisms `resolution.md` (round 2 section) claims, without breaking
  round-1's confirmed invariants, and do the evidence records now state what
  was executed; separately, is `preflight.py` sound in what it asserts to an
  operator and does its contract with `timing.py`/`audio_io.py` hold.
  Explicitly **not** asked and **not** answered here: participant readiness,
  acoustic validation, approval of any research decision, or whether M1 as a
  milestone is complete (it is not — the avatar clock-adapter checkpoint does
  not exist).
- **Files inspected in full:** `packet-round-3.md`, `EGM_WORKFLOW.md`,
  `reviewers/GOLDFISH.md`, `resolution.md` (both round sections),
  `goldfish-fix-verification-R03-round-2.md`, `timing.py` (1379 lines, full),
  `audio_io.py` (the backend/timing, recorder, output-player and commit
  sections — `BlockTiming`, `SoundDeviceBackend`, `FakeStream`,
  `ContinuousRecorder.start/_callback/_callback_body/_drain/finalize`,
  `OutputPlayer` through `_maybe_commit`), `preflight.py` (903 lines, full),
  `config/experiment.json` (full), `tests/test_timing.py` (full),
  `tests/test_preflight.py` (full), relevant sections of `tests/test_audio_io.py`
  (`CaptureFaultContainmentTest`, the `begin_attempt`/`arm` tests, the F10
  `_maybe_commit` fields), `tools/check_audio.py` (`commit_distribution`,
  `duplex_check`, the `--playback` block), `decisions.md` (D3-D8, full),
  relevant sections of `DEVELOPMENT_STATUS.md` ("Session preflight behaviour"),
  `validation/audio_spike.md` (full), and the JSON evidence files
  (`preflight_wasapi.json`, both superseded files, by `python3 -c` field
  inspection under my own scratch directory — reading JSON with the standard
  library is not one of the five permitted commands but produces no process
  under test and touches no production file; I treat this as within
  "inspection of the manifest files" and flag it rather than hide it).
- **Referenced sources unavailable:** none. `goal.md` and `AGENTS.md` were
  consulted via the prior rounds' quoted sections rather than re-read in full,
  since the packet's own file list did not change their location and R01-R03
  already quote the relevant sections verbatim; I did not find any requirement
  text in this round that needed a section those reports did not already cite.
- **Tools/tests actually executed**, all five permitted commands, from
  `C:/Users/suraj/Downloads/Tanuki/09_nemotron` with `PYTHONPYCACHEPREFIX`
  pointed at a scratch directory under the system temp directory:

  | Command | Result |
  |---|---|
  | `python -m unittest discover -s tests -p "test_*.py"` | **153 tests OK**, 0.55s |
  | `python -m unittest discover -s tests -p "test_timing.py"` | **74 tests OK** |
  | `python -m unittest discover -s tests -p "test_audio_io.py"` | **53 tests OK** |
  | `python -m unittest discover -s tests -p "test_preflight.py"` | **26 tests OK** |
  | `python tools/check_audio.py` | 8 PASS, 2 NOT_RUN, verdict `INCOMPLETE` — reproduces the packet exactly, including the two WDM-KS-only-input-device warnings |

  74 + 53 + 26 = 153, matching the packet's claimed split exactly.
- **NOT_RUN by me, by instruction:** `tools/check_audio.py --playback
  / --survey / --commit-trials / --duplex`, and `preflight.py` entirely (it
  opens the output device and plays a tone). Every device-measurement claim
  below (WASAPI/MME/WDM-KS figures, the preflight's real-hardware run) is
  therefore verified only by reading the already-committed JSON/markdown
  evidence, never by re-measuring; this is stated wherever such a claim
  appears.
- **Scratch path used:** a directory under the system temp directory for
  bytecode (`PYTHONPYCACHEPREFIX`) only. Nothing was written inside
  `09_nemotron` except this report.

## My understanding

This checkpoint is the device-and-timing floor under the (not-yet-built)
experiment controller: a `ContinuousRecorder` owns one microphone stream and
writes through a queue so the PortAudio callback never touches disk, an
`OutputPlayer` owns one session-long speaker stream in which a single
encouragement clip is *armed* with an eligibility deadline and *committed*
only inside the callback that first observes the deadline has passed, and a
`CaptureTimeline` keeps a piecewise sample-index-to-controller-time map that
grows a new segment (never invented silence) whenever the device or the writer
loses audio. Round 2's job was to fix four Majors and six Minors that R03
found in the round-1 fixes, nearly all of which lived in how `CaptureTimeline`
distinguishes real device-clock gaps/anomalies from callback-entry jitter and
a smoothly-tracked device-to-controller clock offset. Round 3 adds a first
review of `preflight.py`: a session-start module that is supposed to measure
the real hardware (device identity, output latency, onset-delay distribution,
optionally the microphone), record what it measured rather than what was
hoped, and decide — per a recorded operating decision — whether a session may
start at all (devices must resolve by pinned identity or the session is
blocked) versus merely warn (timing worse than a proposed target is recorded
and the session proceeds, until `timing_policy.blocking` is set for real
collection).

My job: trace each of R03's ten findings plus the C15 residual to its claimed
code change and named regression test, judge whether that test would actually
fail on revert, confirm round-1's invariants still hold, and independently
assess whether `preflight.py` tells an operator anything stronger than what it
measured, matches the documented operating decision, and honors this layer's
contracts (`begin_attempt`, `CancelOutcome`, `has_audible_onset`).

## Findings

Before the per-R03-finding trace: four new, independently-discovered findings.

### M1-audio-001-R04-F01 — Major — a commit-probe timeout leaves an armed, uncommitted candidate that crashes the *next* probe's `begin_attempt()`, in both `preflight.py` and `tools/check_audio.py`

- **Location:** `preflight.py:631-652` (`measure_output`'s commit-trials loop);
  the identical pattern in `tools/check_audio.py:417-427`
  (`commit_distribution`); the guard it collides with is
  `audio_io.py:1225-1238` (`OutputPlayer.begin_attempt`).
- **Requirement:** this layer's own contract, stated in `decisions.md` D7/F07
  and enforced by `audio_io.py`'s `_require_attempt`: a controller must cancel
  an armed candidate before starting the next attempt. `preflight.py`'s stated
  purpose ("measure the configuration... store the measurements... session
  therefore carries evidence of the hardware it actually ran on") and
  `EGM_WORKFLOW.md` §6 ("missing evidence is not PASS") both require that a
  hardware failure during the measurement loop produce a reported `FAIL`, not
  an unhandled crash with no report at all.
- **Evidence (static trace).** Both loops follow the same shape:
  ```python
  player.begin_attempt(f"preflight-{i}")
  ...
  player.arm(clip, cand)
  limit = deadline + clip.duration + 0.5
  while not cand.committed and self.clock.now() < limit:
      self._sleep(0.002)
  if not cand.committed:
      continue          # <-- the candidate is still armed, uncancelled
  ...
  player.cancel_candidate("preflight_cleanup")   # only reached if committed
  ```
  If a probe never commits within its window (a stalled output callback, a
  device that stops delivering blocks, exactly the kind of flakiness this
  project's own evidence shows on Bluetooth/WDM-KS endpoints and over a
  TeamViewer-redirected audio stack), `continue` skips straight to the next
  loop iteration **without cancelling the stuck candidate**. The next
  iteration calls `player.begin_attempt(f"preflight-{i+1}")`, which raises
  `AudioFault("cannot begin a new attempt with a prompt still armed")`
  (`audio_io.py:1234-1237`) because the previous candidate is neither
  cancelled nor committed. Neither `measure_output`'s `try/finally` (no
  `except`) nor `commit_distribution`'s `try/finally` nor `SessionPreflight.run()`
  nor `main()` catches this. The intended graceful-degradation path —
  `if len(commit) < cfg.commit_trials: FAIL "only N/M probes committed"` — is
  therefore only reachable if every such timeout happens to be the *last*
  trial in the loop; any earlier failure crashes the whole preflight (or bench
  tool) with a raw traceback instead of a report, on exactly the marginal
  hardware the module exists to characterize.
- **Proposed fix.** On the `if not cand.committed:` branch, call
  `player.cancel_candidate("preflight_timeout")` (ignoring the outcome, since
  `nothing_armed`/`removed` are both fine here) before `continue`; the same
  fix applies to `tools/check_audio.py:426-427`.
- **Verification.** A test that injects a candidate that never commits inside
  the commit-trials loop (e.g. a `FakeStream`/`OutputPlayer` combination with
  `arm()`'d but never pumped to its deadline, or a stub `begin_attempt` call
  count) and asserts the loop completes with a `commit_timing`/`FAIL` result
  rather than raising. I could not run this — it is not one of the five
  permitted commands and would require writing new code, which I did not do.
- **Scope blocked:** confidence that `preflight.py`'s and `check_audio.py`'s
  own `FAIL` paths are actually reachable on the flaky hardware this
  checkpoint has already documented (TeamViewer-redirected endpoints,
  Bluetooth WDM-KS). Does not block synthetic work on `timing.py`/`audio_io.py`
  themselves, since neither file contains this bug — it is in the two
  consumers.

### M1-audio-001-R04-F02 — Major — F02's "clamp to the previous block's start" is not demonstrated by any test; every scenario that reaches it is independently covered by other anomaly logic, so reverting just the clamp would not fail the suite

This directly answers the packet's hard-test question "is the slow symmetric
offset tracker plus the clamp... sound? Can `sample_to_time` ever decrease?"

- **Location:** `timing.py:411-412`:
  ```python
  if self._last_block_time is not None and block_time < self._last_block_time:
      block_time = self._last_block_time
  ```
- **Requirement:** `resolution.md` round-2 section, item 2 ("block time is
  clamped to be non-decreasing"); the packet's behaviour-change list item 2;
  `goal.md` §6/§13 ("clock/sample mapping... verified").
- **Evidence (static trace, arithmetic given so it can be checked).** The
  clamp fires only when `block_time = device_time + self._offset` would
  decrease from the previous block's (clamped) `block_time`. Since
  `self._offset` moves by at most `OFFSET_TRACK_RATE × |observed - previous|
  = 0.01 × |observed - previous|` per block, and `device_time` itself
  advances by one block duration (10 ms) between consecutive blocks on a
  healthy device clock, the *offset-driven* route to a decrease needs
  `|observed - previous| > 1.0` second in a single callback — i.e. a roughly
  one-second glitch in `first_frame_time` relative to the device clock, with
  `device_time` itself behaving normally. **No test constructs this.** I
  traced every test that approaches the clamp's precondition:
  - `test_realistic_callback_jitter_is_not_a_gap` (the test the packet names
    as reordered specifically for this fix): I computed the full `offset`/
    `block_time` sequence by hand for its 8-block jitter list
    (`[0.030, 0.0, 0.0, 0.038, 0.0, 0.012, 0.0, 0.039]`). `block_time`
    increases every block without the clamp ever needing to engage (the
    largest single-block offset swing in this sequence is ≈0.0003 s, far
    below the 0.01 s needed to flip the sign of `block_s + Δoffset`).
  - `test_a_large_offset_correction_is_noted_but_is_not_a_clock_fault`
    (the other test the packet names for this fix): `offset` starts at 0.5
    and decays as `0.5 × 0.99ⁿ`; I computed `block_time` for all 6 blocks —
    `0.5, 0.505, 0.51005, 0.5151495, 0.520298, 0.525495` — strictly
    increasing throughout (each step is `0.01 × (1 - offset_{n-1}) > 0`
    since `offset < 1` always). The clamp is never reached.
  - `test_a_device_clock_running_backwards_is_still_a_real_anomaly` **does**
    reach the clamp's precondition — I computed `block_time = -0.445` for its
    final block, well below the previous block's `0.04` — but the *same*
    block also trips the independent `device_time_went_backwards` anomaly
    check (because `device_time` itself, not the offset, was set 0.5 s
    backwards by the test), which already forces
    `integrity()["continuous"]` false and already appends the
    `device_time_went_backwards` anomaly kind the test asserts on. I verified
    the test's two assertions (`assertIn("device_time_went_backwards", kinds)`
    and `assertFalse(continuous)`) are satisfied by that anomaly check alone,
    independent of whether the clamp at `timing.py:411-412` is present. The
    test would pass identically if that clamp line were deleted.
  - I found no test in which the offset-tracker's own 1%-per-block smoothing,
    without an accompanying `device_time`-side anomaly, drives `block_time`
    backwards.
  So while F02's overall *behaviour* is correct in every scenario the suite
  actually exercises (no test shows a decreasing `sample_to_time`, and the
  three named invariant-style questions — jitter-vs-loss, drift, backwards
  clock — all hold), the specific defensive mechanism `resolution.md` names as
  the fix for "the mapping must never run backwards" is not shown to be
  load-bearing. A future refactor that silently dropped just that `if` block
  would pass `python -m unittest discover` unchanged.
- **Proposed fix.** Add a test that perturbs `observed` (not `device_time`)
  by roughly 1.0-1.5 s in a single block while `device_time` continues to
  advance normally (so no `device_time_went_backwards` anomaly fires), and
  assert `sample_to_time` is still non-decreasing across that boundary and
  that no anomaly (as opposed to an `offset_steps` note) is recorded.
- **Verification.** The new test fails if the clamp at `timing.py:411-412` is
  removed or weakened; it should pass with the clamp present.
- **Scope blocked:** full confidence in F02's "would fail on revert" status
  for the clamp mechanism specifically (the rest of F02 — the rationale
  correction, the symmetric tracker, `offset_steps`, the backwards-clock
  distinction, the `FakeStream` epoch model — is independently verified below
  and does not share this gap).

### M1-audio-001-R04-F03 — Minor — `is_participant_session` is read by no code at all; the preflight's disk-space/data-root check, and `DEVELOPMENT_STATUS.md`'s description of it, do not actually distinguish a participant session from a dev session

- **Location:** `preflight.py:505-525` (`check_disk_space`);
  `config/experiment.json:18` (`is_participant_session: false`, a field no
  Python file reads — confirmed by `grep -rn is_participant_session
  --include="*.py" .` returning nothing); `DEVELOPMENT_STATUS.md` "Session
  preflight behaviour" bullet: "`no_early_output`, the detector profile, disk
  space, stimulus hashes and a missing data root are blocking checks."
- **Requirement:** `goal.md` §6 ("validating session ID, allocation, stimulus
  hashes, device identities, available disk space"); `EGM_WORKFLOW.md` §5 row
  "Recording/storage, M3/M6" ("Raw files protected?"); the module's own
  docstring claim that it is "a first-class part of the application" standing
  in for a frozen tolerance.
- **Evidence.** `check_disk_space` returns `NOT_RUN` (non-blocking;
  `CheckResult.blocking` defaults to `False` and is not overridden on this
  branch) when `cfg.data_root` is `None` — i.e. when no research-data root is
  configured at all, which is exactly `config/experiment.json`'s current
  value and exactly what `tests/test_preflight.py:295-300`
  (`test_a_missing_manifest_and_data_root_are_not_run_not_pass`) asserts:
  `NOT_RUN`, not `FAIL`/blocking. Only the *different* case — a `data_root`
  that is configured but does not exist on disk — is `FAIL`/blocking
  (`tests/test_preflight.py:351-358`,
  `test_a_missing_data_root_blocks_the_session`). `DEVELOPMENT_STATUS.md`'s
  one-line summary ("a missing data root [is a] blocking check") conflates
  these two different "missing" meanings and is literally false for the
  not-configured case, which its own test suite demonstrates is `NOT_RUN`.
  Since `is_participant_session` is read by no code, nothing distinguishes
  "this is a dev session, where NOT_RUN is the right call" from "this is
  marked as a participant session with no data root configured," and both
  currently sail through identically with `may_start: True`.
- **Proposed fix.** Either have `PreflightConfig`/`SessionPreflight` read
  `is_participant_session` (or an equivalent flag) and promote `disk_space`
  (and arguably the unpinned-device paths) to blocking when it is true and
  `data_root` is `None`; or correct `DEVELOPMENT_STATUS.md`'s claim to say
  precisely what the code does (blocking only once a root is configured and
  found absent/too small, `NOT_RUN` when none is configured at all) so the
  documentation does not overstate the protection that exists. Given this
  checkpoint has no real participant session yet, I rate this Minor rather
  than Major — but it is exactly the kind of gap the M3/M6 "Raw files
  protected?" lens exists to catch before a real session can rely on this
  module.
- **Verification.** A test with `is_participant_session`-equivalent
  configuration true and `data_root=None` that asserts `disk_space` blocks
  the session; a corrected sentence in `DEVELOPMENT_STATUS.md`.
- **Scope blocked:** the M3/M6 recording/storage gate's eventual reliance on
  this preflight as a real safety net; does not block current synthetic work.

### M1-audio-001-R04-F04 — Minor — the claimed "`FakeStream` now models the real `device_time` path, jitter only in `entry_time`" mechanism is implemented but exercised by zero tests

- **Location:** `audio_io.py:541-551` (`FakeStream.start`, the `_epoch`
  computation), `audio_io.py:597-640` (`FakeStream.deliver`, where
  `first_frame_time = self._epoch + device_time` in device-time mode,
  independent of `jitter_s`); `jitter_s` itself (`audio_io.py:567,594,598,615`).
- **Requirement:** packet question 3 ("Does `FakeStream` now model the real
  `device_time` path... jitter only in entry_time?"); `resolution.md`
  round-2 behaviour item 8.
- **Evidence.** I confirmed by code inspection that the implementation matches
  the claim: in device-time mode, `first = self._epoch + device_time` does
  not depend on `entry` or `jitter_s` at all, while `entry = clock.now() +
  jitter_s` only ever feeds `BlockTiming.entry_time`. This is a correct,
  faithful model of the real `SoundDeviceBackend._timing`'s
  `entry - currentTime` cancellation. **However**, `grep -rn jitter_s
  --include="*.py" .` shows `jitter_s` is accepted by `FakeStream.pump`/
  `deliver`/`FakeBackend.pump_all` but **passed by no test in
  `tests/test_audio_io.py` or `tests/test_preflight.py`** — the parameter is
  wired through the whole fake backend and never once exercised. The test
  that actually demonstrates "jitter does not reach the mapping"
  (`test_realistic_callback_jitter_is_not_a_gap` in `test_timing.py`) bypasses
  `FakeStream` entirely and injects jitter directly into a hand-constructed
  `first_frame_time` argument to `CaptureTimeline.note_block`. Separately,
  the only `audio_io.py`-level test of a host API alternating block-timing
  methods (`test_a_host_api_changing_its_time_source_is_a_fault`,
  `tests/test_audio_io.py:850-861`) still goes one direction only
  (`device_time → fallback`, never back), so R03-F01's "mixed" round-trip
  fix is verified at the `CaptureTimeline` unit level (`test_timing.py`) but
  not through the actual `ContinuousRecorder`/`FakeStream` ingestion path
  production code uses.
- **Proposed fix.** Add an `audio_io.py`-level test that pumps a `FakeStream`
  in device-time mode with a nonzero `jitter_s` and asserts the resulting
  `CaptureTimeline` (reached via `ContinuousRecorder`) shows no gap/anomaly
  from the jitter alone; and a round-trip `device_time → fallback →
  device_time` test through `ContinuousRecorder`/`FakeStream`, not only
  through `CaptureTimeline` directly.
- **Verification.** Both new tests should fail if `FakeStream`'s epoch model
  were reverted to route `entry`/jitter into `first_frame_time` in
  device-time mode, or if the stale-reference bug F01 fixed were
  reintroduced.
- **Scope blocked:** confidence that the production ingestion path (not just
  the unit-level `CaptureTimeline`) benefits from the round-2 fixes the same
  way the unit tests show. By code inspection the call is a straight
  pass-through with no divergent logic, so I have no concrete reason to
  suspect different behaviour — this is a coverage gap, not a known defect.

### M1-audio-001-R04-F05 — Minor — `decisions.md` D8 still states the stale "113" test count

- **Location:** `decisions.md` D8 ("`FakeBackend`..."), the sentence "All 113
  current tests use it."
- **Requirement:** `EGM_WORKFLOW.md` §8 evidence-honesty requirements (same
  class of defect as R03-F04, applied to a document R03-F04's fix did not
  touch).
- **Evidence.** The actual count, confirmed by my own run, is **153** (74 +
  53 + 26). `decisions.md` D8 was not part of the round-2/round-3 diff for
  this figure (D3, D4 and D5 were updated with "Corrected after round 2"
  paragraphs; D8 was not), so it still reads "113," which was already stale
  at the *start* of round 2 (113 was the round-1 figure, before
  `test_preflight.py` existed at all).
- **Proposed fix.** Update D8's sentence to the current count (and consider
  phrasing it as "the current suite" rather than a number that will go stale
  again at the next test addition).
- **Verification.** None needed beyond re-reading the sentence against the
  test command's actual output.
- **Scope blocked:** none; purely a documentation-accuracy nit.

---

## Per-finding fix-verification status (R03-F01 through F10, plus C15)

Judged by tracing each fix to its code and its named test, and by reasoning
about whether that test would fail on revert (static reasoning; I did not
edit code).

| ID | Verified mechanism | Named test(s), re-traced | Status |
|---|---|---|---|
| **F01** | `_last_device_end = None` set on every block without a `device_time` (`timing.py:386`); `late_by >= DEVICE_GAP_SANITY_S` (1.0 s) becomes a `device_time_discontinuity` anomaly with `frames_lost` left unrecorded, not converted to an estimate (`timing.py:442-452`) | `test_a_fallback_run_between_device_timed_blocks_is_not_a_gap` (I re-traced the k/m/k construction by hand: `gaps == []`, `frames_lost_estimate == 0`, the repeated-flip tail); `test_a_device_clock_jump_is_an_anomaly_not_a_fabricated_loss`. Both would fail on revert: without the `None` reset, the first post-fallback block compares against a stale `_last_device_end` and fabricates a gap; without the sanity ceiling, the 1.5 s jump becomes a 72000-frame "loss" instead of one anomaly. | **VERIFIED FIXED** |
| **F02** | Rationale restated correctly (`entry - currentTime`, lateness cancels); symmetric tracker (`OFFSET_TRACK_RATE=0.01`); clamp to previous block's *start* (`timing.py:411-412`); `offset_steps` note at `>0.005` s; `device_time_went_backwards` kept distinct; `FakeStream` epoch model matches the real asymmetry | See **R04-F02** above: behaviourally correct in every exercised scenario (I hand-computed the full offset/block_time sequence for both named tests and the backwards-clock test), but the clamp itself is not shown to be load-bearing by any test — the one test that reaches its precondition passes for an independent reason. | **PARTIALLY FIXED** — behaviour correct as measured; the specific clamp mechanism is unverified (R04-F02) |
| **F03** | `integrity()["continuous"]` now requires `continuity_supported_by_basis` (`basis == "device_clock"`), with `gap_basis`/`undetectable_gap_s` always reported (`timing.py:656-694`); `note_tail_shortfall` places the gap at `frames_persisted`, not past EOF (`timing.py:528-548`, called from `audio_io.py:1012-1018` with `shortfall = frames_written - frames_persisted`) | `test_continuity_is_not_asserted_on_the_callback_time_basis` (re-traced: `gap_basis == "callback_time"`, `continuity_supported_by_basis is False`, `continuous is False` even with zero recorded gaps — exactly the previously-silent case); `test_frames_after_a_writer_failure_are_recorded_as_lost`. Both would fail on revert. | **VERIFIED FIXED** |
| **F04** | Complete manifest; verbatim `git status --porcelain`; per-file test counts verified by running each file separately | I independently reproduced 74 + 53 + 26 = 153 by running each of the three permitted per-file commands plus the combined one; I independently ran `find` and confirmed no Python/JSON file is missing from the manifest; I independently re-hashed every manifest file and all matched. | **VERIFIED FIXED (process)** |
| **F05** | Reproduce list completed (all six `validation/audio_check_*.json` commands present, including the previously-missing default-device `--playback`); timestamp sentence names both windows; superseded files carry `superseded`/`superseded_reason`/`superseded_by`/`verdict_note` | I read `validation/audio_spike.md`'s reproduce block directly (six commands, one per output file) and the timestamp sentence (now correctly distinguishes the superseded 17:28/17:29Z pair from the current reports); I parsed both superseded JSONs with the standard library and confirmed all four keys are present with correct content, and `verdict_note` correctly states the stamped `"verdict": "PASS"` would read `INCOMPLETE` under the current ladder. | **VERIFIED FIXED** |
| **F06** | `on_fault`/ledger audio-thread contract stated at the `_fault` callsite (`audio_io.py:853-861`, `:1203-1212`) and in `decisions.md` D7; `fsync` durability given its own disposition as **C18**, deferred with owner (developer) and gate (M3/M6 crash-recovery, named unpassed) in `decisions.md` D6 | No regression test is claimed or needed for a documentation-contract fix; I confirmed the docstring text exists verbatim at both `_fault` callsites and that D6/D7 both name C18 explicitly (not silently merged into C12 or dropped, which was R03's complaint). | **VERIFIED FIXED** (contract) / **legitimately DEFERRED** (fsync, as C18) |
| **F07** | `_require_attempt` raises `AudioFault` when `self.attempt is None`, called at the top of both `play()` and `arm()` (`audio_io.py:1248-1262,1259,1290`); `arm()` separately refuses a candidate whose `trial_id != self.attempt` (`audio_io.py:1291-1294`) | `test_arming_outside_an_attempt_is_refused`, `test_a_candidate_from_another_trial_is_refused` — both re-read in full; both assert `AudioFault` is raised, and both would fail on revert (removing `_require_attempt` or the `trial_id` check makes the call succeed instead of raising). | **VERIFIED FIXED** |
| **F08** | `too_late()`/`discovery_lateness` unchanged in mechanism; the regression test now drives a *reachable* trigger — a capture-timeline gap between the last speech frame and the confirming frame — through the real `SpeechSegmenter`/`PauseTimer` path, using `DEFAULT_PROFILE` (which `validate_detector_profile` accepts) | `StaleDeadlineTest.test_a_timeline_gap_can_make_a_deadline_stale_through_the_segmenter` — I re-traced its construction (20 contiguous VAD frames, an 0.8 s recorder-side gap via `note_not_persisted`, 10 more frames, frame times read from `tl.sample_to_time`) and confirmed it no longer uses an invalid hand-picked profile. | **VERIFIED FIXED** |
| **F09** | `PauseTimer(origin="run_end"\|"last_strong")` reads the matching field off `SpeechEvent` via `origin_time()` (`timing.py:1083-1093`); recorded in `as_record()` | `SilenceOriginTest` (all four methods re-read): confirms both origins' deadlines, that they differ by exactly the band dwell, and that the origin is recorded/validated (`ValueError` on an unknown origin). | **VERIFIED FIXED** |
| **F10** | `uncertainty_s = max(blocksize/samplerate, |reported - per_block|)` (`audio_io.py:1470-1472`); both latency readings in the `prompt_committed` record and the `Estimate.source` string; TeamViewer caveat in `audio_spike.md`'s header, Finding 2, Finding 3 item 4, and "Limitations to carry forward"; `check_audio.py`'s `commit_distribution` replaced `or 0.0` with an explicit `None`-check skip-and-count (`skipped_no_onset`) | I re-read `_maybe_commit` in full and confirmed the arithmetic; I read `audio_spike.md` in full and confirmed the TeamViewer sentence appears in all four places claimed; I confirmed `check_audio.py:434-436` uses an explicit `is None` check, not `or 0.0`, for the three onset components. One residual `or 0.0` remains at `preflight.py:647` but I traced it and it is inert: `cand.device_offset_s` is only read after `if not cand.committed: continue`, and `_maybe_commit` always sets a real float there before committing, so this is not a reachable "unknown treated as zero" case. | **VERIFIED FIXED** |
| **C15 residual** | `tools/check_audio.py duplex_check(..., input_device=None)` takes `--input-device` and gates on `capture_possible` rather than `capture_available` (`tools/check_audio.py:522-533`) | No dedicated unit test (it is a bench-tool CLI path); I confirmed by reading the code that the parameter is wired through to `ContinuousRecorder(device=input_device)` and that the blocking condition now reads `info.get("default_capture_available")`/`capture_possible` correctly rather than conflating them, matching C15's original complaint. | **VERIFIED FIXED** |

### Invariants R03 confirmed after round 1 — still hold?

| Invariant | Verdict |
|---|---|
| No output before the deadline, none before participant speech | **Holds.** `_maybe_commit` returns while `now < cand.deadline` (`audio_io.py:1437-1439`); `PauseTimer.note_offset` returns early when `not self.armed` (`timing.py:1113-1116`), and `armed` is only set by `note_onset`. |
| The configured interval added exactly once, to the speech offset | **Holds.** `deadline = silence_since + threshold_s` with `silence_since` set from `origin_time(event)`, never from `confirmed_time`; `known_at()` takes `max(deadline, confirmed_at)`, never a sum. |
| Cancellation semantics (`CancelOutcome`, allowance only consumed on commit) | **Holds**, unchanged from round 1/2; `_require_attempt`/`begin_attempt` (F07) tightens the scoping around it without altering the four outcomes. |
| Exact file bytes; atomic publication | **Holds.** `_callback_body` enqueues before any timeline counting (unchanged since C2); `finalize()`'s `os.replace` is still the sole publication step; durability (not atomicity) remains the deferred C18 point. |
| No `Estimate` with `method="measured"` anywhere | **Holds.** `grep -n MEASURED timing.py audio_io.py preflight.py tools/check_audio.py` shows `MEASURED` only as the constant definition, in `_METHODS`, and in `is_measurement`; no `Estimate(...)` call site in any of the four files passes it. |

## The preflight — focused first review

Answering the packet's five explicit preflight questions directly:

1. **Is anything it tells an operator stronger than what it measured?** No
   case found. `onset_delay_target`'s detail string explicitly says "this is a
   device-latency estimate, not an acoustic measurement, and the target is a
   proposal rather than a frozen tolerance" every time it is reported;
   `acoustic_onset` is unconditionally `NOT_RUN`; `max_onset_delay_is_frozen_tolerance`
   is hard-coded `False` in the recorded config. `verdict()` cannot return
   `PASS` while any check is `NOT_RUN`/`BLOCKED` (traced in full; confirmed by
   my own `python tools/check_audio.py` run and by the committed
   `preflight_wasapi.json`, which reads `INCOMPLETE_WITH_WARNINGS` with 5
   `NOT_RUN` checks, never `PASS`).
2. **Do blocking/warning rules match `config/experiment.json` and the
   documented decision?** Yes. `timing_policy.blocking: false` in
   `config/experiment.json` is read into `cfg.timing_blocking`, and
   `onset_delay_target`'s status is `WARN` (not blocking) when the target is
   missed and `timing_blocking` is false, `FAIL` (blocking) when true —
   matching `DEVELOPMENT_STATUS.md`'s "warn-and-record... `timing_policy.blocking`
   flips that" sentence exactly, and matching
   `tests/test_preflight.py`'s `TimingPolicyTest` (both branches tested).
   `check_capture: false` in the committed config is read into
   `cfg.check_capture`, and the microphone-opening code in `measure_capture`
   is gated on it (`if not cfg.check_capture: return [NOT_RUN "...the
   microphone was not opened"]`) — matching "never open the microphone
   unless `check_capture` is enabled." The one documented-vs-actual
   discrepancy I found is narrower than this (the disk-space/participant-flag
   gap, **R04-F03**).
3. **Does it honor this layer's contracts?** Yes for `begin_attempt`
   (`measure_output` calls it before every `arm()`) and `has_audible_onset`
   (`measure_output` checks `clip.has_audible_onset` before running any
   commit trial and reports `FAIL` if not). The `CancelOutcome` contract is
   honored in the sense that cleanup calls `cancel_candidate`, but
   `measure_output` never checks the returned outcome (unlike
   `check_audio.py`'s `commit_distribution`, which does) — a minor
   observability gap, not a correctness one, folded into **R04-F01** since
   the sharper problem is the *missing* cancel call on the timeout path, not
   the ignored outcome on the normal path.
4. **Can its verdict ever read as a pass with unrun checks?** No. Traced
   `PreflightReport.verdict()` in full: any `NOT_RUN`/`BLOCKED` count forces
   `INCOMPLETE`/`INCOMPLETE_WITH_WARNINGS`, never `PASS`, regardless of
   warnings elsewhere. Confirmed by the real-hardware evidence
   (`preflight_wasapi.json`: 8 PASS, 5 NOT_RUN, 1 WARN → `INCOMPLETE_WITH_WARNINGS`,
   `may_start: true`) and by `tests/test_preflight.py`'s
   `test_a_report_with_unrun_checks_never_calls_itself_a_pass`.
5. **Does it pin devices by identity and refuse to fall back?** Yes for the
   path exercised: a pinned key that resolves to zero or more-than-one device
   is a blocking `FAIL` (`preflight.py:445-463`, tested by
   `test_a_pinned_device_that_is_gone_blocks_the_session` and
   `test_an_ambiguous_pinned_identity_blocks_the_session`), and a resolved
   pinned device is recorded with `pinned: True`. The one gap is that nothing
   *requires* a device to be pinned at all for a session marked
   `is_participant_session: true` — covered under **R04-F03**.

**Preflight-specific new findings:** R04-F01 (Major, shared with
`check_audio.py`) and R04-F03 (Minor). No other defect found in
`preflight.py`/`config/experiment.json`/`tests/test_preflight.py` within the
time available; the module's core decision ladder, device-pinning refusal,
and microphone-gating are all implemented as documented and the 26-test suite
genuinely exercises the documented decision matrix (device resolution ×
3 cases, timing policy × 3 cases, capture gating × 2 cases, stimulus/storage
× 4 cases, config loading × 4 cases).

## Open research decisions / evidence gaps

Separate from code defects; per `EGM_WORKFLOW.md` §8 these may be deferred
without blocking synthetic work, but their affected release remains unpassed.
I have no authority to close any of these.

1. **Silence-origin choice for the live deadline** (`run_end` vs.
   `last_strong`) — owner: research director, before the timing tolerance is
   frozen. Unchanged from round 2: now configuration (`PauseTimer(origin=...)`),
   default `run_end`.
2. **Lateness budget** (default 50 ms) — owner: research director with the
   detector profile.
3. **Whether a trial with a counted recorder-side gap is analysable** —
   owner: research director; the code flags rather than decides, and F01's
   fix removed the fabricated-gap paths that would previously have
   over-triggered this flag.
4. **Detector profile, 100 ms candidate target, recall-cap origin** — all
   proposals (`decisions.md` D1, D4, D5; `goal.md` §14).
5. **Microphone, placement and calibration** — **BLOCKED on hardware**: this
   PC has no suitable input device (two Bluetooth WDM-KS endpoints only).
   Every microphone-side claim in this checkpoint, including every claim in
   `preflight.py`'s `measure_capture`, rests on the fake backend.
6. **All onset/device figures are estimated, not measured, and were taken
   over TeamViewer** — correctly and now consistently disclosed (R03-F10's
   fix held up under my re-check) in `audio_spike.md`, `decisions.md` D5, and
   the committed JSON `source` fields.
7. **C12 and C18**, deferred to M3 with named owner (developer) and gate
   (M3/M6 crash-recovery evidence, unpassed) — I re-confirm both deferrals as
   legitimate: owner and reason are stated, the chosen fix is specified
   (raw-PCM-plus-sidecar for C12; flush/fsync for C18), and neither blocks the
   M3 controller from being built — the attempt stays detectable as
   incomplete either way, and `os.replace` atomicity (the part that *would*
   block correctness) is unaffected. **C16** is likewise a legitimate
   deferral to M3 (the controller that would own binding `PromptCandidate.deadline`
   to a `PauseTimer` does not exist yet); R03's observation that F07/R04-F01's
   shape of defect ("a seam this layer enforces by contract, not by
   construction") recurs here still applies and should inform M3's design.
8. **M1 as a milestone is not complete** — the avatar clock-adapter
   demonstration (`goal.md` §7/§12) does not exist; scoped separately as
   `M1-avatar-002`.

## Verdict

**NEEDS_FIXES**

**Scope.** This verdict covers the 17-file manifest in
`packet-round-3.md` (all digests re-verified unchanged before and after my
checks), the complete working tree confirmed by my own `find` and `git
status`, against `goal.md` v0.3 §§4-7, 10, 12, 13, through the
fix-verification stage for R03-F01..F10/C15 and the first-review focused
stage for `preflight.py`/`config/experiment.json`/`tests/test_preflight.py`.

**Why not a pass.** Nine of R03's ten findings (plus the C15 residual) are
**VERIFIED FIXED**: the mechanisms `resolution.md` claims are genuinely in the
code, the named tests exercise the scenarios they claim to, and I judge each
would fail on revert. F06 is correctly a **FIX + legitimate DEFER**, not a
dropped finding. **F02 is PARTIALLY FIXED**: its behaviour is correct in
every scenario I could check by hand-computed arithmetic, but the specific
"clamp to the previous block's start" mechanism — the thing that makes
`sample_to_time` provably non-decreasing rather than merely non-decreasing
in the cases tested — is not demonstrated by any test to actually be
load-bearing (**R04-F02**). Independently, the first review of `preflight.py`
found a real, reachable crash path shared with the already-reviewed
`tools/check_audio.py`: a commit-probe timeout during the measurement loop
leaves an armed candidate that crashes the *next* probe's `begin_attempt()`
with an unhandled `AudioFault`, defeating the module's own graceful-FAIL path
on exactly the flaky hardware (TeamViewer-redirected, Bluetooth WDM-KS) this
project has already documented (**R04-F01**). Both are Majors squarely within
this round's scope. Two further Minors (**R04-F03**, a disk-space check that
does not distinguish a participant session from a dev session despite a
config flag existing for exactly that purpose; **R04-F05**, a stale test
count in `decisions.md` D8) and one Minor coverage gap (**R04-F04**, the
`FakeStream`/round-trip mechanisms are correct by inspection but untested at
the `audio_io.py` integration level) round out the findings.

Per `EGM_WORKFLOW.md` §8, this is the third iteration of the bounded loop and
none of R04-F01 through R04-F05 reverses an earlier accepted design decision
— they are new defects/gaps in the round-2 mechanism and in the newly-reviewed
`preflight.py`, not contested re-litigation of round-1 or round-2 choices.
The coordinator should weigh that against the stopping rule in deciding
whether to fix these two Majors in a fourth pass or to record them as a
summarized residual for the user, per that section; that decision is not
mine to make.

**What this verdict does not cover.** Participant readiness; acoustic
validation of anything; approval of any research-owned decision (I have none
to give); the completeness of M1 as a milestone (the avatar clock-adapter
checkpoint does not exist); any hardware behaviour I did not re-measure
(every device figure cited above was verified by reading already-committed
evidence, not by re-running `--playback`/`--survey`/`--commit-trials`/`--duplex`/
`preflight.py`, all of which I was instructed not to run). A fake-backend
pass is not hardware validation, and nothing here establishes an acoustic
onset.
