# Tanuki experiment and local conversation

Status: planning and design review only. No experiment controller, model runtime or chat interface has been implemented in this folder.

Start with [goal.md](goal.md), the current development specification. It prioritizes the prerecorded story-recall experiment, followed by a separate local conversation mode.

- [Elephant–Goldfish review](ELEPHANT_GOLDFISH_REVIEW.md): fresh-context findings, dispositions and remaining readiness gates.
- [Six candidate dialogue stories](EXPERIMENT_STORIES_DRAFT.md): draft materials requiring review; three reference stories and one practice story remain to be prepared.

## Develop with ongoing review

- [Development prompt](DEVELOPMENT_PROMPT.md): give this to a coding chatbot to start or resume implementation.
- [Elephant–Goldfish workflow](EGM_WORKFLOW.md): checkpoint reviews, fresh-context isolation, testing, findings and release gates.
- [Elephant role](reviewers/ELEPHANT.md) and [Goldfish reviewer prompt](reviewers/GOLDFISH.md): reusable instructions for the implementer and independent reviewer.
- [Development status](DEVELOPMENT_STATUS.md): current milestone and next step.
- [Review index](reviews/INDEX.md) and [packet template](reviews/CHECKPOINT_TEMPLATE.md): evidence and review records.
- [AGENTS.md](AGENTS.md): folder-level instructions for coding agents that support automatic discovery.
- [Workflow validation](reviews/WORKFLOW_VALIDATION.md): review outcome and checks for these reusable instructions.

These Markdown files are invoked by the coding assistant; they are not an installed plugin or background watcher. Tools supporting `AGENTS.md` can discover the folder instructions. Other chatbots must be given the development prompt and referenced files explicitly.

The earlier feasibility notes below are retained as background for the later conversation mode. Where they differ from `goal.md`, the current goal takes precedence. In particular, Nemotron installation is not a prerequisite for the experimental release.

## Earlier conversation feasibility assessment

Browser text input -> local Python chat endpoint -> Nemotron inference server -> Japanese reply -> sentence queue -> AivisSpeech -> Tanuki audio playback and lip sync.

Use the working components in ../08_avisspeech as the starting point. That version currently speaks supplied text; it does not generate replies or transcribe microphone audio.

## Earlier proposed conversation version

- Separate web interface with chat history, Send, Stop, voice selection, and the Tanuki avatar.
- Local backend calling an OpenAI-compatible inference endpoint. Keep the inference endpoint on localhost.
- Q4_K_M GGUF model, no optional DFlash drafter initially.
- Start with a 4K-8K context, one active conversation, conversational mode enabled and thinking disabled, subject to runtime support.
- Generate short Japanese replies, split them into speech chunks, and enforce the existing speech limits per chunk: 160 characters and 45 seconds of audio.
- Speak only the final reply; exclude reasoning and tool data from speech.
- Stop should cancel generation, pending synthesis and playback.
- Keep bounded conversation history. Persistent memory and microphone transcription are later features.

## Hardware observed

On assessment, nvidia-smi reported an NVIDIA GeForce RTX 2080 Ti with 11264 MiB total video memory and 8753 MiB free. Free memory changes with running applications. System RAM could not be read using the available system query.

The memory capacity looks promising, but this is not a compatibility or speed test. The model card's software integration section lists Linux and newer GPU architectures, not Windows/Turing. A compatible Windows CUDA build of llama.cpp and a real model load/generation test are required. Do not assume NVIDIA's supplied CUDA 13 container runs on this GPU. A CPU or remote server fallback may be necessary.

## Constraints and useful applications

- The model accepts and emits text. AivisSpeech supplies speech, and Tanuki supplies animation. Microphone input requires a separate speech recognition component.
- The 4GB branding is a target workload footprint, not a fixed total memory requirement. Context, concurrency, runtime buffers, speech synthesis and rendering consume additional memory.
- Japanese dialogue is supported by the model; the current mouth shapes and voice pipeline target Japanese. Other languages need suitable voices and lip-sync work.
- Lip timing in the current AivisSpeech integration is estimated and aligned to audio, not exact phoneme timing.
- Response speed must be measured on this PC; published newer-GPU results do not predict RTX 2080 Ti performance.
- Useful for conversational companions, reminiscence prompts, museum/exhibition guides, Japanese practice and interactive characters. Document-grounded FAQ requires retrieval; app actions require implemented and validated tools.
- Answers and tool calls can be incorrect. For reminiscence use, avoid inventing a person's past and retain user control over stored conversation data.
- Local use can operate without cloud inference after downloads, provided every chosen component is local. Public hosting requires authentication, HTTPS, rate limits, and capacity planning; visitors cannot use this PC's localhost.
- The model card describes commercial and noncommercial availability under OpenMDW-1.1. Distribution must follow applicable model, engine, voice and asset terms.

## Sources

- NVIDIA release: https://research.nvidia.com/labs/nemotron/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB/
- Official model card and serving examples: https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Bolt-E4B-4GB
- Existing project: ../08_avisspeech/README.md and ../08_avisspeech/ARCHITECTURE.md

Current next milestone: validate local audio capture, playback timing, completion handling and avatar synchronization with synthetic fixtures. Nemotron compatibility testing belongs to the later conversation milestone.
