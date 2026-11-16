# Validation of the reusable development workflow

Date: 2026-11-17, Asia/Tokyo.

## What was reviewed

The reusable `AGENTS.md`, development-start prompt, ongoing EGM workflow, Elephant/Goldfish prompts, status and review templates were checked against the existing goal and historical design review.

- [Original neutral packet with SHA-256 target manifest](workflow-001/packet.md).
- [Fresh-context R01 report](workflow-001/goldfish-focused-R01-round-1.md).
- [Findings and fixes](workflow-001/resolution.md).

The initial review attempt on November 13 hit a usage limit and produced no verdict. The November 17 retry completed and independently confirmed all 11 target-file fingerprints. It returned **PASS_FOR_SCOPE** with no Blocker/Major findings and three Minor findings. Those Minor fixes were then applied and author-checked. There was no independent second review of the changed files.

## Executed checks

- Before review: 11 target files decoded as UTF-8, had balanced fenced blocks and no trailing whitespace; 14 relative Markdown links resolved.
- Reviewer: static file inspection, SHA-256 comparison, directory inventory and Git-status inspection.
- After fixes: final formatting, relative-link and reviewer-name collision checks are recorded below.

No application code was changed. Application tests, microphone capture, speech synthesis, model installation, timing calibration and participant operations were not run. A documentation pass establishes usability of the instructions, not correctness of future software.

## Reproducing the final documentation check

Run from `C:/Users/suraj/Downloads/Tanuki` using Python 3. The check reads Markdown only and does not start services or modify project files.

```python
from pathlib import Path
import re

root = Path('09_nemotron')
files = sorted(root.rglob('*.md'))
links = 0
for path in files:
    text = path.read_text(encoding='utf-8')
    assert sum(line.startswith('```') for line in text.splitlines()) % 2 == 0, path
    assert all(line == line.rstrip() for line in text.splitlines()), path
    for target in re.findall(r'\]\(([^)]+)\)', text):
        if '://' in target or target.startswith('#'):
            continue
        assert (path.parent / target.split('#')[0]).exists(), (path, target)
        links += 1
names = [f'goldfish-focused-{r}-round-1.md' for r in ('R01', 'R02')]
ids = [f'M1-audio-001-{r}-F01' for r in ('R01', 'R02')]
assert len(set(names)) == len(names)
assert len(set(ids)) == len(ids)
print(f'PASS: {len(files)} Markdown files; {links} relative links; unique reviewer names/IDs')
```

An initial final-check attempt counted literal backticks inside its own displayed Python example as a Markdown fence and failed on this file. The checker was corrected to count fence lines; the rerun result is recorded below. This was a documentation-checker issue, not an application test failure.

Final result: **PASS — 16 Markdown files, 24 relative links, and distinct same-stage/same-round reviewer names and finding IDs.** `git diff --check` also completed without whitespace errors; Git emitted ordinary LF/CRLF conversion warnings. No application tests were required for this documentation-only change.

## How to use the deliverable

Give the complete `DEVELOPMENT_PROMPT.md` to a coding assistant with this folder available. It will read the project instructions, implement the first unfinished checkpoint and invoke fresh reviewers when its tools permit. When they do not, it must prepare a manual fresh-chat packet and label the missing independent review honestly. These files do not run in the background by themselves.
