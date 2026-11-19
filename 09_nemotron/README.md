# Tanuki experiment and local conversation

Status: M1 in progress. The timing core and the native audio capture/playback
layer exist and are under independent review (`M1-audio-001`). There is still
no experiment state machine, voice-activity detection, stimulus manifest,
server, user interface, model runtime or chat interface in this folder, and no
participant may be run on what exists. The device/timing layer is in
fix-verification review after an independent review found eight Major defects,
all since fixed; the session preflight has not been independently reviewed yet.

Start with [goal.md](goal.md), the current development specification. It prioritizes the prerecorded story-recall experiment, followed by a separate local conversation mode.

## Running the current checks

Python 3.13 with `pip install -r requirements.txt` (numpy, sounddevice). From
this folder:

```text
python -m unittest discover -s tests -p "test_*.py"   # 180 tests, no devices
node --test tests/test_clock_adapter.mjs              # 30 tests, avatar clock
python tools/check_audio.py                           # device inventory + synthetic
python tools/verify_snapshot.py --baseline            # renderer snapshot provenance
python preflight.py --config config/experiment.json   # session preflight
```

The [session preflight](preflight.py) is the start-of-session step `goal.md` §6
requires: it pins audio devices by identity, measures this configuration's
timing, checks disk space and verifies stimulus hashes, and writes the
measurements into the session record. Timing worse than the configured target
is recorded as a warning rather than refusing the session, so measurements
accumulate from real runs instead of a tolerance being guessed up front. **The
microphone is only opened when `preflight.check_capture` is enabled**, which it
is not by default.

The test suite and `tools/check_audio.py` with no flags open no audio device
beyond querying it, and neither records. The preflight does open the configured
output stream and plays a faint probe tone. The remaining modes of
`tools/check_audio.py` touch hardware too: `--survey` and `--commit-trials N`
open an output stream and emit silence, `--playback` plays an audible test
tone, and `--duplex --allow-microphone` would open the microphone.

Two measured facts about this PC, recorded in
[validation/audio_spike.md](validation/audio_spike.md):

- **No input device is attached.** Continuous recording cannot be opened here,
  so microphone-side behaviour is currently verified only on the fake backend
  and acoustic onset measurement is `NOT_RUN`.
- **The Windows default output device is too slow** for the candidate timing
  target: estimated onset delay p95 ≈ 191 ms on MME against ≈ 30 ms on WASAPI,
  where 100 ms is the proposal in `goal.md` §7. Device choice is recorded as
  [decision D5](decisions.md). (An earlier version of this file quoted 233 and
  70 ms; those figures were inflated by a probe-clip artifact that independent
  review caught, and are corrected here.)

- [Elephant–Goldfish review](ELEPHANT_GOLDFISH_REVIEW.md): fresh-context findings, dispositions and remaining readiness gates.
- [Six candidate dialogue stories](EXPERIMENT_STORIES_DRAFT.md): draft materials requiring review; three reference stories and one practice story remain to be prepared.

## Develop with ongoing review

- [Development prompt](DEVELOPMENT_PROMPT.md): give this to a coding chatbot to start or resume implementation.
- [Elephant–Goldfish workflow](EGM_WORKFLOW.md): checkpoint reviews, fresh-context isolation, testing, findings and release gates.
- [Elephant role](reviewers/ELEPHANT.md) and [Goldfish reviewer prompt](reviewers/GOLDFISH.md): reusable instructions for the implementer and independent reviewer.
- [Development status](DEVELOPMENT_STATUS.md): current milestone and next step.
- [Review index](reviews/INDEX.md) and [packet template](reviews/CHECKPOINT_TEMPLATE.md): evidence and review records.
- [Engineering decisions](decisions.md): implementation choices D1-D10, their alternatives, and which research decisions they depend on.
- [Avatar clock evidence](validation/avatar_clock.md): the renderer snapshot, the browser clock adapter, and what remains unverified (visual synchronisation is NOT_RUN).
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

Current next milestone: finish M1. The timing core and device layer are built
and under review; the avatar clock adapter against the real renderer, and any
measurement needing a microphone, are still outstanding. Nemotron compatibility
testing belongs to the later conversation milestone.
