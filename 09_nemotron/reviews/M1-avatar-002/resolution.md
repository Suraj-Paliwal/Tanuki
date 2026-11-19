# M1-avatar-002 — R05 findings, dispositions and fixes

Review [R05](goldfish-combined-R05-round-1.md) covered two scopes under one
[packet](packet.md) and returned two verdicts, both **NEEDS_FIXES**:

- **Scope A** — fix verification of `M1-audio-001` round 3. Four of five
  round-3 findings verified fixed; one new Major (F01) and two Minors (F02,
  F03).
- **Scope B** — first review of the avatar clock adapter and renderer
  snapshot. Four Majors (F04-F07) and six Minors (F08-F13).

R05 confirmed all 32 packet digests before and after its checks and reproduced
every executed result in the packet. Its report is preserved unedited; this
file records only what was done about it.

**Scope A and the bounded loop.** `M1-audio-001` had used its three
fix/review iterations. R05 judged F01 neither a reversal of an accepted
decision nor non-convergence (8 → 4 → 2 → 1 Major) and left the choice to the
user. On 2026-11-20 the user chose **one more fix cycle**, verified in the same
next review as the scope-B fixes, over carrying F01 into M3.

No severity was downgraded and nothing was closed by moving it to a backlog.

## Findings and dispositions

| ID | Scope | Severity | Summary | Disposition |
|---|---|---|---|---|
| F01 | A | Major | Probe loops: the finish wait shared the commit wait's bound, so a commit in the last clip-length before the limit left a clip playing and the next `arm()` raised; a commit in the timeout-cancel race was counted as a timeout; no test drove either loop | FIX |
| F02 | A | Minor | `preflight.py`'s empty-onset path raised `StatisticsError` one check before its guard; the branch is unreachable with the `tone_clip` probe | FIX |
| F03 | A | Minor | D8's test count stale again (153 vs 161) | FIX |
| F04 | B | Major | Staleness clock did not start until the first snapshot; a transport that died before it left the mouth parked on a speaking pose, no fault | FIX |
| F05 | B | Major | Between `play()` and the first callback `position()` published "not playing", which the adapter read as a stop for the whole clip | FIX (both sides) |
| F06 | B | Major | Clip-end flip came one output latency before the audible end; nothing published the audible end, so M3's "instruction audible end" would be early on every trial | FIX |
| F07 | B | Major | `pre_roll_s` had no test that would fail on revert; the JS cross-check read a committed generated fixture nothing kept in sync | FIX |
| F08 | B | Minor | Stops not latched: a same-generation `playing` snapshot un-stopped the adapter; `onStop` could fire twice | FIX |
| F09 | B | Minor | No arm/reset, so clip A's position leaked into clip B; a snapshot without `generation` passed the supersede check | FIX |
| F10 | B | Minor | Cross-language test passed silently when the fixture was missing; `?? stops` made the stop assertion vacuous | FIX |
| F11 | B | Minor | Provenance was a list, not a closure: an extra file under untracked `model/`/`vendor/` was invisible to Git and the verifier; `app.js` unnamed | FIX |
| F12 | B | Minor | (a) clip-start transport bias is ≈2L, not L; (b) `pre_roll_s` attributed to the wrong estimator; (c) `interpolate` called a mirror but lacked the monotonic guard | FIX |
| F13 | — | Minor | Packet's "verbatim" `git status --porcelain` omitted the untracked review directory | FIX in the next packet |

## What was changed

### Scope A

- **F01.** The probe loop now exists once, as `audio_io.run_commit_probe`,
  shared by `preflight.SessionPreflight.measure_output` and
  `tools/check_audio.py`, so the two copies cannot drift apart again. It
  (a) gives the finish wait its own bound, `clip.duration + slack` from the
  moment the commit is seen; (b) inspects the timeout cancellation and, on
  `too_late_committed`, reports `PROBE_COMMITTED_LATE`, waits the clip out and
  counts the trial as committed (shown as `committed_late` in the
  `commit_delay` result) rather than as a timeout; (c) returns `PROBE_STUCK`
  when a committed clip does not finish within its bound. Both callers turn
  `PROBE_STUCK`, and any `AudioFault` from a probe, into a blocking FAIL naming
  the trial index, so neither can end in a traceback.
- **F02.** The reporting half of `measure_output` is now
  `SessionPreflight._report_probes`, and every statistic in it is guarded by
  the emptiness of the list it reads. With no onset estimate it reports both
  `device_offset` and `onset_delay_target` as `NOT_RUN` with the skipped count.
  The skip branch in the loop stays, commented as defence in depth for a
  future non-`tone_clip` probe and as unreachable today.
- **F03.** D8 no longer carries a number: "Every Python test that touches an
  audio stream uses it", with a note on why.

### Scope B

- **F04, F08, F09 — the adapter's lifecycle.** `PlaybackClockAdapter.arm()` is
  required immediately before every `playTrack`, and construction counts as
  an arm. It clears the previous clip's snapshot and position, starts the
  staleness clock, and sets the oldest generation it will accept (the
  `generation` passed in, or one past the last clip it drove). With no
  snapshot, `fileTime()` faults `stale_clock` and stops once `staleAfterMs`
  has passed since `arm()`; `age()` and `isStale()` measure from `arm()` in
  that state. Every stop is latched until the next `arm()`: while stopped,
  snapshots are counted as `ignored` and change nothing. A snapshot without a
  finite numeric `generation` is malformed. A newer generation that is
  *playing* while an older clip is driven stops with `superseded`, since the
  renderer still holds the old track. Previously that case silently restarted
  the position at zero under the old track.
- **F05.** Controller side: `OutputPlayer.position()` publishes the window
  between `play()` and the first callback as playing, `file_time` 0,
  `duration` of the clip, `pre_roll_s` = the stream's reported latency (the
  only estimate available before a callback), and no `ended_reason`. Adapter
  side, as defence in depth: a not-playing snapshot that arrives before the
  armed clip has been seen playing is ignored rather than read as a stop. The
  staleness clock still runs from `arm()`, so a controller that never starts
  the clip is still a fault.
- **F06.** `OutputPlayer` records the audible end of the last block when the
  clip is fully written. `position()` keeps reporting `playing` through that
  tail, with `file_time = duration − remaining`, and publishes a new
  `PlaybackPosition.audible_end_s` (seconds from `controller_time` until the
  clip is fully audible) on every playing snapshot. `OutputPlayer.audible_end`
  gives the controller-time instant M3 needs for `recall_cap_origin:
  instruction_audible_end`. It equals `finished[-1]["end_block_time"]`, which
  a test asserts. An explicit `stop()` still reports stopped at once and
  clears the audible end. R05's alternative, a post-roll field plus a deferred
  stop in the adapter, was not taken: it would leave every other consumer of
  the playing flag with the early end. Recorded in D10.
- **F07.** (i) `test_pre_roll_is_published_before_audio_and_zero_mid_clip`
  guards the Python half of `pre_roll_s`; (ii)
  `test_position_holds_through_the_pre_roll_then_advances` guards
  `interpolate`; (iii)
  `test_the_committed_position_trace_matches_the_current_controller`
  regenerates the trace through `make_position_trace.build_trace()` and
  `render()` and fails if the committed fixture differs. The trace generator
  now samples frame 0 before any callback (F05's window) and asserts through
  the audible tail (F06's window), so both ends of the clip are inside the
  cross-check. Regenerated: 53 frames, 12 delivered, 47 asserted.
- **F10.** The JS cross-language test lets a missing fixture throw (fail, not
  skip), asserts `expect_stops` is a non-empty array, and asserts the number
  of checked positions equals the fixture's `asserted_frames`.
- **F11.** `tools/verify_snapshot.py` walks `model/` and `vendor/` and reports
  any unlisted file as `UNEXPECTED`, exiting 1. `tests/test_snapshot.py`
  covers it; a scratch file dropped into `vendor/three/addons/` was reported
  and the tool exited 1. `asset-provenance.json` names
  `../08_avisspeech/src/app.js` as the closure root and says why it is not
  copied. `validation/avatar_clock.md` says the same.
- **F12.** (a) The ≈2L pre-roll bias is stated in D9, in the adapter's header
  and `transportBiasNote`, and in `validation/avatar_clock.md`. (b) The
  validation record now attributes mid-clip `pre_roll_s` to the per-block DAC
  time, and the pre-start value to the reported latency. (c) `interpolate`
  takes an optional `floor` (the previous answer) and never returns below it,
  so the monotonic guard is available on the Python side. Its docstring now
  names the two remaining intended differences: the time base, and raising
  where the adapter faults. Test:
  `test_a_late_snapshot_does_not_move_the_position_backwards`.
- **F13.** The next packet pastes `git status --porcelain` from the repository
  root complete and unfiltered, and states that status, index and README
  files may change during the review window, with the digests as the
  authority.

Also changed, to keep the bench page consistent with the new contract:
`tools/avatar_clock_check.html` calls `arm()` before each `playTrack`, and its
stale-clock button now also checks the F04 case (no first snapshot). It
remains **not opened**.

## Revert checks

Each fix was reverted in a scratch copy of the tree, and the suite was run
against the result. Every revert failed:

| Revert | Result |
|---|---|
| F01a: finish wait shares the commit limit (`idle_limit = limit`) | 3 failures |
| F01 / R04-F01: no cancellation on timeout | 3 failures |
| F01b: a `too_late_committed` cancel counted as a timeout | 1 failure |
| `preflight.py` as reviewed (HEAD) | 4 errors; the two loop tests raise exactly R05-F01's `AudioFault: cannot arm a prompt while output is playing` |
| `src/clock-adapter.js` as reviewed (HEAD) | 12 JS failures |
| F05: pending start published as idle | 2 failures (incl. the fixture guard) |
| F06: no audible tail | 2 failures |
| F07a: `pre_roll_s` dropped from `OutputPlayer.position` | 2 failures |
| F07b: `interpolate` ignores `pre_roll_s` | 1 failure |
| F10: fixture deleted | 1 JS failure |

## Checks after the fixes

Environment as in the packet: Windows 11 Education 10.0.26300 x64,
Python 3.13.9, Node v24.14.0, from `09_nemotron`, 2026-11-20.

| Command | Result |
|---|---|
| `python -m unittest discover -s tests -p "test_*.py"` | **180 OK** (77 timing, 65 audio I/O, 35 preflight, 3 snapshot) |
| `node --test tests/test_clock_adapter.mjs` | **30 pass, 0 fail** |
| `python tools/check_audio.py` | 8 PASS, 2 NOT_RUN, verdict `INCOMPLETE`, exit 0 (no device opened) |
| `python tools/verify_snapshot.py --baseline` | 23/23, PASS, exit 0 |
| `python tools/make_position_trace.py` | regenerates the committed fixture byte-for-byte (the fixture-guard test passes) |

**NOT_RUN, and why:**

- `tools/check_audio.py --commit-trials N` on real hardware. It now goes
  through the shared helper, which the tests cover, but the tool's own
  wrapper around it has not been executed on a device after this change.
  That run plays a faint tone through the speakers, and the PC is still
  reached over TeamViewer.
- `tools/avatar_clock_check.html` — still not opened.
- Everything R05 listed as outside both verdicts: acoustic or visual
  synchronisation, the real transport, `playTrack` under a real frame loop,
  microphone capture (BLOCKED).

## Still deferred, unchanged

**C12**, **C16** and **C18** remain deferred to M3 with the developer as owner,
and the M3/M6 crash-recovery gate stays unpassed. New for M3/M4's transport
design, from R05's evidence-gap list: nothing binds `staleAfterMs` (250 ms) to
a required snapshot publication cadence.

## Verdict status

Not passed. Both scopes need fresh fix-verification review of the snapshot
these fixes created. Neither `M1-audio-001` nor `M1-avatar-002` is marked
complete here.
