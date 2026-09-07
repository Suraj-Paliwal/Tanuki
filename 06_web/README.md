# 06_web — the tanuki avatar, self-contained

Everything the avatar needs is in this folder: the model, its textures, the
JavaScript, the Japanese lip-sync pipeline and a voice server. Copy the whole
folder into a project and it works.

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

## What's in here

```
chatbot.html          the chat UI
minimal.html          the smallest working example
player.html           tuning bench
model/                tanuki.gltf + .bin + 3 WebP textures (8 morph targets)
src/
  tanuki-lipsync.js   the driver: loads the model, plays audio, moves the mouth
  body.js             breathing, weight shift, nod while speaking
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
gTTS, then an offline formant synth that always works. The server prints which
one it picked. Force one with `--tts edge --voice ja-JP-NanamiNeural`.

The server measures the clip and fits the mouth to its real duration. Mora
timing alone is an estimate and drifts over a sentence.

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

**`update()` clears every channel each frame.** Anything not re-driven settles
to zero, so `setViseme()` is washed out on the next tick. To hold a value, use
`setOverride('Blink', 1)` and `setOverride('Blink', null)` to release.

## Moving the mouth

Not here — it's geometry. Edit `MOUTH` in `../02_scripts/visemes.py`, preview
with `tune_mouth.py`, rebuild with `build_model.py`, then copy the new
`07_web_model/*` into `model/`. See `../GUIDE.md`.
