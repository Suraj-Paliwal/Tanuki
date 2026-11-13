# Tanuki experiment and local conversation — development goal

Version: 0.3 reviewed development draft, 2026-11-13 (Japan time).
Status: development specification; no experiment controller or Nemotron integration has been implemented or verified in this folder. Research approval is not asserted.

## 1. Outcome and order of delivery

Build a local Japanese-speaking Tanuki application with two explicitly separated modes:

1. **Experiment mode (first release):** run the planned older-adult story-recall study with prerecorded stories, a single fixed encouragement, controlled pause thresholds, continuous recording, reliable timing evidence, and manual scoring exports.
2. **Conversation mode (later release):** listen to a person and generate short Japanese responses locally using speech recognition, Nemotron and AivisSpeech. This mode is outside the current experimental protocol and must never supply replies or history to an experimental trial.

Success means a researcher can start, supervise, stop, and export a reproducible session; subsequently, a separate local conversation experience can be demonstrated. Installing a model alone does not satisfy either outcome.

The current request is to prepare and review this specification, not to deploy the application or recruit participants. Implementation follows the milestones below. Optional conversation work must not delay the experimental release.

## 2. Sources and authority

Research sources supplied by the user:

- `C:/Users/suraj/Downloads/2_人を対象とする研究_研究計画書_12名探索研究_記入案 (1).docx` — Japanese confirmation draft dated 2026-10-30; sections 6-1 and 6-2 define the trial and analysis design. This is the principal experiment-design reference.
- `C:/Users/suraj/Downloads/2_研究計画書_外部API・利益相反修正版 (1).docx` — revised draft dated 2026-11-04; provides additional external-API conditions. Neither file is treated as evidence of approval.
- User's subsequent development decision: prerecorded experiment first, live conversation later; prefer local processing without paid external AI APIs.

Both documents describe external APIs. A local replacement is a proposed implementation change: the research director must reconcile the submitted/approved plan, explanation and consent materials with the actual data flow before participant use. Do not silently combine conflicting administrative statements from the drafts.

Existing code references:

- `08_avisspeech/README.md`, `ARCHITECTURE.md`, `VALIDATION.md`, `server.py`, `src/app.js`, `src/tanuki-lipsync.js`, `start.ps1`, `stop.ps1`.
- `09_nemotron/EXPERIMENT_STORIES_DRAFT.md`: six newly drafted candidate dialogue stories; not source-document stories, validated stimuli, or final materials.

External technical references for implementation verification:

- https://github.com/snakers4/silero-vad
- https://github.com/ggml-org/whisper.cpp
- https://github.com/Aivis-Project/AivisSpeech-Engine
- https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB

Versions and runtime support must be verified and pinned when installed. External documentation does not establish performance on this PC.

## 3. Study contract

| Item | Requirement from the supplied plan |
|---|---|
| Population | Approximately 12 community-dwelling adults aged 65+, Japanese conversation and informed consent possible; ordinary hearing support allowed |
| Purpose | Explore waiting time, information retained/recovered, and perceived speaking burden; not cognitive diagnosis or ranking |
| Session | One visit, approximately 75–90 minutes including explanation, consent, checks, practice, tasks and breaks |
| Stories | One unscored practice story; nine distinct main stories: three reference and six dialogue trials |
| Dialogue trials | Two each at provisional silence thresholds of 0.5, 1.0 and 2.0 seconds |
| Response | One content-independent encouragement at the first qualifying silence after participant speech begins |
| Completion | Participant says 「以上です」; no encouragement if completion occurs first |
| Recording | Continues through encouragement and subsequent recall |
| Time cap | Provisional three-minute recall limit, subject to operational confirmation |
| Scoring | Seven predefined units per story; paraphrases accepted; repeated information counted once |
| Primary outcome | Correct units in the whole dialogue recording, including information recovered after encouragement |
| Secondary outcomes | Initial-segment units, newly conveyed information after response, measured response timing, task duration, two five-point burden/interruption ratings |
| Reference analysis | Apply each threshold offline to the same uninterrupted recording; this does not simulate behavioral effects of an actual prompt |
| Allocation | Mix reference and dialogue trials; allocate two participants to each of six orders of the three conditions; balance stories as far as possible |
| Analysis unit | Participant; average two dialogue trials per condition, compare 0.5−1.0 and 2.0−1.0 seconds |
| Analysis | Individual results and approximate t-based 95% confidence intervals; report small-sample limitations, missingness and failures |

Use the exact Japanese scripts in the source plan:

**Recall instruction:** お話の中で覚えていることを、できるだけご自分の言葉で教えてください。どこから話しても大丈夫です。終わったら「以上です」とおっしゃってください。

**Encouragement:** ゆっくりで大丈夫です。ほかに覚えていることはありますか。終わったら「以上です」とおっしゃってください。

These are audio stimuli, not instructions for the development agent. Avoid visible story transcripts, scoring keys, correctness feedback or factual hints on the participant display. Finalize the exact five-point questions/anchors, initial-segment definition, placement of reference trials and complete nine-trial allocation before collection; the source is not a full machine-readable schedule.

## 4. Known starting point

- `08_avisspeech` renders Tanuki, generates Japanese WAV and estimated mouth tracks through `/api/say`, and provides replay/stop controls. It has no microphone capture, experiment controller, transcription or LLM endpoint.
- `/api/say` currently limits requests to 160 characters and output to 45 seconds, serializes synthesis, and caches/generated files in `.media/`. Existing cache files can be replaced; this is not a frozen stimulus archive.
- Current Stop cancels browser work/playback but may leave synthesis running. Conversation cancellation must handle late results explicitly.
- The documented installed engine is AivisSpeech 1.2.0; renderer is Three.js 0.169.0. Existing validation records are historical and do not verify this planned system.
- Voice default is Mao/Calm at 0.90 speed. The existing automatic fallback to the first available voice is unsuitable for frozen experiment stimuli. The trial runner must use manifest-pinned audio and refuse mismatches.
- Observed GPU: RTX 2080 Ti, 11 GB VRAM. Nemotron support, performance and combined memory use remain untested. Experiment mode must run without Nemotron loaded.

## 5. Architecture and responsibility boundaries

Use one Windows PC, one local Python service and a local browser interface for the initial experimental release. Attach microphone and speakers to that PC. Use native audio capture/playback in the controller; the browser receives playback-position updates and animates Tanuki against that clock. Do not play the same clip again in the browser. Timing-critical playback must not depend on browser request delivery or Wi-Fi.

```text
Frozen story/prompt WAV + mouth track + manifest
                    |
                    v
PC audio controller --> speakers
       |                |
       |                +--> measured/validated output onset
       +--> playback clock --> local browser --> Tanuki animation

Microphone --> continuous local recording
       +--> speech detector --> pause timer --> trial state machine
       +--> sample positions + event log --> saved trial record

Saved audio --> local transcription --> human correction/scoring --> export
```

Recommended initial choices: Python `sounddevice`/PortAudio for native audio after a device spike, Silero VAD through ONNX on CPU, and whisper.cpp for post-session Japanese transcription. These are proposed dependencies; choose and pin compatible versions after the spike. Avoid introducing a database, distributed services or a cloud fallback in the first release. Use local WAV, JSON and append-only JSONL events; derive CSV exports from them.

VAD means voice activity detection: it estimates speech versus non-speech, not words. ASR means automatic speech recognition: it produces text. ASR is not the pause timer or scoring authority.

Reuse the existing model and animation helpers in a new application under `09_nemotron`; keep `08_avisspeech` runnable. For this plan, use a copied, self-contained snapshot with recorded source paths and hashes. Include the preparation helpers `lib/jp_kana.py`, `lib/jp_lipsync.py` and `lib/align.py`. A new preparation module calls the local AivisSpeech engine directly and writes temporary audio/tracks only to `09_nemotron/.preparation/`, then publishes reviewed stimuli under `09_nemotron/stimuli/`. Do not call the baseline `/api/say` for preparation because it writes into `08_avisspeech/.media`. An already-running local engine may be attached to without claiming ownership. Engine-managed voice caches/settings may remain in their documented user locations; record those locations, and keep participant content out of preparation requests. Large runtime/model downloads and research data remain outside Git. Never copy real participant data as demonstration fixtures.

## 6. Experiment state machine and audio rules

Controller states: `SETUP -> READY -> STORY -> INSTRUCTION -> AWAITING_SPEECH -> RECALL -> FINALIZING -> REVIEW`. `RECALL` has a one-use encouragement flag; the prompt does not end recall. Ending an active trial enters `FINALIZING` with a separate terminal reason: `COMPLETION_CANDIDATE`, `ABORTED`, `FAULT` or `TIMEOUT`. After integrity checks, `REVIEW` permits annotation and an adjudicated outcome such as `COMPLETE`; keep controller state, terminal reason and adjudicated outcome as distinct fields. Crash recovery reconstructs the unfinished finalization rather than inventing success. Breaks occur between trials. Pausing an active recall ends that attempt with its reason; it is not silently resumed as an equivalent uninterrupted trial.

### Starting a trial

1. Validate session ID, allocation, stimulus hashes, device identities, available disk space and audio-clock health.
2. Open the recording and log before stimulus playback. Mark stimulus/instruction/recall intervals so the whole acquisition is preserved but only the intended recall interval is scored.
3. Play the story once and then the recall instruction. Ignore their speaker output for participant-onset detection; a microphone/output reference must distinguish system audio from participant speech.
4. Define recall time zero as the instruction's audible end. Start the three-minute cap then (a proposed operational definition requiring research confirmation). Arm pause-triggering only after participant speech is detected. No speech before the cap is a timeout, not a successful zero-score completion.

### Silence and prompt scheduling

- Preserve original audio; use a separate normalized/resampled stream for VAD. Log the mapping back to original audio sample indices.
- Define silence onset from the end of the most recent detected participant speech frame. Document frame size, thresholds, smoothing, minimum speech length and detector hangover. Do not add the configured waiting interval twice through VAD hangover plus a second timer.
- At the assigned threshold, re-check that speech has not resumed, completion/stop has not been registered, and no encouragement has started. Serialize decisions in one controller so duplicate browser events cannot trigger duplicate playback.
- Define the output commit boundary as the last point where queued prompt audio can reliably be removed before entering the device buffer. Cancel a candidate when resumed speech is detected before that boundary. Resumption after commitment but before audible onset may still overlap the prompt; no perfect cancellation guarantee is made. Log detector delay, commit and acoustic onset separately and flag this case for the predeclared deviation rule.
- Proposed rearming rule: a cancellation before commitment does not consume the one-prompt allowance. Return to listening and calculate a fresh deadline from the next detected speech offset. Commitment consumes the allowance; a post-commit output failure becomes a fault, not a reason to retry. Log every candidate and cancellation separately. Confirm this operational interpretation with the research director before freezing the manipulation.
- Once encouragement starts, the proposed policy is to play the short clip through ordinary resumed speech and preserve the overlap. Stop, fault, completion and timeout still interrupt output according to the precedence table below. This overlap policy needs confirmation before freezing the study configuration.
- Reference trials never play encouragement. They retain equivalent recording, display and completion handling.

### Completion and interruption

Initial experimental delivery is supervised. The researcher has a dedicated completion control to mark an observed 「以上です」 and suppress a pending prompt; log the control timestamp and later annotate the spoken completion onset from audio. Use the same procedure across conditions. A separate Stop control handles withdrawal/distress and stops output immediately while finalizing recoverable data.

Human detection delay can exceed 0.5 seconds. Test completion immediately before each threshold. If the operator cannot reliably suppress prompts after completion, do not claim the protocol is satisfied: add and validate a local completion-phrase detector or revise the completion procedure with the research director. ASR-generated partial text alone is not sufficient proof of completion. Log late suppression failures as deviations and retain them in exports.

Any unexpected recording, playback, clock, device or disk failure stops prompt output, finalizes what is recoverable and flags the attempt. Do not continue a trial while recording is broken or replay a story automatically after failure. Restarts/replacements require a recorded protocol decision because repeating a story changes exposure.

### Event precedence and scored interval

Use one serialized controller queue. Apply events by controller timestamp; at the same timestamp/cycle, use the order below. Evaluate terminal conditions again immediately before output commitment. Retain every observed event even when it loses precedence. This proposed operational policy must be included in the research freeze.

| Priority | Event | Output and trial disposition |
|---|---|---|
| 1 | Participant/researcher Stop, withdrawal, distress | Stop output; finalize recoverable recording; `ABORTED` with reason |
| 2 | Audio/storage/clock/control-connection fault | Stop output; finalize recoverable recording; `FAULT` |
| 3 | Completion control already received | Stop any remaining output; finalize recording; completion candidate pending annotation |
| 4 | Recall time cap reached | Stop output and finalize; `TIMEOUT`, not completed/zero-score |
| 5 | Participant speech resumes | Cancel uncommitted prompt and rearm; log overlap if commitment already passed |
| 6 | Eligible encouragement commitment | Commit once if all higher-priority guards remain clear |

No adjudicated outcome becomes `COMPLETE` solely from a browser event. Persist terminal reason, integrity checks and later annotation/adjudication separately; do not rewrite the event history. Finalization enters `REVIEW` even for aborted, faulted or timed-out attempts; review does not itself imply successful completion. If Stop and a fault coexist, preserve the fault flag even though Stop determines the terminal reason.

The proposed primary scored interval begins at instruction audible end and ends at the earliest of annotated spoken completion onset, the recall cap, or a stop/fault endpoint. Scoring includes all eligible recall before that end, including speech overlapping encouragement. Do not score later remarks merely because the operator marked completion late. Keep the full acquisition and annotated boundaries. A completion discovered retrospectively may change the adjudicated outcome but never erase the original timeout or a post-completion prompt deviation. Confirm this interval rule and deviation inclusion/exclusion before collection; the initial-segment boundary remains a separate research decision.

Participant speech overlapping the recall instruction is retained and flagged as early speech; do not pretend it began after instruction end or silently include it in the main scored interval. Predeclare its handling and do not replay the story automatically.

## 7. Timing evidence and calibration

Keep time within the audio controller: a monotonic clock plus input/output sample positions. Wall-clock timestamps identify files but must not calculate waiting intervals. Record any mapping between browser display time and controller time; browser timing is not authoritative.

Record at least:

- Participant speech onset/offset; qualifying pause onset; configured threshold and eligibility deadline.
- Prompt scheduled, committed and output-buffer positions; clip leading-silence offset.
- Audible onset measurement or calibrated estimate, its method and uncertainty. Never label a scheduling timestamp as a measured acoustic onset.
- Participant restart, overlap, completion-control event and annotated spoken completion time.
- Instruction/story start/end, timeout, operator actions, device faults and dropped frames.

Calibrate on the final PC/microphone/speaker configuration with a recorded playback reference. Prefer simultaneous captured output/reference for per-trial measurement; if only a separate calibration is available, explicitly label trial onsets as estimates. An acoustic reference must not collect video or unrelated conversations. If a reference adds recording channels, include them in the data inventory.

Validate actual last-speech-to-audible-response time, detector boundary error and playback delay separately. Freeze numerical tolerances before participant use. A candidate engineering target is playback-onset delay after the eligible deadline of no more than 100 ms at the 95th percentile, with no unintended early trigger; this is a proposal, not a measured result or research-approved bound. Report all observations and maxima, not only averages. Failure to meet an agreed tolerance blocks participant deployment, not documentation or bench development.

Test low-volume speech, long pauses, breaths, coughs, background noise, playback leakage, resumed speech around the deadline and continuous speech. Preserve simultaneous participant speech during encouragement; never solve echo by muting the only microphone recording. Use close microphone placement and/or a validated echo-cancellation analysis path, with raw audio retained under the agreed policy.

Reuse `TanukiLipSync.playTrack(track, getTime)`, which plays no audio. `getTime` returns the controller's estimated audible playback position in seconds relative to the start of the complete frozen WAV, including any file offset. Use timestamped updates with bounded interpolation and an explicit stale-update fault. The adapter must call `stop()` on clip end, abort, fault and disconnect because an external-clock track does not automatically finish. Freeze the existing mouth lead/offset settings; do not add browser AudioContext output-latency compensation to native audio. Bring a minimal renderer/asset snapshot into M1 to test this adapter. Visual synchronization needs bench verification; existing energy-aligned tracks do not establish exact phoneme timing.

## 8. Stimuli, allocation and scoring

Create a frozen manifest containing ten story IDs (practice plus nine main), Japanese text, seven-unit rubrics for main stories, audio/track filenames and hashes, voice/model/version, speed, duration and pronunciation-review status. Include the fixed instruction and encouragement assets. This manifest is immutable once a collection version is released.

Review the six existing candidate stories for natural Japanese, comparable difficulty, familiarity and repetitive-template learning effects. Add three reference stories and one practice story; do not relabel the six as a complete study set. Confirm compound-unit scoring, acceptable paraphrases, corrections and contradictions before collection.

If a story exceeds the existing synthesis limits, prepare it offline in reviewed chunks and concatenate the final waveform/tracks with consistent pacing, or deliberately extend and verify the preparation service. The released trial always loads one complete reviewed asset; it never synthesizes a story during the trial.

The allocation file must list all nine trial positions for each of the 12 planned participants, with unique story IDs, trial type and threshold. Validate three reference trials and two per dialogue threshold, no repeated main story within a participant, and the intended two-participants-per-order balance. The six-order rule does not uniquely specify how two repetitions and references are interleaved; a researcher must choose and freeze that table. Record the freeze deadline before recruitment; do not change allocations for convenience after recruitment. Any authorized amendment gets a new version, rationale and research review as applicable. Report any remaining story/condition imbalance.

Produce a cross-tabulation of story frequency by threshold, trial position and trial type. Record whether reference stories have fixed roles or rotate across participants and require explicit researcher acceptance of residual imbalance; correct per-participant counts alone do not demonstrate counterbalancing.

Scoring records include full-recall unit scores, evidence timestamps, initial-segment unit scores and first post-response occurrence times as applicable. Provide separate scorer entries, an adjudication field and a predefined independently scored subset. Do not show scoring during recall or generate grades with Nemotron.

Offline reference processing uses the same versioned VAD/endpoint rules and reports all three cut positions without altering original audio. For files with no qualifying pause, mark no-cut explicitly. Keep initial-cutoff and actual-audible-response boundaries separate; the precise initial-segment scoring boundary must be settled before collection.

Export participant-level means and paired differences with trial status/missingness. Exclude or include deviations according to a predeclared analysis rule, not a convenient post-hoc choice. Do not replace missing data with zero, count trials as participants, or equate reference truncation with actual interruption effects.

## 9. Interface and operation

Participant view: Tanuki, clear listening/speaking/break states, accessible text size, and an obvious Stop option. No live transcript, story cues, timer or condition label during measured recall unless explicitly standardized in the protocol. Keep animation/background behavior consistent across conditions.

Researcher view: participant/session ID, validated allocation, audio device health, recording state, trial progress, Start, completion marker, Stop/Abort, break controls, two rating questions and export status. Protect active-trial controls from double clicks and stale connections. Mode switching is prohibited during an active session.

Use a second locally attached display or a researcher screen positioned outside the participant's view. Verify physical screen separation in the dry session so condition labels, scoring and controls do not become participant cues. This arrangement is a deployment requirement, not a blocker to synthetic development.

Use a single local controller owner. Multiple browser tabs may observe but cannot independently advance the same session. A browser refresh reconnects to server state; it must not restart playback or create a second recording. Losing the controlling UI must produce a defined fault/stop rather than an unsupervised continuing experiment.

For the local web service, validate Host and Origin, deny unrelated cross-origin requests and require controller-issued capabilities for operator actions and sensitive reads/events/exports. Use an unguessable per-launch operator credential, not a browser-declared role, and a restricted participant-display capability. The participant capability permits display updates and Stop for its current session, but denies trial advancement, completion marking, scoring and sensitive reads/exports. Avoid a new user-account database for this single-PC release. Protect state-changing requests against cross-site submission and authorize every action against current session ownership; a second tab cannot claim control simply by connecting. Include rejection tests for untrusted origins, absent credentials and unauthorized event/export subscriptions. Bind to loopback; any later network/iPad exposure requires its own authenticated HTTPS configuration.

Initial host is this PC with locally served assets and loopback-bound services. Future iPad use is a separately tested interface extension; keep audio/timing on the PC initially. A standalone iPad AI application and App Store publication are outside these milestones.

## 10. Data and local operation

Use research IDs in application records. Names/contact details and signed consent stay in separate university-managed systems. The application records only an operator's confirmation that required consent exists, not a scanned consent document.

Authoritative session files live in a configured university-managed research-data directory outside the repository and web static root. Only synthetic fixtures may live under tests. Use file permissions appropriate to approved researchers. Avoid speech/transcripts in general application logs, crash telemetry or public diagnostics. No raw audio is published or pushed to Git.

Suggested record structure:

```text
<research-data-root>/<session-id>/
  session.json                 # mode, protocol/stimulus/allocation versions
  events.jsonl                 # ordered event records with trial/attempt IDs
  trials/<trial-id>/<attempt-id>/
    microphone.wav
    output-reference.wav       # only if this measured channel is configured
    trial.json                 # condition, state, outcomes, timing quality
    transcript.json            # generated then human-corrected; versioned
    scores.json                # scorer/adjudication evidence
  exports/                     # reproducible CSV/JSON derivatives
```

Write incrementally and finalize atomically where appropriate. Detect incomplete attempts after crashes; never silently mark them complete. File names use internally generated safe identifiers. Restrict web routes to intended assets/actions; never expose the research-data directory through a generic file server.

Withdrawal handling must locate recordings, transcripts, scoring, exports and any backups by session/participant ID; apply the approved deletion/retention policy and keep a minimal permitted audit. Final retention duration and backup access remain research-director decisions. Local processing does not anonymize voices or automatically encrypt disks/backups.

After setup downloads, prove the experimental mode works with internet disconnected. Verify the actual configuration has no cloud fallback, telemetry upload or remote asset requirement. Ordinary model downloads are separate from participant-data handling. Document third-party engine and chosen voice terms before distribution.

## 11. Later live conversation mode

Only start after the experiment release is usable and isolated.

```text
Microphone -> local VAD/ASR -> local Nemotron text reply
           -> reply checks -> AivisSpeech -> Tanuki audio/animation
```

Use a separate session namespace, prompt configuration, history and output directory. Experiment controller APIs must reject conversational generation requests. Switching modes clears conversational state; no research story or scoring rubric is inserted into ordinary chat context by default.

Start Nemotron with a compatible local runtime and official quantized model only after proving load/generation on the RTX 2080 Ti. Initial engineering target: single user, 4K–8K context, concise conversational mode, reasoning disabled when supported, and no optional drafter. These are starting settings, not performance promises. Record model/runtime versions and actual memory, first-token and first-audio latency with ASR/TTS active.

First prototype may use push-to-talk to establish correctness, followed by tested automatic turn-taking. Provide interrupt/Stop, cancel pending work, discard stale late synthesis/generation results and close the avatar mouth on stop. The existing `/api/say` stop behavior alone is insufficient. Do not speak reasoning, tool payloads or partial invalid replies. Split valid Japanese replies to respect the current speech-service limits.

Editable system prompts should support respectful adult language, short replies, one question at a time, no invented personal memories, clear AI identity, and immediate respect for stop/skip. Do not assume cognitive impairment from age. Avoid medical diagnosis or medication instructions, pressure for personal data, and claims to be family or a clinician. Use deterministic checks and reviewed fallback responses where appropriate; a prompt is not a safety guarantee.

Keep personal memory off by default. Any persisted history needs explicit user control and deletion. Test confusion, grief, repetition, unsupported beliefs, sensitive information, instruction overrides, transcription mistakes and interruptions with synthetic scenarios before any participant-facing use. This is a conversational prototype, not a validated care intervention or an extension of the approved experiment unless separately reviewed.

No paid API or silent alternative model fallback. If the selected model/runtime fails on this hardware, report the failure and evaluate a named alternative explicitly. Conversational failures must not affect experiment operation.

## 12. Detailed implementation plan and write boundaries

All proposed implementation writes are under `09_nemotron/`; the list below names future files, not files already present. The existing `08_avisspeech` baseline is read-only for this development unless a later change is expressly justified.

| Milestone | Proposed files | Work and exit evidence |
|---|---|---|
| M0 — freeze specification | `goal.md`, `ELEPHANT_GOLDFISH_REVIEW.md`, `README.md`, `decisions.md` | Resolve review findings; record research-owned open decisions without inventing approval |
| M1 — audio feasibility | `requirements.txt`, `audio_io.py`, `timing.py`, `tools/check_audio.py`, `tests/test_timing.py`, `validation/audio_spike.md` | Select/pin audio/VAD dependencies; measure PC capture/playback, clock mapping, avatar clock adapter feasibility and completion handling with synthetic audio |
| M2 — stimuli and schedule | `prepare_stimuli.py`, `preparation.py`, `lib/jp_kana.py`, `lib/jp_lipsync.py`, `lib/align.py`, `.preparation/`, `stimuli/manifest.json`, `stimuli/audio/`, `stimuli/tracks/`, `stimuli/rubrics.json`, `config/allocation.json`, `tests/test_materials.py` | Implement preparation against the local engine with isolated scratch storage; validate synthetic assets/allocation first; freeze reviewed research materials later |
| M3 — experiment core | `server.py`, `experiment.py`, `vad.py`, `storage.py`, `config/experiment.json`, `tests/test_experiment.py`, `tests/test_storage.py` | Implement state machine, continuous recording, one-prompt policy, reference trials, faults and durable records; fake-clock/audio tests verify boundaries |
| M4 — usable local interface | `index.html`, `researcher.html`, `src/app.js`, `src/controller-client.js`, `src/tanuki-lipsync.js`, `src/body.js`, `src/bands.js`, `src/formants.js`, `src/quality.js`, `model/`, `vendor/`, `asset-provenance.json`, `setup.ps1`, `start.ps1`, `stop.ps1`, `.gitignore` | Copy/reuse renderer assets; adapt to native playback clock; operator ownership, reconnection and accessible UI verified; downloads/data excluded appropriately |
| M5 — transcription/scoring/export | `transcribe.py`, `analyse_reference.py`, `scoring.py`, `export_results.py`, `tests/test_analysis.py`, `tests/fixtures/` | Offline transcript review, timestamped manual scoring and reference cuts; known-answer fixtures reproduce participant-level calculations |
| M6 — experimental validation | `VALIDATION.md`, `run.md`, `validation/` | Execute full synthetic 10-story session, timing/echo/completion/failure tests and offline-network check; freeze version and document limitations; participant use requires research approvals/materials |
| M7 — local conversation feasibility | `llm_client.py`, `config/conversation.json`, `prompts/conversation_ja.txt`, `validation/nemotron.md` | Prove model/runtime compatibility and resource use; text-only Japanese replies first |
| M8 — voice conversation | `conversation.py`, `conversation.html`, `src/conversation.js`, `tests/test_conversation.py`, `validation/conversation.md` | Add ASR, short reply checks, TTS, interruption and mode separation; verify actual response latency and safety scenarios |

Milestones are dependency gates, not a requirement to wait for final research materials before coding. M3–M5 may proceed with clearly labeled, versioned synthetic manifests and allocations while research review continues. The minimal renderer snapshot/provenance listed under M4 may be brought forward into M1 for the clock-adapter spike. Only collection requires the frozen research materials.

Reuse existing API semantics only where verified: `08_avisspeech` has `/api/status`, `/api/voices`, `/api/say` and generated media routes, not a chat or experiment API. Its existing server already restricts static paths and disables directory listings. The new `server.py` should retain an explicit asset allowlist and keep research data outside all served roots. Expose a narrow session-action API and read-only event stream; define request/response schemas and action idempotency in M3 before implementing the UI.

Configuration must record mode, versioned device IDs, detector settings, timing policy, assets/allocation, data root and cap. Trial settings are frozen at session start; changes require ending the session and creating a new configuration version. Launchers record whether they created or merely attached to each process. Stop only owned processes; request graceful controller shutdown and recording finalization before bounded forced termination, which must leave an incomplete-attempt record. Keep background windows hidden.

## 13. Verification and completion criteria

### Experiment release

- [ ] Ten reviewed stories/assets exist; nine main trials satisfy the allocation contract; frozen audio is used without synthesis calls during trials.
- [ ] Known synthetic pauses trigger correctly at all thresholds; no pre-speech trigger, duplicate encouragement, reference-trial encouragement or automatic replay.
- [ ] Resumed speech, completion, stop and timeout races have deterministic logged outcomes.
- [ ] Full participant audio survives encouragement overlap; clock/sample mapping and dropped-frame detection are verified.
- [ ] Actual timing evidence meets predeclared bounds on final hardware; completion suppression is validated at the shortest threshold.
- [ ] Device loss, disk error, browser disconnect, repeated actions and service crash produce flagged recoverable attempts, not false completion.
- [ ] Source audio remains immutable through transcription, reference cuts and scoring; expected unit/participant calculations match fixtures.
- [ ] Exports distinguish missing, aborted, timeout, deviation and complete outcomes; missing is not zero.
- [ ] Operator can run a full dry session from documented setup, with internet disconnected and no participant data in repository/web assets/logs.
- [ ] Research-owned decisions below are settled and protocol/consent/data-flow descriptions match the released system before participant use.

### Conversation release

- [ ] Exact model/runtime runs on this PC with measured resources; no cloud fallback or claimed unmeasured latency.
- [ ] A complete local microphone-to-spoken-Tanuki exchange works and can be interrupted reliably.
- [ ] Late requests cannot speak after stop or mode/session change; experimental mode cannot call generation.
- [ ] Japanese reply constraints and synthetic safety cases have recorded outcomes and residual limitations.
- [ ] Local data controls, setup and failure recovery are documented.

Documentation completion is not evidence that any of these software checks have passed.

## 14. Decisions still required

| Decision | Owner / deadline | Consequence |
|---|---|---|
| Final stories, rubrics, Japanese question wording and rating anchors | Researcher/Japanese reviewers, before stimulus freeze | Drafts cannot be used as validated materials |
| Full nine-trial schedule and interpretation of six condition orders | Research director/researcher, before allocation freeze | Controller must not invent a counterbalancing scheme |
| Recall cap origin, completion procedure, event precedence, rearming, early-speech and overlap policies | Research director, informed by M1 | These operational choices affect the experimental manipulation |
| Primary scoring endpoint, initial-segment cutoff and handling of deviations/no-pause cases | Research director/analyst, before collection | Required for reproducible analysis |
| Device models, measured timing tolerance and calibration method | Developer + research director, M1/M6 | Hardware feasibility and protocol fidelity are not yet proven |
| Independent-scoring subset, agreement/adjudication procedure | Research team, before collection | Avoid retrospective selection |
| Data storage, retention, access, backups and withdrawal process | Research director/university, before collection | No invented retention period or anonymization claim |
| Reconciled ethics/consent description for local processing | Research director, before collection | Supplied drafts still describe external APIs |
| Nemotron runtime compatibility and later conversation boundaries | Developer + user, M7 | Does not block the experiment release |

These decisions permit development with clearly labeled synthetic fixtures. They block the relevant material freeze or participant deployment, not unrelated engineering work.

## 15. Elephant–Goldfish review record

See `ELEPHANT_GOLDFISH_REVIEW.md` for independent fresh-context findings, resolutions, residual gates and the actual review scope. Do not describe self-review as independent review or a design review as runtime validation. Update this goal after accepted findings and preserve the distinction between implemented evidence, planned work and research decisions.
