# Elephant–Goldfish development review

Date: 2026-11-13 (Japan time).
Target: [goal.md](goal.md), initially version 0.1, revised to 0.2 for the final fresh review and 0.3 after its minor corrections.
Scope: design and static code review. No application was implemented, model downloaded, service started, hardware calibrated or participant session run for this review.

## 1. Method and provenance

The user requested the Elephant–Goldfish development process. This review uses its core separation: the context-aware author drafts the specification; fresh-context reviewers receive the written specification and referenced sources, without the earlier conversation. The author records and resolves findings, while research/architectural decisions remain visible to the user.

Reference: [Google's EGM repository](https://github.com/google/elephant-goldfish-model) and [review protocol](https://github.com/google/elephant-goldfish-model/blob/main/docs/designs/review.md).

This was a manually orchestrated adaptation, not an execution or certification of the installed EGM plugin. Strategic/comprehension, critique and implementation/codebase lenses ran independently in the first round. A fresh reviewer then checked the revised design for scope and readiness. It does not claim to have completed the official plugin's full staged workflow or two consecutive clean rounds. Design review does not substitute for testing or research approval.

| Reviewer | Fresh context | Material / lens | Execution |
|---|---|---|---|
| `goldfish_comprehension` | Yes; no conversation history | Goal, candidate stories and referenced research documents; comprehension and strategic fit | Completed |
| `goldfish_critic` | Yes; no conversation history | Goal; experimental behavior, timing, failure and access boundaries | Completed |
| `goldfish_readiness` | Yes; no conversation history | Goal and referenced baseline code/docs; dependencies, APIs and implementation readiness | Completed |
| `goldfish_final` | Yes; no conversation history | Revised goal and referenced sources; final scope/readiness check | Completed; no Blocker or Major findings |

Reviewers were read-only. The author made the document changes. Findings below are synthesized from actual reviewer outputs, with author resolutions distinguished from independently verified outcomes.

## 2. Elephant: context and design rationale

The primary deliverable is a supervised experiment investigating the relationship between response waiting time and older adults' story recall. The research documents specify approximately 12 participants, one unscored practice story, three uninterrupted reference stories and six dialogue stories, with two dialogue trials at each of 0.5, 1.0 and 2.0 seconds. Encouragement is fixed and delivered once; primary scoring uses seven predefined units across the full eligible recall recording.

The user also wants a future local conversational character. The accepted development order is prerecorded experiment first, then an isolated live conversation mode. Keeping those releases separate avoids letting variable generated wording or model latency enter the current experiment while still preserving the longer-term product objective.

The existing `08_avisspeech` implementation supplies avatar rendering, Japanese speech preparation and estimated mouth tracks. It does not supply a trial controller, continuous microphone recording, pause manipulation or conversational LLM. The plan reuses the proven code surfaces without treating their historical validation as proof of the new system.

Native PC capture/playback is proposed to centralize timing and recording. The browser displays the avatar against the native playback clock. This choice creates an adapter/calibration obligation, so the first implementation milestone is a synthetic feasibility spike before participant deployment assumptions are frozen.

## 3. Goldfish comprehension result

The fresh comprehension reviewer independently understood the proposal as:

1. A local Japanese Tanuki application initially serving a supervised recall experiment with fixed stimuli and one timed encouragement.
2. A native controller owning audio, timing and records while the browser renders the character.
3. Human-reviewed transcripts/manual scoring, with final materials and operational rules settled before collection.
4. A separate later local ASR–Nemotron–speech mode that cannot feed generated content or history into experimental trials.

This matches the intended architecture. The reviewer identified no Blocker or Major issue preventing synthetic bench development, but found three comprehension/operational gaps listed below.

## 4. Findings and resolutions

Severity records the reviewing agent's rating. “Addressed in specification” means the written contract was changed; it does not mean the corresponding code has been implemented or tested.

| ID | Severity / source | Finding and consequence | Resolution / status |
|---|---|---|---|
| GF-01 | Major / readiness | Stimulus preparation omitted imported lip-sync helpers; calling the baseline service would write to its `.media` despite the read-only baseline boundary. | **Addressed in specification, §§5/12.** Add `preparation.py` and three `lib/` helpers, call the local engine directly, use isolated `.preparation/` scratch and frozen `stimuli/` output; record provenance and engine-managed cache exceptions. |
| GF-02 | Major / critic | Cancellation until audible onset was promised even after audio commitment, which buffering cannot guarantee. | **Addressed in specification, §6.** Guarantee cancellation only when restart is detected before the defined commit boundary. Preserve commit/acoustic/detector timestamps and flag late races. Research acceptance of deviation handling remains open. |
| GF-03 | Major / critic | Completion, stop, timeout and prompt commitment lacked a common precedence rule; late completion marking could expand scoring incorrectly. | **Addressed in specification, §6.** Add serialized event handling, precedence table, terminal dispositions, and separate observed/adjudicated outcomes. Propose scored boundaries tied to spoken completion, cap and stop/fault. These operational policies require research confirmation. |
| GF-04 | Major / critic | A cancelled prompt candidate had no defined rearming or allowance-consumption rule. | **Addressed in specification, §6.** Proposed pre-commit cancellation rearms from the next speech offset; commitment consumes allowance; post-commit failure does not retry. Confirm manipulation policy before freeze. |
| GF-05 | Major / critic | Localhost binding alone did not specify protection from unrelated browser pages/tabs. | **Addressed in specification, §9.** Validate Host/Origin, deny unrelated cross-origin requests, require per-launch operator capability and restricted display capability, authorize actions and sensitive reads, and test unauthorized subscriptions/exports. No account database added. |
| GF-06 | Minor / comprehension | Ordered milestones could imply controller work must wait for final study stories. | **Addressed in specification, §12.** Explicitly allow M3–M5 against versioned synthetic materials while research review proceeds. Material freeze remains a collection gate. |
| GF-07 | Minor / comprehension | Separate web views did not ensure the participant could not see researcher information on the physical display. | **Addressed in specification, §9.** Require a second local display or screened operator position and verify it in the dry session. |
| GF-08 | Minor / comprehension | The source prohibition on changing allocation for convenience after recruitment was not carried over explicitly. | **Addressed in specification, §8.** Record a pre-recruitment freeze deadline, forbid convenience reassignment and version authorized amendments. |
| GF-09 | Minor / readiness | The external-clock renderer API and end-of-track cleanup were underspecified. | **Addressed in specification, §7.** Name `playTrack(track, getTime)`, define time origin/units, require explicit `stop()` at termination, and bring the minimal renderer snapshot into M1. Native audio does not use browser output-latency compensation. |
| GF-10 | Minor / readiness | Goal incorrectly called baseline static serving unrestricted. | **Corrected factual error, §12.** Baseline `server.py` already allowlists paths and disables directory listings. Retain that pattern and keep research data outside served roots. |
| GF-11 | Minor / readiness | Process ownership and graceful recording shutdown were not explicit enough. | **Addressed in specification, §12.** Distinguish attached from launched processes; stop only owned processes, finalize gracefully, and flag forced termination as incomplete. |
| GF-12 | Minor / critic | Trial counts alone could pass validation despite story difficulty being confounded with threshold. | **Addressed in specification, §8.** Export story × threshold × position/type distributions, decide fixed versus rotating reference roles, and require acceptance of residual imbalance. No allocation scheme invented. |
| GF-13 | Minor / final | Controller state, terminal reason and adjudicated outcome were not consistently named. | **Addressed in version 0.3, §6.** Define the three separate fields and finalization/review transitions; remove editorial wording about adding TIMEOUT. |
| GF-14 | Minor / final | “Play through” overlap wording could conflict with terminal-event interruption. | **Addressed in version 0.3, §6.** Play through ordinary resumed speech only; Stop, fault, completion and timeout still stop output. |
| GF-15 | Minor / final | Participant Stop was not explicitly permitted by the restricted display capability. | **Addressed in version 0.3, §9.** Allow Stop for the current session while denying completion marking, trial advancement and sensitive access. |

The author also made early speech during the instruction an explicit retained/flagged event, rather than silently assuming all recall begins after the instruction. All substantive behavior choices are labeled proposals until the research team freezes them.

## 5. Evidence checked against the existing code

- `08_avisspeech/src/tanuki-lipsync.js` contains `playTrack(track, getTime)`. It samples a caller-owned clock without playing audio. The external-clock path requires explicit lifecycle handling.
- `08_avisspeech/server.py` imports `lib/jp_kana.py`, `lib/jp_lipsync.py` and `lib/align.py`; these are dependencies of copied stimulus preparation, not optional documentation references.
- The baseline service writes its own `.media` files. Calling it would violate a strict no-write promise for the old folder.
- The baseline HTTP handler restricts static routes and rejects directory listing/HEAD; the initial draft's contrary wording was incorrect.
- Baseline start/stop semantics require care when attaching to an engine already running. The new experiment launcher must use explicit ownership and recording-aware shutdown.

These are static observations. They do not show that the proposed native playback integration, timing precision or experiment data recovery works.

## 6. Remaining decisions and release gates

| Gate | Why it remains open | Development impact |
|---|---|---|
| Completion at the 0.5-second threshold | Human marking or automatic recognition may arrive too late to suppress a prompt. | M1 must measure it; failure requires a validated detector or research-approved procedure change. |
| Timing and output reference | Actual audible onset differs from timer execution; hardware/driver details are untested. | Spike and calibration first; no participant-ready timing claim. |
| Final stimuli and rubrics | Six drafted stories are not difficulty-validated; three reference stories and practice are missing. | Synthetic development can proceed; final material freeze cannot. |
| Full allocation and analysis rules | Six condition orders do not uniquely specify all nine trial positions, reference roles or secondary scoring boundaries. | Research-owned table and scoring/adjudication rules needed before collection. |
| Operational policies | Cap origin, rearming, early speech, overlap, completion/scoring endpoints and deviations affect interpretation. | Implement proposed rules behind versioned configuration; obtain research confirmation before freezing. |
| Screen, device and environment setup | Operator information and speaker leakage could affect participant experience or detection. | Verify physical deployment and microphone/output arrangement in the full dry session. |
| Ethics and data handling | Supplied drafts describe cloud APIs; retention/access and local-system explanations must be reconciled. | Does not block synthetic engineering; blocks unapproved participant use. |
| Nemotron compatibility | This PC has an older RTX GPU; exact runtime support and latency are untested. | Later conversation milestone only; experiment release has no dependency on it. |

These are explicit gates, not hidden assumptions or a request to stop all work. Neither reviewer approval nor a finished Markdown document authorizes research recruitment.

## 7. Final review and decision

The initial independent reviewers found no blocker to M1 synthetic development. Five Major specification findings were accepted and addressed in version 0.2. The final fresh-context reviewer found **no Blocker or Major findings** in that version and judged it ready for M1 synthetic development. Its three Minor clarifications were applied in version 0.3 and checked by the author; no additional independent pass of 0.3 is claimed.

All 15 reported findings have written dispositions and corresponding specification changes. This is one revised design with a fresh follow-up review, not two consecutive clean official EGM rounds. No runtime acceptance item has been marked passed by this review.

Current design disposition: experiment-first architecture retained; later conversation remains a separate mode; no cloud deployment, native iPad inference, automated scoring, new account database or broad memory system added to the experimental scope.

## 8. Ongoing development reviews (updated 2026-11-17)

The earlier instruction to append ongoing development reviews to this historical report is superseded by [EGM_WORKFLOW.md](EGM_WORKFLOW.md). Preserve the design findings above. Store new checkpoint packets, reports and resolutions under `reviews/<checkpoint-id>/` and register them in [reviews/INDEX.md](reviews/INDEX.md). Give fresh reviewers the current goal, relevant source files and validation evidence without the earlier conversation. Prefer correcting the specification or implementation over adding features solely to satisfy a reviewer.

Before declaring a milestone complete, compare the code and measured evidence with the relevant acceptance checks in `goal.md`. Label unmeasured outcomes as unmeasured. Research protocol amendments and real participant authorization remain decisions for the research team.
