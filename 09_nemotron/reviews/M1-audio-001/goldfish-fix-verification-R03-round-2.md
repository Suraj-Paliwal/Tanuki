# Goldfish review — M1-audio-001 / fix-verification / R03 / round 2

## Provenance and scope

- **Fresh context: yes.** Separate agent session with no development-chat
  history. Isolation mechanism: a new subagent thread whose only inputs were
  the dispatch prompt and the files I read from disk. I did not see any other
  reviewer's round-2 verdict. Per `EGM_WORKFLOW.md` §6 this is a *recheck*, so
  reading the round-1 finding IDs, fixes and dispositions was in scope and I
  did read them.
- **Snapshot:** packet `reviews/M1-audio-001/packet-round-2.md`, base commit
  `eeb0f0e2f4da98cf1e2cfade27a3c49a4b840479` (which captures **none** of the
  reviewed work — everything is staged-but-uncommitted or untracked, as the
  packet states).
  - I independently recomputed all **15** SHA-256 digests in the manifest
    **before** my checks and **again after** them. **All 15 matched the packet
    exactly, both times**, including the two files declared unchanged-and-
    superseded (`audio_check_wasapi.json`, `audio_check_playback.json`). No
    coverage of a manifest file is stale.
  - **However, the working tree contains three files that are in neither the
    manifest nor the packet's description of `git status`:** untracked
    `preflight.py` (39,627 bytes, which imports from both `audio_io` and
    `timing`), untracked `tests/test_preflight.py` (26 tests), and
    `config/experiment.json`. The packet asserts "Target edits are paused for
    the duration of this review" and lists only `packet-round-2.md` and
    `resolution.md` as `??`. See finding **F04**; this does not invalidate my
    coverage of the 15 manifest files, but it does mean the packet's headline
    regression figure no longer reproduces.
- **Stage/lenses:** fix-verification. Lenses as dispatched — timing and
  state-machine correctness, concurrency and cancellation races,
  recording/storage integrity, evidence honesty (estimated vs measured), via
  `EGM_WORKFLOW.md` §5 rows "Audio feasibility, M1" and "Recording/storage,
  M3/M6".
- **Named readiness question** (from the packet): are the eight consolidated
  round-1 Majors actually fixed by the mechanism `resolution.md` claims; did
  the fixes introduce new defects or unnecessary complexity; do the corrected
  evidence records now state what was executed. Explicitly *not* asked, and
  **not** answered here: participant readiness, acoustic validation, approval
  of any research decision, or whether M1 as a milestone is complete (it is
  not — the avatar clock-adapter checkpoint `M1-avatar-002` does not exist).
- **Files inspected in full:** `packet-round-2.md`, `EGM_WORKFLOW.md`,
  `reviewers/GOLDFISH.md`, `AGENTS.md`, `goal.md` §§3–7, 10, 13, 14,
  `resolution.md`, `timing.py` (all 1229 lines), `audio_io.py` (all 1478),
  `tools/check_audio.py` (all 623), `tests/test_timing.py`,
  `tests/test_audio_io.py`, `decisions.md`, `requirements.txt`, `.gitignore`,
  `validation/audio_spike.md`, all five `validation/audio_check_*.json`,
  `goldfish-focused-R01-round-1.md` and `goldfish-critic-R02-round-1.md`
  (outlines plus the findings bearing on the dispositions I questioned).
- **Referenced sources unavailable:** none needed were missing. I deliberately
  did **not** review `preflight.py`, `tests/test_preflight.py` or
  `config/experiment.json` — they are outside the declared manifest and outside
  this checkpoint's scope.
- **Tools actually executed** (only the two the packet permits, both inspected
  before running, run from `C:/Users/suraj/Downloads/Tanuki/09_nemotron` with
  `PYTHONPYCACHEPREFIX` pointed at my own scratch directory under the system
  temp directory):

  | Command | Result |
  |---|---|
  | `python -m unittest discover -s tests -p "test_*.py"` | **Ran 139 tests in 0.487s — OK.** Not 113 as the packet, `resolution.md` and `audio_spike.md` all state. `test_timing` 63 + `test_audio_io` 50 = 113; the undeclared `test_preflight` contributes the other 26. |
  | `python tools/check_audio.py` | **8 PASS, 2 NOT_RUN, verdict `INCOMPLETE`** — reproduces the packet exactly, including both inventory warnings and the two named non-default WDM-KS input devices. |

- **NOT_RUN by me, by instruction:** `--playback`, `--survey`,
  `--commit-trials`, `--duplex`. I therefore did **not** re-measure any device
  figure; I verified the device rows only by reading the committed JSON. I also
  did not write or run any scratch script of my own, since the packet permits
  exactly two commands — every dynamic claim below that is not one of those two
  results is marked as derived by static reasoning.
- **Scratch path used:** a directory under the system temp directory for
  bytecode only. Nothing was written inside `09_nemotron` except this report.

## My understanding

This checkpoint is the device-and-timing floor under the experiment
controller: it owns the microphone and the speakers natively so that no
protocol interval is ever computed from browser or wall-clock time. A
`ContinuousRecorder` keeps one uninterrupted file per attempt, writing through
a queue so the PortAudio callback never touches disk, and a `CaptureTimeline`
keeps a piecewise map from sample index in that file back to controller time —
piecewise because when the device or the writer loses audio the honest record
is a gap plus a new segment, never invented silence that would shift every
later speech boundary. A `SpeechSegmenter` turns detector probabilities into
onset/offset boundaries dated where they actually happened, a `PauseTimer`
adds the assigned 0.5/1.0/2.0 s threshold to that offset exactly once and
never to the detector's confirmation time, and an `OutputPlayer` holds one
session-long output stream in which the single encouragement is *armed* with
its eligibility deadline and commits only inside the callback that first
observes the deadline has passed — so "nothing audible early" is structural
rather than a matter of timer accuracy, and a resumption before that instant
cancels the clip without spending the one-prompt allowance.

Round 2's question is narrower: eight consolidated Major defects were found by
two independent reviewers and all eight were dispositioned `FIX`. My job is to
trace each fix to its code and its regression test, to ask whether the named
test would actually fail if the fix were reverted, to check that no fix broke
an invariant that held in round 1, and to check that the evidence records now
say what was executed rather than what was hoped. Two Minors (C12, C16) were
deferred to M3 and I must judge whether those deferrals are legitimate or
whether either one blocks the M3 controller that will be built on this layer.

## Findings

### M1-audio-001-R03-F01 — Major — device-clock gap detection turns unvalidated device-time deltas into fabricated lost-frame counts; reachable on this PC's only input devices

- **Location:** `timing.py:375-392` (`CaptureTimeline.note_block`, the gap
  branch), with `timing.py:400-403` (`_last_device_end` is assigned **only**
  inside `if device_time is not None`) and `timing.py:323`.
- **Requirement:** `goal.md` §13 "clock/sample mapping and dropped-frame
  detection are **verified**"; §6 "Do not continue a trial while recording is
  broken"; `EGM_WORKFLOW.md` §5 row "Recording/storage, M3/M6" ("Faults/disk
  failure recoverable? No silent completion after crash?"); packet behaviour
  item 2 and `decisions.md` D3.
- **Evidence and failure case (static trace).** `_last_device_end` is never
  invalidated when a block arrives without a device time. During a run of
  `method="fallback"` blocks, `note_block` takes the `else` branch and leaves
  `_last_device_end` frozen at the value from the last `device_time` block.
  The first block that again reports a device time is then compared as
  `late_by = device_time - self._last_device_end` (`timing.py:376`) against the
  2 ms device tolerance, where `_last_device_end` is stale by the entire
  fallback interval. For *N* fallback blocks of 10 ms, `late_by ≈ N × 0.010`,
  so the code records a `discontinuity` gap of `round(late_by × 48000)`
  "lost" frames — 480 × *N* frames of audio that were never lost, added to
  `device_frames` and to `frames_lost_estimate`, with `continuous` set false.
  **This is reachable on this hardware, not hypothetically:** the committed
  survey evidence shows WDM-KS reporting *both* methods inside a single
  one-second stream —
  `audio_check_survey.json`, `output_survey[Windows WDM-KS]`:
  `"block_timing_method": ["device_time", "fallback"]` — and the only two
  input-capable devices on this PC are WDM-KS endpoints (`capture_possible:
  true`, `input_devices` lists both). A WDM-KS capture that flips methods
  repeatedly would therefore fabricate one gap per return to `device_time`,
  flagging every attempt and inflating the dropped-frame evidence. The existing
  test `CaptureFaultContainmentTest.test_a_host_api_changing_its_time_source_is_a_fault`
  (`tests/test_audio_io.py:811`) switches `device_time → fallback` **once and
  never back**, so it cannot catch this.
  A second case with the same root: nothing bounds `late_by` at all, so a
  forward step in the device clock (the mirror of the backwards step
  `test_a_backwards_device_time_does_not_kill_the_stream` exercises) is
  converted directly into a lost-frame count — a 1 s step becomes "48000
  frames lost".
- **Proposed fix.** (a) Set `self._last_device_end = None` on every block where
  `device_time is None`, so the next device-timed block re-anchors instead of
  measuring against a stale end; (b) bound the conversion: when `late_by`
  exceeds a sanity ceiling (say one second, or the fallback run's own duration),
  record a `device_time_discontinuity` anomaly with `frames_lost` left
  `None`/unknown rather than an invented `ESTIMATED` count, since
  `TimelineGap.method = ESTIMATED` currently asserts the number means something.
- **Verification.** A test that pumps *k* `device_time` blocks, then *m*
  `method="fallback"` blocks, then *k* more `device_time` blocks, and asserts
  `tl.gaps == []`, `gap_basis == "mixed"` and `frames_written == (2k+m) ×
  block`; plus a test that a one-second forward step in `_device_time` produces
  an anomaly rather than a 48000-frame `frames_lost`.
- **Scope blocked:** the recording-integrity evidence for `M1-audio-001`, and
  any M3/M6 dropped-frame claim derived from `frames_lost_estimate`.

### M1-audio-001-R03-F02 — Major — the minimum-biased device→controller offset can step the mapping's time labels backwards; its stated justification does not describe the real backend, and the fake backend does not model the real asymmetry

- **Location:** `timing.py:363-369` and `timing.py:329`
  (`OFFSET_RISE_RATE`), `timing.py:405-411` (the anchor and anomaly record),
  `audio_io.py:466-487` (`SoundDeviceBackend._timing`), `audio_io.py:585-620`
  (`FakeStream.deliver`).
- **Requirement:** `goal.md` §6 "Log the mapping back to original audio sample
  indices"; §7 "Keep time within the audio controller: a monotonic clock plus
  input/output sample positions"; packet question 3 ("is the minimum-biased
  offset estimator safe against a monotonicity violation in the mapping");
  `goal.md` §13 "clock/sample mapping … verified".
- **Evidence and failure case (static trace; arithmetic given so it can be
  checked without running anything).** The estimator takes the running
  *minimum* of `observed = first_frame_time - device_time` and drops to any
  lower observation **immediately** (`timing.py:365-366`), while rising only at
  0.1 % of the error per block. `block_time = device_time + self._offset`
  (`timing.py:369`) and `end_time = block_time + frames/rate`
  (`timing.py:398`). Consecutive end times therefore differ by
  `block_s + (offset_new − offset_prev)`, which is **negative whenever the
  offset drops by more than one block duration** (10 ms at 480/48 kHz).
  Nothing clamps `block_time`: the only clamp is inside
  `StreamTimebase.anchor`, which clamps its *own* anchor and returns an
  anomaly string that is appended to `self.anomalies` — and `anomalies` makes
  `integrity()["continuous"]` false (`timing.py:583-584`). So a perfectly
  ordinary sequence where the **first** callback is late by 30 ms and a later
  one is not drops the offset by 30 ms, steps the segment's time labels back by
  20 ms, and records a spurious `clock_went_backwards` anomaly that marks a
  good recording non-continuous. The existing test
  `test_realistic_callback_jitter_is_not_a_gap`
  (`tests/test_timing.py:211-232`) passes only because its jitter list begins
  with `0.0`, which makes the first observation the minimum; reorder it to
  `[0.030, 0.0, …]` and, by the arithmetic above, it should fail. (I could not
  execute that variant — only the two packet-permitted commands were run.)
  The same mechanism is what makes
  `test_a_backwards_device_time_does_not_kill_the_stream`
  (`tests/test_audio_io.py:797`) pass: it asserts `continuous` is false, and
  what makes it false is precisely this unclamped backwards step.
- **Secondary, and the direct answer to packet question 3.** The code's
  justification — "A callback can only ever run late, so the observed offset is
  biased upwards" (`timing.py:316-321`) — describes the *fake* backend, not the
  real one. In `SoundDeviceBackend._timing`, `first_frame_time = entry +
  (target − current)`, so
  `observed = first_frame_time − device_time = entry − current`: the difference
  between `perf_counter` and PortAudio's `currentTime`, **both sampled at the
  same callback entry**. Callback lateness cancels out of that difference, so
  it is not a late-only quantity at all; it is a clock-epoch difference whose
  sign of drift depends on the host API, and minimum-biasing it will track
  drift instantly in one direction and lag by ~10 s (0.001/block) in the other.
  In `FakeStream.deliver` (`audio_io.py:604-612`), by contrast,
  `first = entry − block_s − latency` with `entry = clock.now() + jitter_s`,
  so jitter flows fully into `observed` and `device_time` is independent. **The
  fake backend's two-clock model does not represent the real asymmetry** — it
  over-models it in the `device_time` path (where the real controller estimate
  is already anchored to the device clock) and matches it only in the
  `fallback` path. `decisions.md` D3's claim that "callback-entry time carries
  12-40 ms of scheduling jitter, so no threshold on it could separate jitter
  from a lost 10 ms block" is therefore correct for the fallback path and
  inaccurate for the device-time path it was used to justify. The *behaviour*
  change is still an improvement; the *rationale* and the *test model* are not
  what they claim.
- **Proposed fix.** Clamp `block_time` to `max(block_time, previous block end)`
  and record a downward offset correction as its own non-fatal
  `device_offset_step` note, distinct from `clock_went_backwards` (a real
  clock anomaly must stay distinguishable from the estimator improving).
  Restate the estimator's rationale in terms of what `observed` actually is on
  the real backend, and give `FakeStream` a mode in which `first_frame_time` is
  derived from `device_time` plus a stable epoch offset, matching
  `SoundDeviceBackend` in `device_time` mode.
- **Verification.** Reorder the jitter list in
  `test_realistic_callback_jitter_is_not_a_gap` so the first block is the
  latest one, and assert `clock_anomalies == []`, `continuous is true`, and
  `sample_to_time` non-decreasing across every sample boundary; add a test that
  `sample_to_time` is monotonic across a segment boundary that coincides with
  an offset drop.
- **Scope blocked:** the sample→time mapping claim for `M1-audio-001`, and the
  "attempt flagged" semantics M3 will consume.

### M1-audio-001-R03-F03 — Major — `integrity()["continuous"]` can be `true` on a basis that the module's own comment says cannot see a lost block, and the `writer_shortfall` gap points past the end of the file

- **Location:** `timing.py:550-585` (`integrity`, especially
  `"continuous"` at 583-584 and `"gap_basis"` at 579-582),
  `timing.py:274-281` (the `DEFAULT_GAP_TOLERANCE_S` comment),
  `audio_io.py:983-991` (the `finalize()` shortfall reconciliation).
- **Requirement:** `goal.md` §13 "Full participant audio survives encouragement
  overlap; clock/sample mapping and dropped-frame detection are verified";
  §6 "Any unexpected recording … failure … flags the attempt";
  `EGM_WORKFLOW.md` §6 "missing evidence is not PASS"; packet behaviour item 4.
- **Evidence and failure case.** (a) `continuous` is computed from
  `frames_written > 0 and not self.gaps and not self.anomalies and complete`.
  It does **not** consider `gap_basis`. On the callback-time basis the tolerance
  is 80 ms, and the module says plainly why that is unsafe:
  "*At that width a single lost 10 ms block is invisible*"
  (`timing.py:279-280`). So a recording that silently lost up to about eight
  consecutive 10 ms blocks can report `continuous: true`, because nothing
  compares `frames_written` against an expected duration and
  `frames_persisted == frames_written` holds. That is honest in the *code
  comment* and dishonest in the *field a consumer reads*; `goal.md` §13's
  dropped-frame requirement is not met on that basis. This is not a corner
  case here: per F01, WDM-KS — the only input host API available on this PC —
  uses the fallback part of the time.
  (b) The `finalize()` reconciliation is arithmetically correct for the case it
  targets (queued blocks lost when the writer dies are necessarily the tail of
  the file, so earlier indices still map correctly — I traced this and agree
  with the packet's "failed attempts" note), but the gap it records is placed
  at `file_sample = timeline.frames_written`, i.e. the *delivered* count, which
  is `shortfall` frames **past the end of the published WAV**. A reader using
  `gaps[].file_sample` to locate the discontinuity in the file gets an index
  beyond EOF, and `note_not_persisted` then opens a trailing empty segment at
  that index.
- **Proposed fix.** (a) Require `blocks_without_device_time == 0` for
  `continuous`, or keep `continuous` and add an explicit
  `undetectable_gap_s: 0.080` / `continuity_basis` field and make `continuous`
  false whenever the basis is `callback_time` or `mixed`; either way a consumer
  must not be able to read "continuous" as "no block was lost" when the basis
  cannot support it. (b) Clamp the `writer_shortfall` gap's `file_sample` to
  `frames_persisted` and suppress the trailing empty segment.
- **Verification.** A test that a fallback-basis timeline with a silently
  omitted block reports `continuous is False` (or carries the explicit
  undetectable-gap bound); and a test that every `gaps[].file_sample` is
  `<= RecordingResult.frames`.
- **Scope blocked:** the M3/M6 recording-integrity gate.

### M1-audio-001-R03-F04 — Major — the snapshot contains undeclared files, and the packet's named regression evidence does not reproduce

- **Location:** `packet-round-2.md` "Snapshot identity" and the "All round-1
  fixes regress-tested" row of "Acceptance checks and actual evidence";
  `resolution.md` "Checks after the fixes"; `validation/audio_spike.md`
  Finding 4. Tree: untracked `preflight.py`, `tests/test_preflight.py`,
  `config/experiment.json`.
- **Requirement:** `EGM_WORKFLOW.md` §6 — "Complete relevant file list
  including dependencies, tests, fixtures and **untracked files**"; "A commit
  hash alone is insufficient for a dirty tree"; §3.4 "Pause edits to its target
  until reviewers return. You may work on unrelated files only if they do not
  change dependencies or evidence under review"; §8 "An affected checkpoint
  passes only when its required executed checks pass … and fresh review covers
  the **current snapshot**."
- **Evidence.** `git status --porcelain` in this tree shows two `??` Python
  paths the packet does not mention — `09_nemotron/preflight.py` (39,627
  bytes) and `09_nemotron/tests/test_preflight.py` — plus an unmentioned
  `config/experiment.json`. `preflight.py` is **not** unrelated: it imports
  directly `from audio_io import …` and `from timing import …`
  (`preflight.py:45,56`), i.e. it is an in-tree consumer of the exact layer
  under review, created after the packet (file mtimes 03:18 against the
  `reviews/` directory's 03:13). The consequence I can measure: the packet's
  own acceptance command,
  `python -m unittest discover -s tests -p "test_*.py"`, returns
  **139 tests OK**, not the **113** claimed in three places (packet,
  `resolution.md`, `audio_spike.md`). 63 + 50 = 113 comes from the two declared
  test files; `test_preflight` adds the other 26. The claimed figure is not
  reproducible from the stated command in the stated directory.
- **Proposed correction.** Either (a) revert `preflight.py`,
  `tests/test_preflight.py` and `config/` out of the working tree for the
  duration of this checkpoint and restate the figure as "113 tests in the two
  declared test files", or (b) regenerate the manifest to include all three
  files with digests, state the real total (139) and the per-file split, and
  record that an undeclared consumer of `audio_io`/`timing` now exists — in
  which case its contract assumptions on this layer need review before M3
  builds on it. Do not leave the packet asserting that edits were paused when
  two new modules landed after the freeze.
- **Verification.** `git status --porcelain` output pasted into the packet
  verbatim rather than described, plus the test count printed by the named
  command; both re-checked at dispatch and on return, as §6 requires.
- **Scope blocked:** the §8 "fresh review covers the current snapshot"
  condition for `M1-audio-001`. My own coverage of the 15 manifest files is
  **not** stale — their digests matched before and after.

### M1-audio-001-R03-F05 — Minor — C17 is only partly fixed: one evidence command is still unlisted, the timestamp note is wrong for the current reports, and the two superseded reports still read `"verdict": "PASS"`

- **Location:** `validation/audio_spike.md` lines 7-9 (environment note) and
  its "Reproduce with" block; `validation/audio_check_wasapi.json` and
  `validation/audio_check_playback.json` (`"verdict": "PASS"` with two
  `NOT_RUN` checks each).
- **Requirement:** `EGM_WORKFLOW.md` §6 "Evidence files with command, working
  directory, tool/dependency versions, exit result, brief output and
  limitations"; §8 "Do not … erase failed runs"; C17's stated fix ("the missing
  command added to the reproduce list") and C13's purpose.
- **Evidence.** (a) The reproduce block lists six commands and accounts for
  `audio_check_survey.json`, `audio_check_commit_wasapi.json`,
  `audio_check_commit_default.json` and `audio_check_wasapi.json`. **No command
  in the list produces `audio_check_playback.json`** (it would be
  `--playback --out validation/audio_check_playback.json`, the default-device
  run: its `playback_stream` detail reports 180.0 ms, i.e. MME). One evidence
  file is still unreproducible from the record — the exact defect C17 named.
  (b) The record states "the JSON reports carry UTC timestamps from
  2026-11-16T17:2x". The three **current** reports are
  `18:07:16Z`, `18:07:33Z` and `18:07:38Z`; only the two **superseded** files
  are at `17:28:34Z` and `17:29:24Z`. The note describes the retracted run, not
  the evidence it heads.
  (c) Both superseded JSONs still carry `"verdict": "PASS"` internally
  (`{'PASS': 11, 'NOT_RUN': 2}`), because they predate the C13 fix. The packet
  marks them superseded, but nothing in `validation/` or inside the files does,
  so anyone reading the evidence directory finds two PASS-stamped reports whose
  figures `audio_spike.md` says must not be quoted.
- **Proposed fix.** Add the missing `--playback` default-device command to the
  reproduce list; correct the timestamp sentence to name both windows; and mark
  the two superseded files in place — rename to `*.superseded.json` or add a
  top-level `"superseded_by"` / `"superseded_reason"` key (and, since the
  packet freeze is what forbids editing them now, do it as the first step after
  this review rather than quietly).
- **Verification.** Every `validation/audio_check_*.json` is produced by exactly
  one listed command; no file in `validation/` reads `"verdict": "PASS"` unless
  it is current and has no `NOT_RUN`/`BLOCKED` check.

### M1-audio-001-R03-F06 — Minor — two round-1 sub-findings lost their disposition: the `on_fault` audio-thread contract (C14) and `os.replace` durability (C12)

- **Location:** `audio_io.py:833-841` and `audio_io.py:1176-1184` (`_fault`
  calls the controller-supplied `self._on_fault(rec)` synchronously — in
  `OutputPlayer` from inside `_callback` while holding `_lock`);
  `decisions.md` D7 (lines 189-201, which states the non-blocking rule for
  `guard` only); `audio_io.py:995-1000` (`os.replace` with no `flush`/`fsync`);
  `resolution.md` C12 and C14 rows.
- **Requirement:** `EGM_WORKFLOW.md` §8 — allowed dispositions are `FIX`,
  `CONTEST`, `DEFER` (with named owner, reason and affected gate) or
  `DUPLICATE`; "Do not silently downgrade severity"; `goal.md` §10 "Write
  incrementally and finalize atomically where appropriate".
- **Evidence.** R01-F11 asked for the thread-and-latency contract to be stated
  for **`on_fault` and for ledger writes from the audio path**, not only for
  `guard`. C14's recorded fix is "`CaptureTimeline` mutations are under a lock;
  the audio-thread contract is documented on the callback, not only on
  `guard`." The lock is there and the callback docstring now says "Must never
  raise and never touch the disk" — but that is a contract on the *implementer
  of the callback*, not on the *controller-supplied `on_fault`*, which is still
  invoked on the audio thread with no documented constraint anywhere
  (`grep on_fault decisions.md` returns nothing). The half of the finding that
  names the M3 seam is unaddressed and undispositioned.
  R01-F12 likewise had two parts: the zero-frame `.partial` header (deferred as
  C12, correctly) **and** "no `fsync` of the file or the containing directory
  before `os.replace`, so durability under power loss is asserted rather than
  established". `grep fsync audio_io.py` returns nothing. C12's summary line
  names only the header half, so the durability half appears in no disposition
  at all. (The packet's invariant "`os.replace` publication stays atomic" does
  still hold — atomicity is not the issue; durability is.)
- **Proposed fix.** State the `on_fault` / audio-path-ledger thread and latency
  contract in D7 and at the `_fault` callsite (or deliver faults through a
  queue drained by the controller thread); and give the `fsync` point an
  explicit disposition — `FIX` (flush + `os.fsync` the file before
  `os.replace`, fsync the directory after) or `DEFER` to the same M3 storage
  checkpoint as C12, with the gate named.
- **Verification.** A test that a deliberately slow `on_fault` does not extend
  callback work (or that faults are queued); for durability, state it as a
  documented M3 acceptance check rather than a test on this layer.

### M1-audio-001-R03-F07 — Minor — C4's per-attempt scoping is opt-in; `arm()` does not require `begin_attempt()`, so an M3 controller that omits it reproduces the round-1 behaviour

- **Location:** `audio_io.py:1198-1219` (`begin_attempt`),
  `audio_io.py:1242-1262` (`arm`, which checks the armed slot but never
  `self.attempt`), `audio_io.py:1130` (`self.attempt: str | None = None`).
- **Requirement:** `goal.md` §6 "`RECALL` has a one-use encouragement flag";
  the packet invariant "commitment consumes the allowance and is reported as
  such"; C4's purpose.
- **Evidence.** `begin_attempt` is the whole of C4's fix: it is what clears
  `_committed`, `_vetoed`, `_candidate` and `_guard`. Nothing requires it.
  `arm()` succeeds with `self.attempt is None` and with a stale `_committed`
  from a previous trial, which is exactly the round-1 defect
  ("`_committed` was session-scoped and never cleared, contaminating later
  trials' records"). The reviewed test suite demonstrates the gap itself:
  `OnsetEstimateComponentsTest._commit` (`tests/test_audio_io.py:563`) arms
  without ever calling `begin_attempt`, and
  `test_the_onset_estimate_is_not_the_commit_delay_plus_a_clip_length` calls
  it only mid-test. So the Major is fixed *mechanically* but enforced only by
  convention, at precisely the seam M3 must write — the same shape as C16,
  which both reviewers rated Minor and the coordinator deferred.
- **Proposed fix.** Make `arm()` (and `play()`) raise when `self.attempt is
  None`, and/or refuse to arm a candidate whose `trial_id` does not match the
  current attempt; alternatively fold the clear into `arm()` so the scoping
  cannot be skipped.
- **Verification.** A test that `arm()` without a preceding `begin_attempt()`
  raises `AudioFault`, and that a candidate whose `trial_id` disagrees with the
  current attempt is refused.

### M1-audio-001-R03-F08 — Minor — `PauseTimer.too_late()` is unreachable through the segmenter path it is justified by, and its only test uses a profile `validate_detector_profile` would reject

- **Location:** `timing.py:988-1013` (`discovery_lateness`, `too_late`),
  `timing.py:886-903` (the offset event's `confirmed_time`),
  `tests/test_timing.py:644-677` (`StaleDeadlineTest`), `resolution.md` C6.
- **Requirement:** `EGM_WORKFLOW.md` §8 "`FIX` (change + evidence +
  verification)"; `AGENTS.md` "Test observable behavior and failure modes, not
  merely duplicated implementation logic".
- **Evidence (static).** In `SpeechSegmenter.push`, an offset event carries
  `event_time = _frame_end(last)` and `confirmed_time = _frame_end(idx)` where
  `idx − last == hangover_frames` at emission. So
  `confirmed_time − event_time == hangover_frames × frame_s` always, and
  `discovery_lateness = max(0, (event_time + hangover) − (event_time +
  threshold)) = max(0, hangover − threshold)`, which is **identically zero**
  for any profile `validate_detector_profile` accepts (it requires
  `hangover + decision_budget < shortest threshold`). After C6's origin fix —
  which moved the origin forward onto the last band frame — the band dwell no
  longer inflates this difference, so `too_late()` can never fire on the
  event-driven path. `StaleDeadlineTest` reaches it only by calling
  `note_offset(1.0, 1.8)` by hand, with `hangover_ms=600.0`, a profile that
  `validate_detector_profile(profile, [0.5, …])` would itself reject. **Both
  mechanisms do carry weight** — the guard has a genuinely reachable trigger I
  can see (frame times come from the capture timeline, so a recorder gap
  between the last speech frame and the hangover-confirming frame makes
  `confirmed_time − event_time` exceed the hangover; a real Silero VAD with
  variable buffering will be another) — but `resolution.md`'s stated rationale
  for it, "an unbounded band dwell would then produce a deadline already long
  past", is the one thing the origin fix *removed*, and the reachable triggers
  are untested.
- **Proposed fix.** Restate C6's rationale: the origin fix closes the band-dwell
  path, and the staleness guard covers a *different* class (timeline gaps and
  real detector latency). Add a test that drives the segmenter through a
  `CaptureTimeline` containing a gap and asserts `too_late()` becomes true, and
  change `StaleDeadlineTest`'s profile to one the validator accepts (or assert
  explicitly that it is deliberately an invalid-profile case).
- **Verification.** The new gap-driven test fails if `too_late()` is reverted to
  always-false; `validate_detector_profile` is applied to every profile used in
  the test suite.

### M1-audio-001-R03-F09 — Minor — the "which reading of speech ended" gate is recorded as an analysis choice, but the band-inclusive origin now sets the live eligibility deadline

- **Location:** `timing.py:873-884` (`push`, the in-speech branch that moves
  `_last_speech_frame` on a band frame), `timing.py:947-957`
  (`PauseTimer.note_event` → `note_offset(event.event_time, …)`),
  `resolution.md` "Open research decisions this round surfaced" row 1,
  `validation/audio_spike.md` "Limitations to carry forward".
- **Requirement:** `goal.md` §3 "Dialogue trials: two each at provisional
  silence thresholds of 0.5, 1.0 and 2.0 seconds"; §14 "Recall cap origin,
  completion procedure, event precedence, rearming … **Research director**";
  `AGENTS.md` "Preserve the research contract and unresolved research-owned
  gates"; packet question 4.
- **Evidence.** The answer to the packet's question is **yes, it is a research
  decision and not only an engineering one**, and the record half-says so.
  `PauseTimer` consumes `event.event_time`, which is now the end of the last
  *band* frame, so the deadline — and therefore the silence the participant
  actually receives before the prompt — moves later by `band_dwell_s` relative
  to round 1. Both readings are recorded per event (`band_frames`,
  `band_dwell_s`, `last_strong_frame`, `strong_event_time`), which is the right
  thing to have done. But `resolution.md` frames the gate as "Which definition
  **the analysis** uses", and `audio_spike.md` says "The deadline is computed
  from the first" almost in passing. The choice governs the manipulation during
  collection, not just the analysis afterwards, and the engineering default is
  currently unreachable without editing `timing.py`.
- **Proposed fix.** Restate the open-decision row as governing *both* the live
  deadline origin and the analysis reading, and make the origin a configured
  field (e.g. `PauseTimer(..., origin="run_end" | "last_strong")` reading the
  matching field off `SpeechEvent`) so the research decision can be applied as
  configuration rather than as a code change. Same for the 50 ms
  `DEFAULT_LATENESS_BUDGET_S`, which is already correctly listed as an
  engineering default.
- **Verification.** A test that both origins produce the deadlines they should
  for the same probability sequence, and that the configured origin is recorded
  in the trial's detector-profile record.

### M1-audio-001-R03-F10 — Minor — the machine-readable onset record is weaker than the prose: `uncertainty_s` does not cover the disclosed latency disagreement, the remote-session caveat is missing from the primary evidence record, and the tool re-introduces "unknown term treated as zero"

- **Location:** `audio_io.py:1420-1430` (`uncertainty_s=self.blocksize /
  self.samplerate`); `validation/audio_spike.md` Finding 3 item 2 and
  "Limitations to carry forward"; `decisions.md` D5 "Not yet established";
  `tools/check_audio.py:428-430` and `:251`.
- **Requirement:** `goal.md` §7 "Audible onset measurement or calibrated
  estimate, **its method and uncertainty**"; "Report all observations and
  maxima"; `EGM_WORKFLOW.md` §6 "Evidence files with … limitations";
  `AGENTS.md` "Do not turn … timer timestamps into acoustic measurements".
- **Evidence.** (a) Every onset `Estimate` gets `uncertainty_s = 480/48000 =
  10 ms`. The same evidence set discloses that the two available latency
  reports for WASAPI disagree by 12 ms — `stream.latency` 22.0 ms against a
  per-block DAC offset of 10.00 ms (`audio_spike.md` Finding 3 item 2,
  `decisions.md` D5) — so the recorded half-width is smaller than the known
  disagreement between the only two estimators of the quantity. The prose is
  honest; the field M3 will read is not. (The headline conclusion is unaffected:
  30.32 ms p95 clears the 100 ms candidate target either way, and the default
  MME device fails it either way.) (b) `decisions.md` D5 and
  `DEVELOPMENT_STATUS.md` disclose that **the device measurements were taken
  over a TeamViewer session, which can redirect or claim audio endpoints**, and
  say they must be repeated at the physical machine. That caveat appears in
  neither `validation/audio_spike.md` (the primary evidence record, including
  its "Limitations to carry forward") nor the packet's limitations column, where
  the survey row reads only "1 s per device, silence only, no load". Since a
  remote-desktop audio stack can change which endpoint is default and what
  latency it reports, that is the largest single limitation on Findings 2 and 3
  and it is missing from the record that states them. (c)
  `commit_distribution` writes `(cand.onset_delay_s or 0.0)`,
  `(cand.device_offset_s or 0.0)` and `(cand.clip_leading_silence_s or 0.0)`
  — the exact "a missing term silently treated as zero" pattern C1 removed from
  `PromptCandidate.onset_delay_s`. It is currently unreachable because
  `has_audible_onset` is checked first, which is why I rate this Minor, but it
  is one probe change away from publishing a zero for an unknown.
- **Proposed fix.** Set the onset `uncertainty_s` to at least
  `max(blocksize/samplerate, |reported stream latency − per-block DAC offset|)`
  and carry both latency readings in the committed record; copy the
  remote-session caveat into `audio_spike.md`'s Findings 2 and 3 and its
  limitations list and into the packet's limitation column; replace `or 0.0`
  with an explicit `None`-skip that drops the trial from the distribution and
  reports the count dropped.
- **Verification.** A test that an onset `Estimate`'s `uncertainty_s` is never
  smaller than the recorded disagreement between the two latency sources; a
  tool run in which a probe without a detectable onset reports a skipped-trial
  count rather than zeros.

## Per-finding fix-verification status

Judged by tracing each fix to its code and its named test, and by asking
whether that test would fail on revert. "Would fail on revert" is static
reasoning — I was not permitted to edit code to confirm it.

| ID | Mechanism claimed in `resolution.md` | Verified in code | Named test fails on revert? | Status |
|---|---|---|---|---|
| **C1** | `_leading_silence_s → None`; three components kept separate and summed | Yes — `audio_io.py:277-294` returns `None`; `_maybe_commit` (`:1415-1432`) records `commit_delay`, `device_offset_s`, `clip_leading_silence_s` separately; `PromptCandidate.onset_delay_s` returns `None` when `audible_onset` is `None`. I checked the arithmetic: `onset_delay = (first_frame_time + lead) − deadline = commit_delay + device_offset + lead`, and the committed JSON is internally consistent (7.00 + 10.00 + 10.00 = 27.00 median, p95 30.32). | **Yes.** Reverting `_leading_silence_s` to return the clip duration makes `assertIsNone(cand.audible_onset)` and `assertIsNone(cand.onset_delay_s)` fail in both `test_a_silent_clip_yields_no_onset_estimate_rather_than_an_inflated_one` and `test_the_onset_estimate_is_not_the_commit_delay_plus_a_clip_length`; reverting the component split fails `test_components_are_recorded_separately_and_sum_to_the_onset`. | **VERIFIED FIXED** |
| **C2** | `note_block` only after a successful enqueue; `note_not_persisted` with a `COUNTED` count; `note_persisted` from the writer; `finalize()` reconciliation | Yes — `audio_io.py:884-900` records the drop *before* any counting and returns; `timing.py:414-450`; `finalize` shortfall at `:983-991`. The reconciliation is correct for its case (lost queued blocks are necessarily the file's tail, so earlier indices still map truly). Residual: the shortfall gap's `file_sample` points past EOF — **F03(b)**. | **Yes.** Reverting to count-then-enqueue makes `frames_written == frames_persisted` fail in `test_a_backlog_drop_is_a_counted_gap_and_not_continuous`, and removing the `finalize` reconciliation fails the `writer_shortfall` assertions in `test_frames_after_a_writer_failure_are_recorded_as_lost`. | **VERIFIED FIXED** (one reporting detail in F03) |
| **C3** | `anchor` clamps and returns instead of raising; the whole callback body is guarded; mid-stream method change is a fault; `check_liveness` | Yes — `timing.py:149-181`; `audio_io.py:846-860` (`_callback` is a thin `try/except` wrapper that converts anything into `capture_callback_error`); `:867-876`; `:925-943`. I traced the `except` path for re-raise risk: `_fault` only appends, logs with a non-reserved key, and wraps `_on_fault` in its own `try`. | **Yes.** `test_a_backwards_device_time_does_not_kill_the_stream` asserts all 11 blocks were delivered — a raising `anchor` would stop at 6; `test_a_host_api_changing_its_time_source_is_a_fault` and `test_a_stalled_capture_callback_is_faulted_while_the_trial_runs` each fail without their respective additions. | **VERIFIED FIXED** |
| **C4** | `begin_attempt(attempt)` scopes and clears the slot; refuses to start with a prompt armed | Yes — `audio_io.py:1198-1219`. Mechanism correct and `_playing_candidate` is genuinely per-playback (`stop()` at `:1322-1331` no longer reports an old commitment). Residual: nothing *requires* `begin_attempt` — **F07**. | **Yes.** Reverting the `_committed = None` clear makes `assertIsNone(self.player.committed_candidate)` fail and turns the outcome into `too_late_committed` in `test_a_later_attempt_does_not_inherit_an_earlier_commitment`. | **VERIFIED FIXED** (opt-in; see F07) |
| **C5** | Four-way `CancelOutcome`; `_vetoed` remembered; `allowance_consumed` only for a commitment | Yes — `audio_io.py:1029-1072`, `:1264-1300`, `:1397-1409`. `allowance_consumed` is `outcome == CANCEL_TOO_LATE` only, and `_maybe_commit`'s veto path sets `_vetoed` and logs `prompt_vetoed_at_commit`. Commit and cancel are both under the same `RLock` held across the callback, so the race is genuinely serialised. | **Yes.** Removing `_vetoed` turns the outcome into `nothing_armed` and fails `assertEqual(outcome.outcome, CANCEL_ALREADY_CANCELLED)` in `test_a_vetoed_prompt_does_not_consume_the_allowance`. (Note: the *allowance* stays intact even without `_vetoed`; what `_vetoed` adds is correct reporting, which is what the test pins.) | **VERIFIED FIXED** |
| **C6** | Band frames move the silence origin; both readings recorded; plus `discovery_lateness`/`too_late`/`eligible` | Origin: yes — `timing.py:873-884`, with `band_frames`, `band_dwell_s`, `last_strong_frame`, `strong_event_time` on the event. Staleness guard: implemented correctly but, after the origin fix, unreachable via the segmenter path its rationale cites — **F08**; and the origin change is a research decision scoped as analysis-only — **F09**. | Origin: **yes** — reverting it makes `off.frame_index == 23` and `band_frames == 20` fail in `test_band_frames_move_the_offset_origin`. Guard: `StaleDeadlineTest` would fail on revert, but it drives `note_offset()` directly with a hand-made confirmed time under a profile `validate_detector_profile` rejects, so it does not demonstrate a reachable path. | **VERIFIED FIXED** (origin) / **PARTIALLY FIXED** (guard: correct but unexercised on any reachable path) |
| **C7** | Gap detection and the sample/time mapping moved onto PortAudio's block clock, 2 ms device / 80 ms fallback tolerance, minimum-biased offset, interpolated anchors | The clock-domain change is the right diagnosis and the four named cases hold: constant 30 ms lateness yields no gap, 1000 ppm drift over three minutes yields no gap and `drift_ppm ≈ 1000`, one omitted block is exactly one gap at the right sample, and heavy lateness plus one real loss is still exactly one gap. But the mechanism introduces or leaves three defects: fabricated gaps from stale/unvalidated device-time deltas (**F01**, reachable on this PC's only input devices), a non-clamped offset that can step the mapping's time labels backwards and whose rationale/test model do not match the real backend (**F02**), and `continuous: true` on a basis that cannot see a lost block (**F03**). The 80 ms fallback is honest *in the code comment* and not in the field a consumer reads. | Yes for the four new gap tests individually. | **PARTIALLY FIXED** |
| **C8** | Exact pins | Yes — `requirements.txt`: `numpy==2.3.5`, `sounddevice==0.5.5`, PortAudio build recorded per measurement, with an explicit "Do not relax a pin to a range" note and `onnxruntime`/`soundfile` correctly listed as not-yet-required. | No regression test exists, and none is warranted for a requirements file; the change is directly inspectable. | **VERIFIED FIXED** |

### Minors (spot-checked)

C9 lock around `seq` + append — **VERIFIED FIXED** (`timing.py:1219-1226`,
`LedgerConcurrencyTest`). C10 one `DEFAULT_PROFILE`, asserted equal to the
dataclass defaults — **VERIFIED FIXED** (`DefaultProfileTest`; the documented
profile in `audio_spike.md` matches 32/96/150/0.5/0.35). C11 failed `start()`
tears down and unlinks the partial; zero frames is a `recording_empty` fault
and not `continuous` — **VERIFIED FIXED**
(`test_a_device_that_never_opens_publishes_nothing`,
`test_an_empty_recording_is_not_continuous`). C13 verdict ladder —
**VERIFIED FIXED**, reproduced by me: `8 PASS, 2 NOT_RUN, verdict INCOMPLETE`.
C14 — **PARTIALLY FIXED**, see **F06**. C15 `default_capture_available` vs
`capture_possible` — **VERIFIED FIXED** in `inventory()` and reproduced in my
tool run; note that `duplex_check` still gates on `capture_available`
(`tools/check_audio.py:512`) and takes no device argument, so the tool cannot
exercise a *pinned* non-default input — which is why the "Capture on this PC"
row is partly a tool limitation, not purely the "Hardware gap" the packet
labels it. C17 — **PARTIALLY FIXED**, see **F05**.

### Invariants that held in round 1 — do they still hold?

| Invariant | Verdict |
|---|---|
| No output before the eligibility deadline, and none before participant speech | **Holds.** `_maybe_commit` returns while `timing.entry_time < cand.deadline` (`audio_io.py:1390-1392`); the clip is only placed after that, and the audible instant is `first_frame_time (≥ entry) + lead`. `PauseTimer.arm` happens only on an onset, and `note_offset` returns early when not armed. Tests: `test_nothing_is_audible_before_the_deadline`, `test_no_deadline_before_participant_speech`, plus `no_prompt_before_deadline` PASS in my own tool run. |
| The configured interval added exactly once, to the speech offset, never to the confirmation time | **Holds.** `deadline = silence_since + threshold_s` with `silence_since = event.event_time`; `known_at()` takes a `max`, never a sum; `_maybe_commit` compares against `cand.deadline` without adding anything. Reproduced in my tool run for all three thresholds (`0.320 + 0.5/1.0/2.0`). |
| Cancellation before commitment removes the clip; commitment consumes the allowance and is reported as such | **Holds**, and is now better reported (C5). |
| The recording keeps exactly the frames the device delivered; sample indices map back to controller time across a gap | **Holds for the file bytes** (`test_recorded_samples_are_the_samples_the_device_delivered`, and `frames_written == frames_persisted` after a drop). **Weakened for the mapping** by F01 (fabricated gaps) and F02 (time labels can step backwards), and the `writer_shortfall` gap's index is out of range (F03b). |
| No code path can produce an `Estimate` with `method="measured"` | **Holds.** `MEASURED` appears in `timing.py` only as the constant, in `_METHODS` and in `is_measurement`; the sole `Estimate(...)` construction in `audio_io.py` passes `ESTIMATED`. No production call site passes `MEASURED`. |
| `os.replace` publication stays atomic; `start()` refuses to record over an existing `.partial` | **Holds.** `audio_io.py:791-795` raises on an existing `.partial`; publication is a single `os.replace`. Durability (not atomicity) is still unestablished and now undispositioned — F06. |

## Open research decisions / evidence gaps

Separate from the code defects above. Per `EGM_WORKFLOW.md` §8 a
research-owned gate may be deferred without blocking synthetic development, but
its affected release remains unpassed. **No participant-use approval and no
universal safety guarantee is available from this review**, and I cannot mark
any research approval complete on the research team's behalf.

1. **Which reading of "where speech ended" the protocol uses.** Owner: research
   director / analyst, before the timing tolerance is frozen. Gate: the M1/M6
   timing-tolerance freeze **and** the manipulation itself — not analysis only
   (see F09).
2. **The lateness budget** beyond which a deadline is a `deadline_already_past`
   deviation. Owner: research director with the detector profile. Currently an
   engineering default of 50 ms. Gate: protocol freeze.
3. **Whether a trial containing a counted recorder-side gap is analysable.**
   Owner: research director; `goal.md` §6 leaves it open. The code flags rather
   than decides, which is right. F01/F03 matter here: the flag must not fire on
   fabricated gaps, or the rule will be applied to good trials.
4. **Detector profile, 100 ms candidate target, recall-cap origin** — all
   proposals (`decisions.md` D1, D4, D5; `goal.md` §14). Gate: material/
   protocol freeze.
5. **Microphone, placement and calibration.** Owner: developer + research
   director, M1/M6. **BLOCKED on hardware:** this PC has no default input
   device; the only two input-capable endpoints are Bluetooth hands-free
   headsets on WDM-KS, which are unsuitable as a research microphone. Every
   microphone-side claim in this checkpoint rests on the fake backend. Note
   that this is also the host API most affected by F01/F03.
6. **All onset figures are `estimated`, never measured.** Acoustic onset,
   last-speech-to-audible-response, detector boundary error on real speech,
   echo/leakage, completion suppression at 0.5 s, drift over a real session and
   behaviour under load are all `NOT_RUN` and are honestly recorded as such.
   Additionally, every device figure in this checkpoint was taken over a
   TeamViewer session (disclosed in `decisions.md` D5 and
   `DEVELOPMENT_STATUS.md`, missing from `audio_spike.md` and the packet — F10)
   and must be repeated at the physical machine.
7. **M1 as a milestone is not complete.** The avatar clock-adapter
   demonstration required by `goal.md` §7 and §12 does not exist; it is scoped
   as `M1-avatar-002`. Correctly recorded as an evidence gap, not a defect of
   this checkpoint. `PlaybackPosition`, `interpolate` and
   `OutputPlayer.position()` are the controller half only.

### The two deferrals

- **C12** (`.partial` reports zero frames after an abrupt kill) — **legitimate
  deferral.** Owner named (developer, M3), reason given (the WAV header is
  written on close), the chosen fix is specified (raw PCM plus a sidecar,
  converted on finalisation) and the affected gate is named (crash-recovery
  evidence for M3/M6, which remains unpassed). It does **not** block the M3
  controller: the attempt is still *detectable* as incomplete, which is what
  `goal.md` §10 requires at this stage, and `start()` refuses to record over a
  `.partial`. The only problem is that R01-F12's second half (durability /
  `fsync`) was dropped rather than deferred with it — F06.
- **C16** (nothing binds `PromptCandidate.deadline` to `PauseTimer`) —
  **legitimate deferral.** Owner named (developer, M3), gate named (M3
  controller review), and the originating reviewer stated explicitly that they
  found no path *in this checkpoint* by which the interval is added twice,
  which I independently confirmed. It does not block M3 work; it **is** M3
  work, and it should be built as R01-F10 proposed (a `PauseTimer` factory that
  stamps `deadline`, `silence_since` and `threshold_s` together, plus an
  assertion in `arm()`), because `known_at()` sits next to `deadline` as an
  inviting wrong value. F07 is the same shape and should be fixed in the same
  change.

## Verdict

**NEEDS_FIXES**

**Scope.** This verdict covers the 15 manifest files at the digests listed in
`packet-round-2.md` (all re-verified unchanged before and after my checks),
against `goal.md` v0.3 §§3–7, 10, 13, 14, through the fix-verification stage
and the dispatched lenses. It answers only the packet's question: whether the
eight consolidated round-1 Majors are fixed, whether the fixes introduced new
defects, and whether the evidence records state what was executed.

**Why not a pass.** Seven of the eight Majors are verified fixed by the
mechanism `resolution.md` claims, with regression tests that I judge would
genuinely fail on revert — C1's correction in particular is thorough, the
arithmetic in the re-measured JSON is internally consistent, and the retraction
is recorded rather than quietly swapped. C6's origin fix is correct and
important. But **C7 is only partially fixed**: moving onto the device clock was
the right diagnosis, and it demonstrably fixed the jitter-versus-loss problem,
yet the new mechanism fabricates gaps whenever a host API stops and resumes
reporting block times (F01) — which the project's own survey evidence shows
WDM-KS doing, and WDM-KS is the only host API with an input device on this PC —
can step the sample→time mapping's labels backwards (F02), and reports
`continuous: true` on a basis the module itself says cannot see a lost 10 ms
block (F03). Those three sit on exactly the contracts M3's recorder and
controller would consume. Separately, the snapshot is not what the packet
describes and the packet's own regression figure does not reproduce — the named
command returns 139 tests, not 113, because an undeclared `preflight.py` and
`tests/test_preflight.py` that import this layer landed after the freeze (F04).
Under `EGM_WORKFLOW.md` §8 a checkpoint passes only when its required executed
checks pass, no unresolved Major remains in scope, and fresh review covers the
current snapshot; two of those three are not met.

**What this verdict does not cover.** Participant readiness; acoustic
validation of anything; approval of any research-owned decision (I have none to
give); the completeness of M1 as a milestone (the avatar clock-adapter
checkpoint does not exist); any hardware behaviour, since I ran no device check;
and `preflight.py`, `tests/test_preflight.py` and `config/experiment.json`,
which I excluded as outside the declared manifest. A fake-backend pass is not
hardware validation, 40 prompts on an idle machine over a remote-desktop
session is not a distribution on the final configuration, and nothing here
establishes an acoustic onset.

**Coverage limits of this review.** All dynamic claims beyond my two permitted
command runs are static reasoning, stated as such; where I describe a test that
would fail under a variation, I was not permitted to edit code to confirm it,
and the arithmetic is given so the author can. I did not inspect the renderer,
the baseline `08_avisspeech`, or any M2–M7 scope.
