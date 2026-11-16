# Prompt to give the development chatbot

Copy the text below into a coding chatbot with access to the Tanuki folder. This prompt requests implementation when you send it; creating this file alone does not start development. It requires local tools to edit/run code and fresh agents or a separate new chat for independent review.

---

Develop the Tanuki system in:

`C:\Users\suraj\Downloads\Tanuki\09_nemotron`

Read `AGENTS.md`, `goal.md`, `DEVELOPMENT_STATUS.md`, `EGM_WORKFLOW.md`, `reviewers/ELEPHANT.md` and the existing `ELEPHANT_GOLDFISH_REVIEW.md`. Inspect the actual code and current Git state before making changes. Use `08_avisspeech` as the read-only baseline and keep unrelated work intact.

Implement the goal, starting with the prerecorded experiment. The later live local Nemotron conversation mode must remain separate and must not delay the experimental release. Do not start by downloading the LLM. Follow M1–M6 first; build M7–M8 after the experiment's engineering acceptance is satisfied. Research-owned gates may remain pending for synthetic development, but must remain visibly pending before participant deployment. If current files show work already completed, resume the first unfinished step rather than rebuilding it.

Act as the Elephant: retain project context, make reasonable implementation choices, implement bounded slices, run meaningful checks and fix problems. I explicitly request fresh-context Goldfish reviewer agents during development, following `EGM_WORKFLOW.md`. Use `reviewers/GOLDFISH.md` and a neutral packet for each substantive checkpoint. Reviewers must not inherit this development conversation; use history-disabled agents when available. If the environment cannot create them, prepare a packet for a genuinely new chat and clearly mark independent review unavailable. Do not simulate independence by changing your role in this chat.

For each checkpoint:

1. State the requirement, intended behavior, files to change and applicable acceptance checks.
2. Implement and test with synthetic fixtures. Measure hardware-dependent claims or explicitly record missing evidence.
3. Save a stable snapshot packet with relevant files/dependencies, file hashes, test commands/results and limitations. Include untracked/dirty files; a Git commit alone is insufficient.
4. Obtain the required fresh review before claiming that checkpoint complete. Stop editing its target while reviewers inspect it.
5. Resolve findings, rerun affected checks, and get fresh verification of material fixes. Keep original findings and dispositions in the review record. Do not hide failures or weaken requirements to obtain a pass.
6. Update `DEVELOPMENT_STATUS.md`, `reviews/INDEX.md`, relevant validation records and running instructions. Continue the next unblocked authorized step.

Preserve the study's fixed scripts, single encouragement, continuous recording, three silence thresholds, reference-trial behavior and manual-scoring design. Distinguish configured waiting time, output commitment and actual audible onset. Handle completion, resumed speech, Stop, timeout and faults according to the versioned controller policy. Treat unresolved research decisions in the goal as proposals until confirmed; do not invent approvals, final story difficulty, counterbalancing or retention rules.

Keep all AI processing local and add no paid/cloud fallback. Store real research data outside the repository and served assets; use synthetic data for automated checks. Do not begin live microphone capture without clearly telling me. Do not recruit participants, collect study data, publish, push to GitHub or deploy publicly as part of this development prompt. Stop only processes you actually launched and finalize recordings before shutdown.

Use the existing Tanuki assets and `playTrack(track, getTime)` where appropriate. The current `/api/say` baseline writes into its own media folder, so follow the new isolated preparation path in the goal. Keep experiment mode usable without a loaded LLM and reject cross-mode generated replies/history.

Do not repeatedly ask permission for routine, reversible implementation steps. Ask only when a decision materially changes scope/research behavior, a required authorization is missing, or an external blocker prevents the next dependent step; continue independent work meanwhile. Follow the workflow's bounded review loop rather than endless review or superficial test-count growth.

Give concise progress updates. When interrupted or ending a turn, record what actually changed, what tests ran and passed/failed, what Goldfish reviewed, remaining gates and the exact next action. Do not say the system is ready for participants merely because code or a reviewer passed.

Start now by inspecting the project and implementing the first unfinished M1 synthetic audio/timing feasibility step. Continue through the authorized development scope, keeping milestones and reviews current.
