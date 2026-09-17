# 08_avisspeech — Tanuki with a local AivisSpeech voice

A separate, runnable version of the existing Tanuki robot, using **AivisSpeech only** for Japanese speech. Includes a copy of the `07_web_model` rig and the existing mouth/body animation driver. Earlier project folders are unchanged.

## Open it

Run `start.ps1` in PowerShell, then open **http://127.0.0.1:8088**. Choose a voice, enter Japanese text, and press **Speak**. **Replay** repeats the generated line; **Stop** closes the mouth and stops playback. The page reconnects automatically while the engine starts.

The engine and renderer are already downloaded on this computer. Python with NumPy is required. For a fresh checkout, run `setup.ps1` first; it installs NumPy and downloads the pinned official AivisSpeech Engine 1.2.0 and Three.js 0.169.0. First engine startup downloads the default voices and language assets. Subsequent synthesis runs locally without an API key or paid cloud service.

```powershell
cd C:\Users\suraj\Downloads\Tanuki\08_avisspeech
.\start.ps1
# When finished:
.\stop.ps1
```

You can also run `python server.py` while your own AivisSpeech app is open. The default engine address is `http://127.0.0.1:10101`; override it with `--engine-url` or `AIVISSPEECH_URL`. `start.ps1` is for the bundled Windows engine on the default port.

## Lip sync

1. Discover installed voice/style IDs from `/speakers` (AivisSpeech IDs are not VOICEVOX's default speaker 1).
2. Request `/audio_query`, retain the engine's mora readings for kanji and dictionary pronunciation, set the requested speed, and send the query to `/synthesis`.
3. Decode the WAV, measure its actual duration, and find its speech boundaries.
4. Build A/I/U/E/O mouth shapes, then use constrained audio-envelope alignment to adjust their timing. Gate the mouth closed during actual silence, including pauses inside the sentence.
5. Drive every mouth mesh from the **same audio element's playback time**. The existing rig adds a 30 ms anticipatory lead. The adjustment slider adds −200 to +200 ms to tune the display for your audio device.

This is **estimated lip timing**, not exact phoneme alignment. AivisSpeech explicitly returns dummy zero values for `consonant_length` and `vowel_length`; matching an audio file's overall duration cannot prove that individual syllables align. Audio-envelope matching improves rhythm but can still choose the wrong vowel timing, especially in long or expressive phrases. Use short Japanese lines (maximum 160 characters per request). English pronunciation/lip shapes are not targeted.

Official API reference: [AivisSpeech Engine compatibility and mora fields](https://github.com/Aivis-Project/AivisSpeech-Engine#readme).

## Integration

```http
POST /api/say
Content-Type: application/json

{"text":"こんにちは。たぬきです。","voice":"888753760","speed":1.0}
```

`voice` is optional; the first installed style is selected if omitted. Obtain current IDs from `GET /api/voices`. The response includes `audio`, `track`, `duration`, `kana`, `speech`, and `timing: "audio-aligned-estimate"`. Use `tanuki.speak({audio: response.audio, track: response.track})` with the included driver.

The viewer offers downloads of the WAV and complete lip-sync response. Generated files are in `.media/`; its cache, the downloaded `runtime/`, and `vendor/` are excluded from Git. The server only listens on loopback and serves the viewer assets and generated media; it does not expose the engine folder.

## Files and maintenance

- `server.py`: AivisSpeech client, audio alignment, local HTTP API.
- `index.html`, `src/app.js`: viewer and voice controls.
- `model/`: copied Tanuki model and textures.
- `demo/greeting.wav`, `demo/greeting.json`: a verified real AivisSpeech greeting and its lip-sync response.
- `src/`, `lib/`: copied animation and Japanese mouth-shape helpers.
- `runtime/Windows-x64/`: official, unmodified engine distribution.
- `runtime/*.log`: engine/server output. `stop.ps1` stops only recorded processes whose paths match this version.
- `%APPDATA%/AivisSpeech-Engine/`: engine-managed downloaded voice models, settings and logs; language assets may also use the standard user cache.

```powershell
python -m unittest discover -s tests -v
node --check src/app.js
```

Tests cover engine reading extraction, stereo WAV resampling, silent intervals, bounded mouth weights, dynamic style IDs, matching audio/track caching, and explicit engine failures. These automated checks establish timing/data consistency; they do not measure perceptual lip-sync accuracy.

Third-party software and voices retain their own licenses. The renderer's MIT license is in `vendor/package/LICENSE`. AivisSpeech Engine is distributed under LGPL-3.0; see its [official repository](https://github.com/Aivis-Project/AivisSpeech-Engine). Voice-model terms are supplied by each voice creator through AivisSpeech/AivisHub.
