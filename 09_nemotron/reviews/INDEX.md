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
| `M1-audio-001` — complete tree incl. session preflight | 3 | goal v0.3; base commit `0198546` (user commits), dirty files and digests in the round-3 packet | [round-3 packet](M1-audio-001/packet-round-3.md); R04 fix-verification | packet being prepared | C12, C16, C18 deferred to M3 with named owners; acoustic onset NOT_RUN; microphone capture BLOCKED; all device figures measured over TeamViewer |

Both round-1 reviewers independently confirmed all 14 packet digests and
reproduced the claimed test results. Their headline finding was that the
reported audible-onset figures were inflated by a 50 ms probe-clip artifact;
the corrected measurements, the superseded figures and every disposition are in
[resolution.md](M1-audio-001/resolution.md).

**M1 is not complete even if round 2 passes.** Both reviewers noted that the
avatar clock-adapter demonstration required by `goal.md` §7 does not exist; it
is a separate future checkpoint (`M1-avatar-002`).

Executed engineering evidence for this checkpoint lives in
[validation/audio_spike.md](../validation/audio_spike.md); the engineering
decisions it rests on are in [decisions.md](../decisions.md).
