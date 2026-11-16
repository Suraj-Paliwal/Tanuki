# Goldfish review — workflow-001 / focused / round 1

Original reviewer output returned on 2026-11-17. Coordinator assigned reviewer ID R01 for storage; original finding IDs WF-GF01–03 are preserved. The failed November 13 attempt produced no report.

## Provenance and scope

- **Fresh context:** Yes. This reviewer received the review assignment and neutral packet, without the development conversation. The interrupted November 13 attempt produced no verdict and is not counted as a completed review.
- **Snapshot:** `reviews/workflow-001/packet.md`. Independently computed SHA-256 values for all 11 targets matched its manifest. The inspected target contents remained unchanged.
- **Readiness question:** Can a future coding assistant invoke this toolkit while preserving independent review and honest evidence gates?
- **Inspected:** All nine requested toolkit files, `goal.md`, and historical `ELEPHANT_GOLDFISH_REVIEW.md`.
- **Executed:** Read-only file inspection, SHA-256 calculation, directory inventory, and scoped Git status.
- **NOT_RUN:** Application tests, hardware measurements, services, model installation, microphone capture, and participant-data checks. None is needed to assess this documentation checkpoint.
- The packet reports author-executed formatting/link checks; I did not independently rerun that script. External EGM conformity and underlying research documents were outside this review.

## My understanding

The toolkit instructs a future coding assistant to build the prerecorded experiment first, using bounded implementation checkpoints and synthetic evidence before proceeding to the separate conversation mode. The implementation agent retains project context, while reviewers receive a stable packet in genuinely separate contexts. Review findings, fixes, evidence, and remaining research decisions must remain traceable; a documentation or engineering pass cannot authorize participant use. The files become active instructions when invoked by a capable assistant and do not constitute a background service or an instruction to implement during this documentation task.

## Findings

**No Blocker or Major findings.**

### WF-GF01 — Minor: the copyable reviewer prompt omits its required report template

- **Location:** `reviewers/GOLDFISH.md:3–34`.
- **Evidence:** The opening instruction says to copy “this prompt,” and the first fenced block ends at line 32. Inside it, line 31 requires “the structured report below,” but that report appears in a separate block starting at line 36. Copying only the apparent prompt block into a manual fresh chat leaves an unresolved reference and omits the provenance, snapshot, and verdict fields.
- **Remedy:** Explicitly instruct the dispatcher to supply the entire file, including both blocks, or combine the instructions and report requirements into one complete copyable prompt.
- **Verification:** Copy the documented invocation into an otherwise empty chat and confirm it contains the complete output requirements without relying on omitted text.
- **Scope blocked:** None; full-file dispatch already works.

### WF-GF02 — Minor: report filenames and finding IDs lack a reviewer namespace

- **Location:** `EGM_WORKFLOW.md:38`, `:50`, `:98`, and `:121`.
- **Evidence:** Multiple reviewers can inspect the same stage and round, but the documented report filename is `goldfish-<stage>-round-<n>.md`. The example finding ID also lacks reviewer identity. Two parallel focused reviewers can consequently select the same filename and both report `…-GF01`. `GOLDFISH.md:11` requires a unique destination, which mitigates this but leaves the naming convention incomplete.
- **Remedy:** Include a stable reviewer identifier in report paths and finding IDs, for example `goldfish-focused-r02-round-1.md` and `M1-audio-001-R02-F01`.
- **Verification:** Prepare two same-stage, same-round dispatches and confirm both reports and their finding references remain distinct.
- **Scope blocked:** None; the coordinator can currently assign unique destinations manually.

### WF-GF03 — Minor: historical instructions conflict with the new review-storage convention

- **Location:** `ELEPHANT_GOLDFISH_REVIEW.md:104`, compared with `EGM_WORKFLOW.md:118–122` and `reviews/INDEX.md:5`.
- **Evidence:** The historical document tells future agents to record each development finding and recheck “here.” The new toolkit instead directs those records into checkpoint directories and the review index. Because the development prompt explicitly requires reading the historical document, both instructions are encountered during normal invocation.
- **Remedy:** Mark that historical repeat-review instruction as superseded and point ongoing records to `EGM_WORKFLOW.md` and `reviews/INDEX.md`. Preserve the original design findings.
- **Verification:** Follow the development-start reading sequence and confirm it identifies one authoritative location for new checkpoint records.
- **Scope blocked:** None; this is a recordkeeping ambiguity.

## Open research decisions and evidence gaps

The workflow correctly preserves unresolved materials, allocation, timing, completion, operational policy, scoring, and data-governance gates. Their existence does not block this documentation checkpoint or unrelated synthetic engineering. This review supplies no evidence that any implementation milestone or research gate has passed.

## Verdict

**PASS_FOR_SCOPE — static workflow-document clarity, consistency, and invocation readiness, with three Minor findings.**

The toolkit provides actionable fresh-context review instructions, limits reviewer permissions, requires snapshot and evidence checks, and clearly separates authoring documentation from starting implementation. This verdict covers the recorded document snapshot only. It is not an implementation checkpoint, runtime validation, participant authorization, or certification of the external EGM protocol.
