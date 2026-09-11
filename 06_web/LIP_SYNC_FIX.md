# Japanese lip-sync correction

This copy fixes reproducible mouth-shape problems in the Japanese avatar.
The model and textures are the original assets. The changes are in speech
planning, audio decoding, and browser animation.

## What was wrong

- Old vowel shapes faded out more slowly than new ones appeared. During a
  transition, their combined weight reached **1.3257**. This extrapolated
  beyond the intended mouth geometry. The corrected blend stays at or below 1.
- Each Japanese mora had one isolated peak. The mouth spent most of its time
  between vowel poses. Vowels now hold their pose between short transitions.
- A text heuristic reduced some I/U shapes to 0.55. On this model, reducing U
  also widens it toward the resting smile. Estimated tracks no longer guess
  this reduction. Engine-marked devoiced vowels retain 0.90 of their pose.
- The exact timing path did not hold the lips closed for the full m/b/p
  consonant. Closures and silent padding now remain closed.
- Small-vowel combinations such as ファ and ティ were counted as two morae.
  They now form one mora. Existing Japanese is preserved around romaji text.
- MP3 analysis silently failed when ffmpeg was not on PATH. The decoder can
  now use an already-installed imageio-ffmpeg binary, or FFMPEG_BINARY.
- Cached responses could preserve old mouth tracks after a code update.
  A track-version cache key now rebuilds them while reusing natural-voice audio.

## Playback timing

Automatic extra output-latency correction is disabled by default. The browser
uses the media element's playback position with a 30 ms lead, plus any manual
trim. An unrelated AudioContext's latency is not automatically added to this
clock. An integration using a processing clock can opt in to a subtractive
output-delay correction. See the corrected README section for details.

## Validation performed

- **19 Python tests and 8 JavaScript tests passed.** They cover Japanese
  vowel holds, long vowels, small kana, closures, silent padding, cache changes,
  real MP3 decoding, blend limits, and playback-clock options.
- All seven saved natural Japanese Edge voice clips were decoded and given
  fresh tracks. Each produced more frames with a distinct vowel pose than its
  old track. All tracks stayed within the blend limit and ended closed.
  This checks articulation clarity; it is not a phoneme-accuracy score.
- A headless Chrome playback test played one saved natural Japanese clip,
  followed by three generated Japanese sentences through the real queue.
  Audio advanced, all three captions appeared, there were no playback errors,
  and the mouth returned to rest. Maximum combined mouth weight was 1.0.
- An asset audit found matching vowel labels across face, mouth cavity, and
  tongue. The shared mouth rim remained joined, and blinking did not move it.

The full 3D visual check could not run in this task: access to the page's
external Three.js CDN was blocked. The browser playback test used local
modules and a small mock mesh. Please compare the corrected character on your
own browser using the phrases below. Live natural-voice synthesis was not
available here; the test used saved natural recordings and the offline voice.

## Try it

Run START_TANUKI.cmd in the parent folder. Open http://127.0.0.1:8092/player.html
after the server prints its address. The existing voice-engine discovery is
preserved; with no natural voice engine available it uses the robotic fallback.

Use these phrases to inspect the five vowels, lip closures, and contracted
sounds separately:

1. あいうえお。あー、いー、うー、えー、おー。
2. まみむめも。ぱぴぷぺぽ。ばびぶべぼ。
3. きゃ、きゅ、きょ。ファ、フィ、フェ、フォ。
4. こんにちは。きょうもいいてんきですね。

The default tuning is for Japanese only. The five-vowel model still cannot
show every Japanese tongue/consonant articulation independently. Estimated
timing from a voice without phoneme durations is approximate, particularly for
long sentences and ambiguous readings. The current ん/っ closures are a simple
visual approximation. This update does not connect the echo demo to an AI bot.

To run the regression tests from 06_web:

```text
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/driver.test.mjs
```

Python needs numpy. Natural Japanese text-to-speech and kanji conversion use
the same optional packages as the original project (edge-tts, pykakasi), or a
running local compatible voice engine. MP3 decoding needs ffmpeg or
imageio-ffmpeg. No packages were installed as part of this fix.
