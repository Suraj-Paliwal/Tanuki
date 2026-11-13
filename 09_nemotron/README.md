# Tanuki + Nemotron Bolt: integration plan

Status: feasibility assessment only. No model has been downloaded, runtime installed, or chat interface implemented in this folder.

## Intended flow

Browser text input -> local Python chat endpoint -> Nemotron inference server -> Japanese reply -> sentence queue -> AivisSpeech -> Tanuki audio playback and lip sync.

Use the working components in ../08_avisspeech as the starting point. That version currently speaks supplied text; it does not generate replies or transcribe microphone audio.

## Proposed first version

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

Next technical milestone: verify a Turing-compatible inference runtime, load the official GGUF, and measure Japanese generation alongside AivisSpeech before building the complete chat interface.
