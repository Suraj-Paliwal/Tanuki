# How the AivisSpeech Tanuki version works

## Scope

`08_avisspeech` is a standalone copy of the existing Tanuki avatar with an AivisSpeech-only Japanese voice service. Its current role is to speak supplied text with mouth and body animation. It has no microphone input, speech recognition, language-model chatbot, reminiscence-memory database or conversation history UI. A conversational application can supply its own replies through the API described below.

The earlier `06_web` and `07_web_model` folders are not runtime dependencies: the required model and animation helpers have been copied into this folder. This version does not train a new voice or alter the model's mesh.

## Components and data flow

```text
Browser: Japanese text + voice + speed
    |
    | POST /api/say
    v
server.py ----> AivisSpeech /speakers
    |          /audio_query -> pronunciation/mora reading
    |          /synthesis   -> WAV audio
    |
    +--> PCM audio decoding and resampling for analysis
    +--> Japanese reading -> A/I/U/E/O mouth-shape plan
    +--> Audio-envelope alignment and silence gating
    +--> Save matching WAV + JSON in .media/
    |
    v
Browser receives { audio, track, ... }
    |
    +--> One audio element plays the WAV
    +--> TanukiLipSync samples track using that element's currentTime
    +--> Three.js updates mouth morph targets and renders the model
```

The viewer and engine listen on loopback by default. The supplied launcher uses the official engine's `--disable_sentry` option. The application does not use a cloud synthesis fallback. Setup and first-run engine downloads need network access; the downloaded renderer is served locally.

## Why this voice is the default

The reminiscence preset selects the installed style whose name is `まお` and whose style is `おちつき` (Mao / Calm), currently ID `888753763`. Speed defaults to `0.9`. The calm style and modest pace reduction are a design starting point for gentle conversation, not a measured claim about all older adults' preferences or comprehension. Both remain adjustable.

The backend resolves the style by name each time from the installed voice list rather than relying on the numeric ID alone. If unavailable, it uses the first installed style. No available styles results in a clear error. An explicitly supplied invalid voice ID is rejected instead of silently replaced.

## Audio and lip timing

`query_reading()` reads `accent_phrases[].moras[].text`, preserving the engine's interpretation of kanji and dictionary entries. Pause moras become pauses in the mouth plan. It does not use the top-level `kana` field as a phonetic transcript.

The current engine returns dummy zero values for consonant/vowel duration fields. Those fields are never used as exact timing here. See the [official AivisSpeech Engine API compatibility notes](https://github.com/Aivis-Project/AivisSpeech-Engine#readme).

`decode_wav()` accepts uncompressed PCM WAV with 8-, 16- or 32-bit samples, mixes channels to mono, and resamples to 16 kHz for analysis. The original WAV is kept for playback. Unsupported/incomplete audio and silent clips are rejected.

`make_track()` performs the following:

1. Measure the actual audio duration.
2. Calculate a 25 ms energy envelope with a 10 ms hop; find speech above a −40 dB relative threshold and add a small boundary margin.
3. Build the Japanese vowel-shape sequence for that speech span with `jp_lipsync.build()`.
4. Use constrained dynamic time warping to fit predicted mouth opening to the audio envelope. The alignment helper retains the original estimate if the warp does not meet its improvement checks.
5. Gate the five vowel weights with measured energy, so actual silences close the mouth. Sample these tracks every 10 ms and set the first and last weights to zero.

The response always labels timing `audio-aligned-estimate`; `align.aligned` reports whether the warping step was accepted. The internal before/after correlation concerns mouth opening versus audio energy, not the correctness of individual phonemes.

The track contains five channels: `A`, `I`, `U`, `E`, `O`. Each is an array of `[time_in_seconds, weight]`. Weights interpolate between mouth shapes. The returned `fps: 30` is inherited track metadata; the final keys are sampled at a 10 ms interval, and the browser renders at its own frame rate. Blink animation is handled by the browser driver's idle-blink behavior.

The browser drives all matching morph-target meshes, including mouth components. `TanukiLipSync` adds a 30 ms lead and brief smoothing. The offset slider adds −200 to +200 ms. Body motion uses the audio bands where the browser audio graph is available.

Long, emotional or unusually pronounced lines can still have imperfect local alignment. This implementation has not been validated as a clinical intervention or as an exact phoneme aligner.

## API

All examples use the default viewer server at `http://127.0.0.1:8088`. The browser talks to this server; it does not call AivisSpeech directly.

### GET /api/status and GET /api/voices

Both routes currently return the same connection information:

```json
{
  "engine": "aivisspeech",
  "ready": true,
  "voices": [
    {"id": "888753763", "name": "まお", "style": "おちつき"}
  ],
  "default_voice": "888753763",
  "default_speed": 0.9,
  "message": "Connected"
}
```

This is an abbreviated example; the real list includes all installed styles. An unreachable engine produces HTTP 503 with `ready: false`, an empty voice list, and a message. No installed voices produces HTTP 200 with `ready: false` and `default_voice: null`.

### POST /api/say

```json
{
  "text": "こんにちは。よろしければ、昔よく聴いていた歌について、お話を聞かせてください。",
  "voice": "888753763",
  "speed": 0.9
}
```

| Field | Rules |
| --- | --- |
| `text` | Required string, nonblank, at most 160 characters. Use Japanese. |
| `voice` | Optional installed style ID. Omitted/empty uses the configured preferred style. |
| `speed` | Optional finite number, 0.5–2.0; defaults to 0.9. The viewer exposes 0.5–1.5. |

The request body limit is 8192 bytes. Clips longer than 45 seconds are rejected after synthesis and decoding. Requests execute through a single synthesis lock, so concurrent browser requests queue.

Response fields:

| Field | Meaning |
| --- | --- |
| `engine` | `aivisspeech` |
| `voice`, `speed` | The actual requested/resolved style and speaking speed |
| `kana` | Japanese reading extracted from the engine's mora data |
| `duration` | Actual clip duration in seconds, rounded to four decimal places |
| `speech` | Detected speech start/end seconds within the original WAV |
| `timing` | `audio-aligned-estimate` |
| `align` | Whether the alignment warp was accepted, with diagnostic scores/reason when available |
| `audio` | Same-origin `/media/<hash>.wav` URL |
| `track` | Duration, metadata and `tracks` mapping of A/I/U/E/O keyframes |
| `cached` | Whether this response reused this process's generated audio/track pair |

HTTP 400 reports invalid inputs or rejected audio/reading as `{"error":"..."}`. HTTP 503 reports engine availability/synthesis HTTP errors. Unexpected failures produce HTTP 500 and details in the server log. The browser displays the error instead of switching to a different TTS provider.

### GET /media/<hash>.wav and .json

Serves the generated audio or saved full response. The JSON is a wrapper containing `track`, not just the track itself. The allowed media filename is a 24-character lowercase hexadecimal hash followed by `.wav` or `.json`.

### Connect your own reply generator

On a page served by this viewer, with the included Tanuki driver already loaded:

```javascript
const response = await fetch('/api/say', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ text: replyText })
});
const result = await response.json();
if (!response.ok) throw new Error(result.error);
await tanuki.speak({ audio: result.audio, track: result.track });
```

Supply short Japanese replies from your own application. There is no `/api/chat` endpoint. Cross-origin browser access is not configured; a separate frontend needs an appropriate same-origin proxy or deliberate integration changes.

## Configuration

| Change | Location / action |
| --- | --- |
| Preferred voice | `server.py` → `default_voice()`; change the matching installed speaker/style names |
| Default speed | `server.py` → `DEFAULT_SPEED`; also update the initial speed value/output in `index.html` |
| Visible preset description and starting prompt | `index.html` |
| Viewer port | `python server.py --port 8089` |
| Engine address | `--engine-url` or `AIVISSPEECH_URL` in `server.py`; launcher uses default local ports |
| Additional mouth offset | Browser slider; initial HTML value is 0, driver `offset` default is 0 |
| Driver lead/smoothing | `src/tanuki-lipsync.js` constructor settings |
| Alignment behavior | `server.py` → `make_track()` and `lib/align.py` |

The browser obtains the preferred voice from `/api/status` and keeps a selected voice during reconnects if still installed. The speed slider's initial value is defined in HTML; it is not populated from `default_speed`. If changing defaults in code, keep the HTML preset text and values consistent with the backend. Restart the server for Python changes and refresh the browser for frontend changes.

## Storage, cache and cancellation

The cache key hashes the engine URL, style ID and complete synthesis query, including speed. This avoids reusing a different reading after dictionary/query changes. Up to 64 responses are held in memory; the oldest inserted key is removed when that limit is reached. This is not a disk-retention limit.

The original WAV is written through a temporary file then renamed, followed by its JSON response. The on-disk files survive restart, but the server does not reload them into its response cache. A later synthesis of the same query can replace that hash's files.

The browser request timeout is 240 seconds; individual engine synthesis/query calls allow 180 seconds, and voice-list calls allow five seconds. **Stop** cancels the browser's pending request or playback. It does not propagate cancellation into the engine; already-running synthesis may finish and save its output.

Generated readings and voice recordings are stored locally in `.media/`. The application has no user identity, consent workflow or automated deletion mechanism. Its current scope is a local prototype. The engine owns its separate model/settings/log folders; see [run.md](run.md#9-logs-saved-clips-and-backups).

## File map

| File / directory | Responsibility |
| --- | --- |
| `run.md` | Setup, start, stop, manual operation and troubleshooting |
| `README.md` | Project entry point and documentation links |
| `VALIDATION.md` | Recorded tests, real samples and limitations |
| `setup.ps1` | Python dependency and pinned runtime/renderer downloads |
| `start.ps1`, `stop.ps1` | Background process lifecycle for the default Windows setup |
| `server.py` | Engine client, waveform analysis, response/cache handling, HTTP routes |
| `index.html` | Viewer layout, controls, initial preset and text |
| `src/app.js` | Scene setup, voice selection, request/playback/stop controls |
| `src/tanuki-lipsync.js` | Track playback, morph targets, blink behavior and audio clock |
| `src/body.js`, `src/bands.js` | Body movement and audio-band energy |
| `src/formants.js` | Existing driver's optional live-audio vowel support; generated speech uses tracks |
| `src/quality.js` | Model texture/render quality helpers |
| `lib/jp_kana.py`, `lib/jp_lipsync.py` | Japanese mora parsing and mouth-shape planning |
| `lib/align.py` | Audio-energy envelope and constrained timing alignment |
| `model/` | Tanuki glTF, binary geometry and three WebP textures |
| `demo/` | Saved verification samples, including the reminiscence voice |
| `tests/test_server.py` | Engine-independent Python tests |
| `runtime/`, `vendor/`, `.media/` | Downloaded/runtime/generated content excluded from Git |

The official engine is unmodified. Its LGPL license, the renderer's MIT license and individual voice-model terms remain applicable; voice styles are discovered locally rather than being redistributed as newly trained models here.
