# Tanuki Japanese lip-sync rig

Turns `tanu_base.glb` into a model whose mouth can be driven by Japanese
speech, and gives you two ways to drive it: from text, or from a recording.

## What was in the source file

One mesh, 328,708 vertices / 547,934 triangles, a single PBR material with
three 2048×2048 JPEG maps. No armature, no shape keys, no animation. Head,
hat, ears and body are fused into one continuous surface, and the UV atlas is
auto-generated and fragmented across dozens of small islands.

The mouth was **painted, not modelled** — a thin dark curve on a sealed
surface with only a faint crease in the geometry. There was no mouth opening,
no interior, no teeth or tongue, and no edge loops around the lips.

## What the rig adds

* the mouth cut open, with the ragged cut edge relaxed
* an interior cavity extruded inward from the cut rim, plus a tongue
* a **closed** base pose: the rim is collapsed onto the lip line, so the
  neutral model still reads as the original smile
* eight morph targets:
  * `A` `I` `U` `E` `O` — the standard Japanese vowel set, the same one VRM uses
  * `Blink` `BlinkL` `BlinkR` — both eyes, or one at a time for a wink

Everything blends from the closed base, which is what glTF morph targets need.

### How the blink works, given there are no eyelids

The eyes are near-flat domes with the iris, pupil and highlight painted
straight onto them — there is no lid geometry to rotate down. So each eye
collapses vertically onto a line instead. Because the iris is painted on the
surface, squashing the surface squashes the painted eye with it, which is
exactly how a cartoon blink reads.

Two details matter. The collapse line sits just above the eye centre so it
looks like an upper lid coming down rather than the eye imploding; and it sits
*near* centre rather than high, because the surface collapses onto that line,
so running it through the dark iris gives a dark closed eye instead of a bright
sliver of sclera.

The eye keys are built from the sealed base, not the raw mesh. A shape key
stores absolute positions, so a blink built on the open-mouthed original would
drag the mouth back open every time it was blended in.

## Files

| file | what it is |
|---|---|
| `tanuki_visemes.glb` | the rigged model, 8 morph targets, no animation |
| `tanuki_visemes.blend` | the same rig as a Blender file |
| `jp_kana.py` | Japanese text → mora sequence |
| `jp_lipsync.py` | moras → viseme keyframes |
| `audio_lipsync.py` | audio → viseme keyframes, by formant analysis |
| `jp_synth.py` | a small formant synthesiser, for testing the audio path |
| `eyes.py` | the blink morph targets |
| `apply_tracks.py` | writes a track onto Blender shape keys |
| `lipsync.py` | command line front end |

## Using it

```bash
python lipsync.py --text "こんにちは、たぬきです" --out track.json
python lipsync.py --text "ありがとう" --total 1.2 --out track.json
python lipsync.py --audio voice.wav --out track.json
python lipsync.py --text "こんにちは" --preview        # see the timeline
python lipsync.py --text "こんにちは" --blink --out track.json
```

`--blink` adds an idle `Blink` track: fast down, short hold, slower opening,
with randomised spacing. Symmetric timing reads as a twitch, and perfectly
regular spacing is one of the clearest tells that something is animated rather
than alive.

Romaji works too (`--text "arigatou gozaimasu"`). Kanji does not — convert to
kana first.

Output is a JSON track:

```json
{"duration": 1.5, "fps": 30, "visemes": ["A","I","U","E","O"],
 "tracks": {"A": [[0.0, 0.0], [0.61, 1.0], ...], "I": [...],
            "Blink": [[0.35, 0.0], [0.41, 1.0], [0.44, 1.0], [0.51, 0.0]]}}
```

Each entry is `[time_seconds, weight]`. Feed the weights straight into the
morph target of the same name and interpolate linearly between keys.

## How the text path decides timing

Japanese is mora-timed: every mora takes roughly the same beat, so one
duration per mora is a much better first approximation here than it would be
for a stress-timed language. On top of that:

* a youon pair (きゃ) is **one** mora, not two — treating it as two makes the
  mouth flap on a single beat
* `っ` (sokuon) and `ん` (hatsuon) are beats that carry no vowel, so they hold
  the mouth closed
* `ー` holds the previous vowel instead of starting a new attack
* before `ま` `ば` `ぱ` rows the lips are closed first — /m/ /b/ /p/ are
  bilabial and the mouth physically has to meet
* `い` and `う` between voiceless consonants are devoiced in standard Japanese
  (です → "des"), so they open the mouth less

## How the audio path works

No forced aligner and no model download. The five Japanese vowels are well
separated in formant space, so each 25 ms frame gets LPC formant estimation,
and F1/F2 pick the nearest vowel.

Two things it needs to get right:

* **LPC order.** At order 12 the two low, close formants of /o/ (~500 and
  ~900 Hz) merge into one pole and the estimator reports F3 as F2 — every /o/
  then classifies as something else. Order ≈ sr/1000 + 4 keeps them apart.
* **Partial speaker adaptation.** Dividing by the utterance's own median
  formants adapts to a high or low voice, but the median depends on which
  vowels happen to occur, so a phrase heavy in /a/ drags every other vowel out
  of place. The exponent is 0.35, not 1.0.

Round-trip check: synthesise こんにちは、たぬきです with `jp_synth.py`, run it
back through `audio_lipsync.py`, and all eleven vowels come back in order.

## Known limits

* Kanji is not handled; give it kana or romaji.
* The audio path classifies vowels only. It does not detect consonants, so it
  will not close the lips for /m/ /b/ /p/ the way the text path does. For a
  recorded line where you also know the script, generate from text and fit it
  with `--total`.
* The mesh is 548k triangles. For realtime use, decimate — but decimate
  *before* rebuilding the rig, since the morph targets are per-vertex.
