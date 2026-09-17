# Validation — 2026-09-17

- Five Python tests passed: reading extraction, stereo audio resampling, silence/mouth closure and bounded weights, discovered voice IDs and caching, validation and explicit engine failure.
- JavaScript syntax check passed.
- PowerShell launchers parsed successfully; `stop.ps1` and `start.ps1 -NoBrowser` were exercised successfully, and the restarted server reported the engine ready with 10 styles.
- Actual AivisSpeech Engine **1.2.0** installed and run locally. Discovered **10 styles** across **まお** and **コハク**.
- Real greeting with まお / ノーマル (style `888753760`): generated a **4.5537 s** WAV and matching mouth track. First tested request completed in **4.7 s** on this computer, after the engine's first-run downloads finished.
- For that greeting, the alignment helper's mouth-opening/audio-envelope correlation rose from **0.278** to **0.766**. This is an internal rhythm diagnostic, not a phoneme-accuracy or perceptual lip-sync score.
- Tested コハク / ノーマル at 0.5×: generated and played a **7.14 s** line containing kanji.
- Browser verified model rendering, connected voice dropdown, speech generation, playback completion, replay, and Stop. During replay, visible vowel meters reached **99.99%** and the rendered mouth opened; Stop returned the player to its ready state. No browser warnings/errors were reported during the check.

## Reminiscence preset verification

- The configured default is **まお / おちつき** (Mao / Calm, style `888753763`) at **0.90×** speed.
- A real `/api/say` request omitting `voice` and `speed` resolved to that style and pace and generated a **7.374 s** clip. The response's duration matched the track duration, and every mouth channel ended at zero.
- The saved result is in `demo/reminiscence.wav` and `demo/reminiscence.json`.
- After refresh, the browser showed Mao / Calm selected, speed 0.90× and Speak enabled.

## Reproduce the checks

Follow [run.md](run.md) to start the engine and viewer. The connection checks and browser playback checklist are in section 7; engine-independent tests are in section 10. API details and the meaning of the timing diagnostics are in [ARCHITECTURE.md](ARCHITECTURE.md).

The lip shapes and timing remain estimates. No forced phoneme alignment, listening panel, hardware audio/video measurement, or frame-accurate perceptual accuracy claim is made.
