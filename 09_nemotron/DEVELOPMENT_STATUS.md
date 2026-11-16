# Development status

Updated: 2026-11-17 (Japan time).

## Current state

- `goal.md` version 0.3 describes the experiment-first system and later isolated conversation mode.
- A design-only Elephant–Goldfish review exists in `ELEPHANT_GOLDFISH_REVIEW.md`.
- The reusable workflow, role prompts and development-start prompt are prepared; they do not run autonomously.
- A fresh-context documentation review returned PASS_FOR_SCOPE with three Minor findings; their fixes are recorded in `reviews/WORKFLOW_VALIDATION.md`. This is not an implementation pass.
- No experiment controller, native audio integration, model installation or conversation implementation has been completed in this folder as part of these documentation tasks.
- Existing `08_avisspeech` speech/avatar validation is historical baseline evidence, not validation of the new system.
- Six candidate dialogue stories exist. They are not finalized/validated stimuli; reference and practice materials remain outstanding.

## Next action when implementation is requested

Begin M1: inspect current dependencies/devices and implement a synthetic audio/timing feasibility slice under `09_nemotron`. Define a neutral review checkpoint, run relevant checks, and dispatch a fresh Goldfish reviewer. Bring in the minimal renderer snapshot as needed for external-clock feasibility. Do not start by installing Nemotron.

## Milestone ledger

| Milestone | Status | Evidence / pending condition |
|---|---|---|
| M0 specification/review | Development draft reviewed; research-owned decisions open | `goal.md`, historical design review |
| M1 audio feasibility | Not started | Capture/playback, clock mapping, completion handling and avatar adapter unmeasured |
| M2 materials/tooling | Candidate text only | No final ten-story manifest, frozen recordings or approved allocation |
| M3 controller | Not started | No implementation evidence |
| M4 interface | Not started for new system | Reusable baseline exists in `08_avisspeech` |
| M5 analysis/export | Not started | No implementation evidence |
| M6 experiment validation | Not started | Final-hardware tests and research gates pending |
| M7 model feasibility | Not started | RTX 2080 Ti compatibility/performance unverified |
| M8 conversation | Not started | No local conversation pipeline |

## Open gates

Use `goal.md` §14 as the decision list. In particular: timing/completion validation, final materials/allocation, operational policies, scoring boundaries, data governance and reconciled research approvals. They do not block unrelated synthetic engineering. Live conversation is a later milestone and cannot alter experiment behavior.

## Resume contract

On each handoff update this file with the active checkpoint, actual changed files, checks run (including failures), review packet/verdict, unresolved finding IDs, owned running processes and exact next command/action. Re-read actual files before trusting a stale status entry. Preserve history in review/validation records rather than repeatedly appending duplicate status prose here.
