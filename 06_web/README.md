# 06_web — the tanuki avatar, self-contained

Everything the avatar needs is in this folder: the model, its textures, the
JavaScript, the Japanese lip-sync pipeline and a voice server. Copy the whole
folder into a project and it works.

This file is about *using* it. For how it was built and why —
[`../TEACH.md`](../TEACH.md) is the full walkthrough, [`../GUIDE.md`](../GUIDE.md)
the short reference.

## Run it

```bash
pip install edge-tts pykakasi      # both optional, both recommended
python tanuki_tts_server.py
```

Open **http://localhost:8080** — that's the chatbot. Type Japanese, press Send,
the tanuki says it.

| page | what it is |
|---|---|
| `chatbot.html` | the chat avatar — this is the one you want |
| `minimal.html` | 60 lines: load, click, speak. Read this to understand the API |
| `player.html` | tuning bench: orbit, sharpen slider, microphone, viseme meters |
| `selftest.html` | **timing guardrail** — open it and press Run when something feels off |

## What's in here

```
chatbot.html          the chat UI
minimal.html          the smallest working example
player.html           tuning bench
model/                tanuki.gltf + .bin + 3 WebP textures (8 morph targets)
src/
  tanuki-lipsync.js   the driver: loads the model, plays audio, moves the mouth
  speech-queue.js     sentence-by-sentence playback — the latency fix
  body.js             breathing, weight shift, nod while speaking
  bands.js            three-band audio energy — what the body moves to
  quality.js          anisotropy + contrast-adaptive sharpening
  formants.js         browser-side vowel detection, for audio with no script
  react.jsx           <Tanuki ref={...} /> for React Three Fiber
lib/                  Japanese text → viseme timing (used by the server)
tanuki_tts_server.py  serves this folder and provides /api/say
```

## Wiring it to your bot

One function in `chatbot.html`, marked with a banner comment:

```js
async function askYourBot(userText) {
  return (await (await fetch('/api/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: userText }),
  })).json()).reply;
}
```

It ships echoing you back, so the page works before you have a backend. Return
kana or romaji; kanji needs `pykakasi` on the server.

## The integration, in five lines

```js
const tanuki = await TanukiLipSync.load('./model/tanuki.gltf', new GLTFLoader());
const rig = new THREE.Group(); rig.add(tanuki.object); scene.add(rig);
const body = new BodyMotion(rig);
renderer.setAnimationLoop(() => { const dt = clock.getDelta();
  tanuki.update(dt); body.update(dt, tanuki); composer.render(); });
await tanuki.speak({ audio, track });     // resolves when the line ends
```

`BodyMotion` drives a group **you** own, never the loaded scene, so it never
fights your own placement of the character.

## Getting audio + timing

```
POST /api/say  {"text": "こんにちは、たぬきです", "blink": true}

{ "engine": "edge", "kana": "…", "duration": 1.62,
  "audio": "/media/9f3c….mp3",
  "track": { "duration": 1.62, "fps": 30, "tracks": { "A": [[0.61, 1.0], …] } } }
```

Voice engines are tried in order — VOICEVOX on :50021, then edge-tts, then
gTTS, then an offline formant synth that needs nothing but numpy. The server
prints which one it picked. Force one with `--tts edge --voice ja-JP-NanamiNeural`.

On `--tts auto`, an engine that *throws* (no network, a 403 from the voice
service, a bad voice name) drops to the next one instead of failing the reply,
and the response says so:

```json
"fallback_from": { "from": "edge", "error": "RuntimeError: 403 …" }
```

An explicit `--tts` choice is never substituted — if you asked for that engine
you want its error, not a quiet downgrade.

**Voice defaults.** Every field is optional: `{"text": "…"}` is a complete
request. Omitting `voice` or `rate` gets the engine's own default rather than a
`None`, which is what used to reach edge-tts as `TypeError: voice must be str`.

The server measures the clip and fits the mouth to its real duration. Mora
timing alone is an estimate and drifts over a sentence.

## When something feels late or out of sync: run the self-test

Open **http://localhost:8080/selftest.html** and press Run. It drives the real
pipeline against your engine and measures what the ear and the eye actually
get, so "it feels laggy" becomes a number that says which part.

No 3D model is loaded, deliberately: that separates a pipeline problem from a
frame-rate one. It reports:

| it checks | it catches |
|---|---|
| engine turnaround for one sentence | the pause before speech being the engine, not the rig |
| timing source (`voicevox-exact` vs estimated) | whether the mouth is on ground truth or an inference |
| time from Send to the first syllable | the thing the user actually waits for |
| longest silence between sentences | a queue starving because synthesis can't keep ahead |
| queue stalls | the same, named explicitly |
| caption vs voice offset | text printed before the audio — the loudest "lag" that isn't one |
| mouth closes between sentences | the rig left frozen in the last shape it held |
| **the same, with cuts forced mid-word** | the above, deterministically rather than by luck |
| mouth shuts when the reply ends | a character sitting there with its mouth open |
| mouth keeps moving to the end of each sentence | a viseme track running out before its audio |
| every sentence was spoken | a failed chunk silently skipped |

Thresholds come from broadcast AV-sync practice: audio may lead video by ~45 ms
and lag it by ~125 ms before a viewer notices (ITU-R BT.1359); film mixing works
to about ±22 ms.

The mouth checks are written to fail. Removing the one line that resets the rig
at the end of a chunk takes the stress check from `0.23 open` to `0.82 open` —
verified, because a guardrail that cannot fail is decoration.

## Which voice engine to use

All four are free. They are not equally good, and the differences matter more
than the voice quality:

| | cost | where it runs | deploys as | lip-sync timing |
|---|---|---|---|---|
| **VOICEVOX** | free | your machine / your server | Docker image | **exact — from the engine** |
| edge-tts | free | Microsoft's servers | can't | estimated, then aligned |
| gTTS | free | Google's servers | can't | estimated, then aligned |
| offline | free | in-process | anywhere | estimated, then aligned |

**Use VOICEVOX.** Three reasons, in order of how much they matter:

1. **It tells you the timing.** `/audio_query` returns the exact plan it is
   about to synthesise — every mora, its consonant and vowel, and how long each
   will last. The mouth is then driven by the same numbers that generated the
   sound, instead of a uniform-beat estimate warped onto the audio afterwards.
   It even marks devoiced vowels in upper case (the /u/ of です comes back as
   `U`), which is a distinction the text-only path has to infer.
2. **No network round trip**, so it is the fastest of the four by a wide margin
   and the latency does not depend on anyone else's servers.
3. **It is deployable.** edge-tts and gTTS talk to endpoints that are not
   public APIs — fine on your laptop, not something to build a product on.
   VOICEVOX ships an engine you run yourself:

   ```bash
   docker run --rm -p 50021:50021 voicevox/voicevox_engine:cpu-latest
   ```

   The server finds it on `:50021` automatically — nothing to configure. Set
   `VOICEVOX_URL` to point elsewhere. Scaling is ordinary container scaling.

When VOICEVOX answers, the response says `"timing": "voicevox-exact"` and skips
the alignment pass entirely. The durations are checked against the audio that
actually came out first; if they disagree by more than 20% the server logs it
and falls back to the estimating path, so a version change can never silently
desync the mouth.

One licence note: VOICEVOX is free for commercial and non-commercial use, but
each voice requires **credit** in the form `VOICEVOX:キャラクター名`, and some
characters carry extra conditions. Check the terms for the specific speaker id
you ship.

## Latency — why it starts talking sooner now

The obvious way to speak a reply is one request for the whole thing. That makes
the user wait for the entire answer to be synthesised before hearing the first
syllable, and TTS cost scales with length, so a long reply is punished twice.

`SpeechQueue` splits the reply at sentence boundaries, synthesises the first
one alone, and starts playing it while the rest are still being made:

```
one shot   [------- synthesise whole reply -------][play ...]
queued     [synth 1][play 1.............][play 2.......][play 3...]
                    [synth 2][synth 3]   (overlapped, ahead of playback)
```

Measured in a real browser against this server, with synthesis modelled on
edge-tts (0.25 s handshake + 30 ms/character), on a four-sentence reply:

| | time to first sound | total |
|---|---|---|
| one request for the whole reply | 2.74 s | 8.96 s |
| queued by sentence | **0.76 s** | **7.36 s** |
| repeat (server response cache) | 0.06 s | — |

It also **finishes sooner**, because the server already measures where the real
speech starts and ends in each clip, so the queue seeks past the leading
padding and cuts at the trailing one — two unpredictable silences replaced by
one controlled `gap`.

The **first** chunk is cut short (18 characters, and allowed to break at a
comma) because it is the only one anyone waits for. Later chunks are longer:
they are already being synthesised behind the one playing, so length costs
nothing there, and more text gives the engine better intonation.

### Reveal the text with the voice, not before it

The biggest *felt* delay is not always a real one. Printing the whole reply the
instant it arrives and then pausing before the voice catches up makes the eye
finish reading before the mouth has started — which reads as the avatar being
slow even when it is not. `chatbot.html` reveals each sentence as it begins
being spoken:

```js
speech.onChunk = (chunk) => { bubble.textContent += chunk; };
await speech.say(reply);
```

A sentence whose audio failed is still revealed, so words go missing from the
sound and never from the conversation.

```js
import { SpeechQueue } from './src/speech-queue.js';
const speech = new SpeechQueue(tanuki, { api: '/api/say' });

await speech.say(reply);       // split, pipeline, play in order
speech.cancel();               // new user message: drop everything in flight
```

**If your bot streams**, this is the version you want — each sentence is
synthesised the moment the model finishes writing it, so TTS overlaps
generation instead of following it:

```js
for await (const delta of streamFromYourBot(userText)) speech.feed(delta);
await speech.end();
```

Options: `lookahead` (default 2 chunks in flight), `gap` (0.12 s between
sentences), `maxChars` (60, before falling back to splitting at 、),
`timeout` (20 s per chunk), `trimPadding`, `onChunk`, `onError`. A chunk that
fails is skipped and reported — one bad sentence never silences the rest.

### Server-side cost per request

| | before | after |
|---|---|---|
| process spawns | 3 (ffprobe + ffmpeg ×2, with temp files) | 1 (ffmpeg, streamed to stdout) |
| non-TTS overhead | 207 ms | 101 ms |
| a repeated line | 186 ms | ~0 ms (`"cached": true`) |

The same clip used to be decoded three times — once for its duration, once for
the silence trim, once for the alignment envelope. It is decoded once now and
the frames are shared. The full response, not just the audio, is cached to
`.media/<key>.resp.json`, so repeats survive a restart.

## Prefer the text path

Japanese needs the lips to meet before /m/ /b/ /p/, and no vowel detector
recovers that from a waveform — the mouth is closed exactly when there is
nothing to hear. Use `speak({ audio, track })` whenever you know the script;
`speak({ audio })` falls back to live formant analysis, vowels only.

## Lip-sync timing

The track is fitted to the **speech inside the clip**, not to the file. Every
TTS engine pads its output with silence — typically 150–300 ms at the front and
more at the back. Fitting the mouth to the whole clip stretches it across that
silence: a 1.43 s phrase spread over a 2.0 s file runs 40% too slow, and the
error accumulates, so the mouth ends up visibly behind. Measured on a padded
clip, that was a **700 ms lag by the end of a sentence**.

The server detects the speech span by energy and fits the track to it, then
shifts it so the mouth stays shut through the leading silence. Same clip after
the fix: +30 ms, and correlation with the audio envelope went 0.11 → 0.61.
`/api/say` returns the span it found as `"speech": [start, end]`.

### The timing comes from the recording, not from a model

The mora model gives every mora the same beat. Real speech does not: TTS
engines stretch phrase-final morae, compress unstressed ones, and pause at
commas for as long as they feel like. Fitting a uniform track to the clip's
duration only corrects the *average* — the mouth still drifts inside the
sentence and snaps back at the end.

So the track is warped onto the audio's own rhythm. Both signals describe the
same thing in different units: the track predicts how open the mouth should be,
the recording's energy envelope shows how open it actually was. Dynamic time
warping finds the monotonic mapping between them and retimes the keyframes
along it.

No model, no calibration, no per-voice tuning — it adapts to each utterance.
On a deliberately mis-timed clip (first half hurried, second half dragged),
correlation with the envelope went **0.02 → 0.45** and the best-match offset
from **−130 ms to −10 ms**.

The DTW is constrained to a Sakoe-Chiba band. Unconstrained, it will happily
map a whole phrase onto one loud syllable — a perfect score and a useless
result. And if the warp does not improve the correlation it is discarded: a bad
alignment is worse than uniform timing.

`/api/say` reports what it did as `"align": {"aligned": true, "before": …,
"after": …}`. Turn it off with `{"align": false}`.

### Check it on your own voice

```bash
python check_sync.py --tts edge --voice ja-JP-NanamiNeural
```

Synthesises several phrases, prints correlation before and after alignment, and
the residual lag in milliseconds. Anything inside ±45 ms is below the threshold
most people can see.

One caveat on reading it: the **offline** engine scores high in the "uniform"
column and gains little, because its audio was generated from the same mora
model the track assumes — it agrees with itself. Run it against edge-tts or
VOICEVOX for numbers that mean something.

#### Measured baseline, real voice

Recorded so a later regression is visible. Correlation with the audio envelope,
uniform mora timing vs. after alignment:

| phrase | uniform | aligned | gain | contains |
|---|---|---|---|---|
| しゃべってみましょう、いっしょに | 0.532 | 0.854 | +0.322 | comma, sokuon |
| こんにちは、たぬきです | 0.639 | 0.914 | +0.275 | comma |
| がんばってください | 0.657 | 0.904 | +0.247 | sokuon |
| ありがとうございます | 0.814 | 0.924 | +0.110 | — |
| きょうはいいてんきですね | 0.789 | 0.808 | +0.019 | — |
| **mean** | **0.686** | **0.881** | **+0.194** | |

Residual lag was 0 to −10 ms on every phrase — an order of magnitude inside the
±45 ms visibility threshold, and on the early side.

The gains sort cleanly by what the phrase contains. The two biggest are the
ones with a **comma**, where the engine chooses its own pause length and the
uniform model cannot know it. Next is the **sokuon** っ, a beat of silence whose
real length varies. The phrase with neither was already well aligned and gained
almost nothing — which is the result you want: the alignment does work exactly
where the model is blind, and leaves the rest alone.

### Output latency is measured, not guessed

`audio.currentTime` reports the **decoder** position. The sound still has to
cross the output buffer and the hardware before anyone hears it, so driving the
mouth straight off `currentTime` always renders it late. That delay is about
10 ms on wired output and can exceed 150 ms on Bluetooth — far too variable for
a constant.

The Web Audio API measures it: `AudioContext.outputLatency`. The rig reads it
before every line (it changes if the user switches to Bluetooth mid-session)
and shifts the track by that much automatically. No configuration.

```js
await tanuki.measureLatency();   // called for you inside speak()
tanuki.measuredLatency           // seconds, whatever this device reports
tanuki.timeShift()               // latency + lead + your trim
```

Where `outputLatency` is unimplemented it reports 0, so the rig falls back to
`baseLatency + 20 ms`, then to 40 ms. Assuming zero would be the one value that
is never right.

### And a deliberate 30 ms lead

On top of the measured latency the mouth runs 30 ms early, for two reasons that
point the same way:

- **Real speech is anticipatory.** The lips start forming a vowel during the
  consonant before it. A mouth that moves exactly on the sound already reads as
  a beat behind.
- **The perceptual tolerance is asymmetric.** ITU-R BT.1359 puts the
  detectability threshold at **45 ms of audio leading video against 125 ms of
  audio lagging it**; ATSC allows 15 ms lead and 45 ms lag. Erring early is
  roughly three times safer than erring late.

Adjust with `tanuki.lead` if you disagree. The **trim** slider in the tuning
bench is a fine adjustment on top of both and should normally stay at zero —
it is there to diagnose, not to configure.

Pass `{"trim": false}` to `/api/say` if your engine already returns tightly
trimmed audio.

## Things that will bite you

**Three meshes, not one.** The model has three primitives (face, cavity,
tongue), so three.js builds three meshes, each with its own copy of the morph
targets. Drive only the first and the mouth opens while the tongue stays put.
`TanukiLipSync` binds all of them.

**`createMediaElementSource` is once per element, ever.** A second call on the
same `<audio>` throws. Reuse one element for the whole session.

**Reused `<audio>` elements park at the end.** `speak()` rewinds; if you drive
playback yourself, rewind or the track samples past its last key.

**EffectComposer needs an `OutputPass`.** It renders to a linear target, so
without one tone mapping and sRGB conversion stop happening and the image comes
out washed and orange. The final pass must also write opaque alpha, or the
canvas is transparent and nothing draws at all.

**ES modules need a server.** `file://` won't load the modules or the model.

**`speak()` resolves on `ended`, with a safety net.** That event is not
guaranteed — a stalled buffer, a decode error, or a device with no audio output
all leave it unfired. Without a fallback the promise never settles and a chat
UI's send button stays disabled forever. There is a timer capped at the clip
length plus two seconds.

**`update()` clears every channel each frame.** Anything not re-driven settles
to zero, so `setViseme()` is washed out on the next tick. To hold a value, use
`setOverride('Blink', 1)` and `setOverride('Blink', null)` to release.

## What moves the body

The mouth is driven by the phoneme track. The **body is driven by the audio
spectrum**, split into three bands (`src/bands.js`):

| band | Hz | what it is | what it moves |
|---|---|---|---|
| low | 70–260 | the voiced fundamental | torso engagement, breath depth |
| mid | 260–2200 | F1/F2, i.e. perceived loudness | lean and bob |
| high → `hit` | 2600–7000 | frication and plosive bursts | head accents |

`hit` is the **rise** of the high band, not its level — a consonant landing is
an event, so it fires an impulse that decays over ~0.2 s. That is why nods now
fall on the plosives instead of on a fixed sine.

Each band carries a running peak that rises instantly and decays ~6 dB/s, so
the level of the recording stops mattering: a quiet edge-tts clip and a loud
VOICEVOX one both drive the body the same way.

There is no lead applied to the bands, while the mouth is read `timeShift()`
early — so the body trails the mouth by ~30–40 ms. That is the right way
round: lips anticipate a sound, torsos do not.

**The fallback.** With no audio graph — an external clock, a refused
`AudioContext`, a muted tab — `BandAnalyser.synth()` manufactures bands from
mouth openness instead, which is what the body used to run on entirely. Blunter
(it makes the body a function of *which vowel* is being said, so the character
leans on あ and freezes on い) but it keeps the motion in character rather than
stopping dead.

Turn it off to compare:

```js
body.bandDrive = false;         // one scalar, the old behaviour
rig.useBands   = false;         // don't even read the spectrum
```

`player.html` has a **band drive** checkbox and three extra meters (low / mid /
hit) so you can watch it and switch mid-sentence.

## Moving the mouth

Not here — it's geometry. Edit `MOUTH` in `../02_scripts/visemes.py`, preview
with `tune_mouth.py`, rebuild with `build_model.py`, then copy the new
`07_web_model/*` into `model/`. See `../GUIDE.md`.
