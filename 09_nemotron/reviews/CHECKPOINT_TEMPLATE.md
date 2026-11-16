# Review packet template — not a completed checkpoint

Copy to a new checkpoint directory and replace every placeholder. Do not submit this template unchanged or treat its example statuses as results.

## Identity and requested review

- Checkpoint ID: `<M1-audio-001 or another unique safe ID>`
- Created: `<date/time and timezone>`
- Route/stage/lenses: `<from EGM_WORKFLOW.md>`
- Reviewer IDs and unique output destinations: `<R01, R02; goldfish-stage-R01-round-1.md, etc.>`
- Requested verdict scope: `<for example, ready to implement native clock adapter>`
- Goal version and sections: `<version; section IDs>`
- Actual implementation status: `<what exists now>`
- Open research gates: `<what is deliberately not finalized>`

## Expected behavior and change boundaries

- Requirement and observable before/after behavior:
- Invariants that must remain true:
- Files changed/created/deleted:
- Read-only baseline dependencies:
- Out of scope:

## Snapshot identity

- Base/current Git commit if present:
- Dirty/untracked state and diff artifact:
- File/hash manifest (include relevant untracked files, dependencies and evidence):

| Path | Role | SHA-256 |
|---|---|---|
| `<path>` | `<implementation / test / source / evidence>` | `<actual digest>` |

Target edits pause during review. Recheck hashes on return and mark stale coverage explicitly if anything changed.

## Acceptance checks and actual evidence

| Requirement | Check | Status | Evidence path / result | Limitations |
|---|---|---|---|---|
| `<goal reference>` | `<test or measurement>` | `<PASS / FAIL / NOT_RUN / BLOCKED>` | `<real evidence>` | `<scope not established>` |

For each executed check, record exact command and working directory, dependency/runtime versions, timestamp, exit result and relevant output. For acoustic tests also identify hardware, sampling/clock setup, measurement method and uncertainty. List failed attempts as well as fixes/reruns. Do not place real participant audio or credentials in the packet.

## Reviewer permissions

- Default: read-only inspection.
- Explicitly allowed test commands, if any:
- Isolated scratch/output/cache directory:
- Prohibited resources: real participant records, live microphone, network/model downloads, unrelated processes.
- Requested report destination (or return text to coordinator):

## Prior findings (fix-verification only)

| ID | Original severity | Disposition | Change/evidence | Still-open gate |
|---|---|---|---|---|
| `<id>` | `<severity>` | `<FIX / CONTEST / DEFER / DUPLICATE>` | `<path>` | `<if any>` |

Omit this section from an initial independent review. Do not supply other reviewers' opinions to bias the initial verdict.
