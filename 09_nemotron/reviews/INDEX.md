# Development review index

The earlier design review is recorded in
[ELEPHANT_GOLDFISH_REVIEW.md](../ELEPHANT_GOLDFISH_REVIEW.md); it reviewed the
specification, not code or runtime behaviour. Workflow-document validation is
recorded separately in [WORKFLOW_VALIDATION.md](WORKFLOW_VALIDATION.md).

Create new checkpoint directories from
[CHECKPOINT_TEMPLATE.md](CHECKPOINT_TEMPLATE.md). Add rows only when work and
evidence exist. Preserve historical results; link superseding snapshots rather
than overwriting history.

| Checkpoint | Round | Goal version / snapshot | Packet and reports | Scope verdict | Unresolved IDs / gates |
|---|---|---|---|---|---|
| `M1-audio-001` — timing core, native capture/playback, device spike | 1 | goal v0.3 §4-7, §10, §12-13; base commit `eeb0f0e`, all reviewed files untracked, digests in the packet | [packet](M1-audio-001/packet.md); [R01 focused](M1-audio-001/goldfish-focused-R01-round-1.md); [R02 critic](M1-audio-001/goldfish-critic-R02-round-1.md) | **NEEDS_FIXES** (both reviewers) | 8 consolidated Majors + 9 Minors; see [resolution](M1-audio-001/resolution.md) |
| `M1-audio-001` — same scope after fixes | 2 | goal v0.3, same sections; base commit `eeb0f0e`, nothing committed at packet time, digests in the round-2 packet | [fix-verification packet](M1-audio-001/packet-round-2.md); [R03 fix-verification](M1-audio-001/goldfish-fix-verification-R03-round-2.md) | **NEEDS_FIXES** — 7/8 round-1 Majors verified fixed; C7 partially; 4 new Majors on the device-clock mechanism and snapshot drift | see [resolution](M1-audio-001/resolution.md) round 2 |
| `M1-audio-001` — complete tree incl. session preflight | 3 | goal v0.3; base commit `0198546`, dirty files and digests in the round-3 packet | [round-3 packet](M1-audio-001/packet-round-3.md); [R04 fix-verification](M1-audio-001/goldfish-fix-verification-R04-round-3.md) | **NEEDS_FIXES** — all 10 round-2 findings verified fixed (F02 partially: no test isolated the clamp); 2 new Majors (probe-timeout crash, clamp coverage) + 3 Minors | all 5 fixed; see [resolution](M1-audio-001/resolution.md) round 3. Final verification of the post-round-3 snapshot is outstanding; bounded loop at its 3-iteration cap |

| `M1-avatar-002` — renderer snapshot + browser clock adapter, **plus** the `M1-audio-001` round-3 fixes | 1 (combined) | goal v0.3 §4-7, §9, §10, §12-13; base commit `ae435bf`, digests in the packet | [combined packet](M1-avatar-002/packet.md); [R05 combined](M1-avatar-002/goldfish-combined-R05-round-1.md) | **Scope A NEEDS_FIXES** (1 Major: probe loops still crash via `arm()`, untested; 2 Minors). **Scope B NEEDS_FIXES** (4 Majors: no stale fault before first snapshot, starting clip read as stop, clip end one output latency early, `pre_roll_s` unguarded; 6 Minors) | all 13 fixed, see [resolution](M1-avatar-002/resolution.md); user chose one more fix cycle for scope A; C12, C16, C18 deferred to M3 |
| `M1-avatar-002` + `M1-audio-001` — fix verification of all R05 findings | 2 | goal v0.3, same sections; base commit `ae435bf`, full porcelain and digests in the packet | [round-2 packet](M1-avatar-002/packet-round-2.md); R06 fix-verification (pending) | review dispatched 2026-11-20; two separate verdicts requested | C12, C16, C18 deferred to M3; visual synchronisation, real transport and the bench page NOT_RUN; microphone capture BLOCKED |

The two scopes were batched into one packet at the user's direction, to spend
one reviewer dispatch rather than two after the bounded loop reached its cap.

Both round-1 reviewers independently confirmed all 14 packet digests and
reproduced the claimed test results. Their headline finding was that the
reported audible-onset figures were inflated by a 50 ms probe-clip artifact;
the corrected measurements, the superseded figures and every disposition are in
[resolution.md](M1-audio-001/resolution.md).

**M1 completion.** The avatar clock-adapter demonstration that R01, R02 and
R03 all noted as missing now exists and is under review as `M1-avatar-002`.
Even if both scopes pass, M1 as a milestone still has no measured acoustic
onset, no verified visual synchronisation and no microphone on this PC.

Executed engineering evidence for this checkpoint lives in
[validation/audio_spike.md](../validation/audio_spike.md); the engineering
decisions it rests on are in [decisions.md](../decisions.md).
