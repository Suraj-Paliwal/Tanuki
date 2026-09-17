# Validation — 2026-09-17

- Five Python tests passed: reading extraction, stereo audio resampling, silence/mouth closure and bounded weights, discovered voice IDs and caching, validation and explicit engine failure.
- JavaScript syntax check passed.
- PowerShell launchers parsed successfully; `stop.ps1` and `start.ps1 -NoBrowser` were exercised successfully, and the restarted server reported the engine ready with 10 styles.
- Actual AivisSpeech Engine **1.2.0** installed and run locally. Discovered **10 styles** across **まお** and **コハク**.
- Real greeting with まお / ノーマル (style `888753760`): generated a **4.5537 s** WAV and matching mouth track. First tested request completed in **4.7 s** on this computer, after the engine's first-run downloads finished.
- For that greeting, the alignment helper's mouth-opening/audio-envelope correlation rose from **0.278** to **0.766**. This is an internal rhythm diagnostic, not a phoneme-accuracy or perceptual lip-sync score.
- Tested コハク / ノーマル at 0.5×: generated and played a **7.14 s** line containing kanji.
- Browser verified model rendering, connected voice dropdown, speech generation, playback completion, replay, and Stop. During replay, visible vowel meters reached **99.99%** and the rendered mouth opened; Stop returned the player to its ready state. No browser warnings/errors were reported during the check.

The lip shapes and timing remain estimates. No forced phoneme alignment, listening panel, hardware audio/video measurement, or frame-accurate perceptual accuracy claim is made.
