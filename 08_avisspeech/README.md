# 08_avisspeech — Tanuki for reminiscence conversations

A local Japanese voice-and-avatar demo using **AivisSpeech** and the existing Tanuki model. It speaks supplied text with estimated lip sync, a choice of installed voices, and playback controls.

## Start here

**[Read run.md for complete setup and running instructions](run.md).**

On the computer where setup was completed:

```powershell
cd "C:\Users\suraj\Downloads\Tanuki\08_avisspeech"
.\start.ps1
```

Open [the robot viewer](http://127.0.0.1:8088/), wait for the connected message, and press **Speak**. Use `.\stop.ps1` from the same folder when finished. On a fresh checkout, follow the first-time setup section in `run.md` first.

## Documentation

| Guide | What it covers |
| --- | --- |
| [run.md](run.md) | Requirements, first-time setup, everyday start/stop, controls, manual startup, troubleshooting, logs and backups |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Components, lip-sync method, API, configuration, cache behavior, cancellation and file responsibilities |
| [VALIDATION.md](VALIDATION.md) | Recorded automated checks, real voice tests and limits of the evidence |

There is also a short [run.md at the project root](../run.md) pointing to this version.

## Reminiscence preset

The default voice is **まお / おちつき — Mao / Calm**, currently style ID `888753763`, at **0.90×** speed. This is a gentle conversational starting point; adjust the voice and pace to the listener's preference. If the style is absent, the first installed style is used.

The starting prompt politely invites the listener to talk about songs they used to hear:

> こんにちは。よろしければ、昔よく聴いていた歌について、お話を聞かせてください。

The viewer and API use this voice/speed preset. Voice and speed controls can override it for a new line. Changes made in the viewer do not persist across page reloads.

## What is included

- A copy of the Tanuki model and textures from `07_web_model`, plus the existing animation helpers.
- A local Python server that requests AivisSpeech audio and creates matching A/I/U/E/O mouth tracks.
- A viewer with voice selection, speed, lip-sync adjustment, Speak, Replay, Stop and WAV/JSON downloads.
- Windows setup/start/stop scripts, five engine-independent Python tests, and recorded real-engine verification.
- Saved [normal-voice greeting](demo/greeting.wav) and [calm reminiscence sample](demo/reminiscence.wav), with their matching [greeting response](demo/greeting.json) and [reminiscence response](demo/reminiscence.json).

This folder runs without the earlier `06_web` or `07_web_model` directories. It does not train a voice, modify the mesh, listen to the person, or generate conversational replies. A reply-generating application can connect to the documented `/api/say` endpoint.

## Lip-sync expectations

The mouth follows the audio playback clock. Japanese vowel shapes come from the engine's reading, with timing estimated from the generated audio and mouth closure during silence. AivisSpeech does not provide usable exact phoneme durations in the current API, so this is **audio-aligned estimation**, not exact syllable synchronization. The adjustment slider can tune an overall offset.

Use short Japanese lines: input is limited to 160 characters and generated audio to 45 seconds. English lip shapes are not targeted. See [the timing explanation](ARCHITECTURE.md#audio-and-lip-timing) for details.

## Dependencies and storage

The supplied setup pins **AivisSpeech Engine 1.2.0** and **Three.js 0.169.0**, and requires **NumPy >=1.24,<3**. The current copy was tested on Windows with Python 3.13. No paid cloud speech API or API key is used.

`runtime/`, `vendor/`, `.media/`, logs and Python bytecode are excluded from Git. The engine also stores voice models and settings in `%APPDATA%\AivisSpeech-Engine\`; language assets may use the standard user cache. Setup and first-run downloads need internet access. See [storage and backup instructions](run.md#9-logs-saved-clips-and-backups) before moving the project to another computer.

## Third-party licenses

The unmodified AivisSpeech Engine is distributed under LGPL-3.0; see its [official repository](https://github.com/Aivis-Project/AivisSpeech-Engine). Three.js's MIT license is in `vendor/package/LICENSE` after setup. Individual voice models retain their creators' terms supplied through AivisSpeech/AivisHub.
