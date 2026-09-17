# TEACH.md — how a static 3D model was turned into one that speaks Japanese

This is the long version: the whole process, in the order it happened, with the
reasoning shown. Read it if you want to **do this again** — on this tanuki, on
another character, or in another language.

Three documents, three jobs:

| file | what it is for |
|---|---|
| `06_web/README.md` | using what exists. API, endpoints, wiring it to a bot. |
| `GUIDE.md` | the decisions, compressed. A reference to skim when changing something. |
| **`TEACH.md`** (this) | the method. Why each step exists, how to verify it, what to do when it fights back. |

---

## Contents

| § | |
|---|---|
| 0 | [The problem, stated precisely](#0--the-problem-stated-precisely) |
| 1 | [The shape of the whole system](#1--the-shape-of-the-whole-system) |
| 2 | [Measure before you model](#2--measure-before-you-model) |
| 3 | [Mesh surgery](#3--mesh-surgery) |
| 4 | [Morph targets](#4--morph-targets) |
| 5 | [Editing the texture](#5--editing-the-texture) |
| 6 | [Export, and the glTF details that matter](#6--export-and-the-gltf-details-that-matter) |
| 7 | [Japanese text becomes timing](#7--japanese-text-becomes-timing) |
| 8 | [Stop guessing the timing: take it from the audio](#8--stop-guessing-the-timing-take-it-from-the-audio) |
| 9 | [The runtime driver](#9--the-runtime-driver) |
| 10 | [The body, and why one number was not enough](#10--the-body-and-why-one-number-was-not-enough) |
| 11 | [Making it look sharp](#11--making-it-look-sharp) |
| 12 | [The server, and wiring it to your bot](#12--the-server-and-wiring-it-to-your-bot) |
| 12b | [Latency, and why "make it faster" started with a stopwatch](#12b--latency-and-why-make-it-faster-started-with-a-stopwatch) |
| 13 | [How to check your own work](#13--how-to-check-your-own-work) |
| 14 | [Recipes](#14--recipes) |
| 15 | [Glossary](#15--glossary) |
| 16 | [Where the limits are](#16--where-the-limits-are) |
| 17 | [What cost me the most time](#17--what-cost-me-the-most-time) |

---

## 0 · The problem, stated precisely

You had `tanu_base.glb`: an AI-generated tanuki. One mesh, one material, three
textures. **No bones, no blend shapes, no landmarks, no naming.** Nothing in the
file says where the mouth is. There is not even a mouth — there is a *smile
painted onto the texture* and a shallow groove sculpted under it.

The goal: it should look like it is saying Japanese words, in sync with audio.

That splits into five questions, and every one of them has to be answered
before the next means anything:

1. **Where is the mouth?** Nothing labels it. → measurement (§2)
2. **How does a face with no mouth get one?** → mesh surgery (§3)
3. **How does a mouth shape become something a browser can blend?** → morph
   targets (§4)
4. **Which shape, at which moment?** → Japanese phonetics and timing (§7, §8)
5. **How do you know it is actually in sync?** → measurement again (§8, §13)

The recurring theme, and the single most useful habit in the whole project:
**when you can measure it, do not argue about it.** Nearly every hour I lost
was to reasoning about something I could have rendered, plotted or counted in
five minutes.

---

## 1 · The shape of the whole system

```
     OFFLINE  (Python + Blender, run once)          RUNTIME  (JavaScript, per line)

     tanu_base.glb                                   text
          │                                            │
          ▼                                            ▼
     02_scripts/build_model.py                    TTS engine ──► audio file
          │  weld → relax → cut → rim →                │
          │  cavity → tongue → shape keys              ▼
          ▼                                    06_web/lib/  text → morae → track
     07_web_model/tanuki.gltf                          │
     (8 morph targets: A I U E O                       ▼
      Blink BlinkL BlinkR)                     align.py: warp track onto audio
          │                                            │
          └──────────► 06_web/model/ ◄─────────────────┘
                             │                         │
                             ▼                         ▼
                    src/tanuki-lipsync.js  ◄──── track JSON + audio
                             │
                       morph weights, 60×/second
```

The two halves never talk directly. They meet at one flat data structure — the
**track**:

```json
{ "duration": 2.31,
  "tracks": { "A": [[0.00,0.0],[0.61,1.0],[0.74,0.0]],
              "I": [[0.00,0.0],[0.74,0.32]],
              "Blink": [[1.90,0.0],[1.96,1.0],[2.04,0.0]] } }
```

Time in seconds, weight 0–1, linearly interpolated between keys. That is the
entire contract. Anything that can produce this — a different language, a
phoneme aligner, a hand-animated timeline — drives the model. Keep that
boundary clean and you can replace either half without touching the other.

---

## 2 · Measure before you model

### The situation

Open the file and you have a vertex soup in some arbitrary coordinate frame.
You cannot cut a mouth until you know where the mouth *is*, to within a couple
of millimetres, in that frame.

### The method: render, overlay, compare

The mouth line is a curve. Model it as a parabola in the model's own units:

```
z = cz + curv · (x − cx)²
```

Four numbers: `cx` horizontal centre, `cz` the lowest point, `curv` how much
the corners ride up, `hw` the half-width. Now the question "where is the mouth"
becomes "what are those four numbers", which is a question you can *answer by
looking*:

1. Pick candidate values.
2. Draw the curve onto a copy of the texture in a bright colour.
3. Render the head from a fixed, calibrated camera.
4. Look at whether the line sits on the painted smile.
5. Adjust, repeat.

Three rounds settled it. `02_scripts/mouthfind.py` and `tune_mouth.py` are that
loop; `03_visemes/mouth_tuner_example.png` is what one round looks like.

### Why not fit it numerically

I tried, four times, and it kept failing. Every brightness-based search locks
onto the eye patches and the underside of the nose, which are darker than the
smile and much larger. A statistical fit on a texture with no ground truth is a
guess dressed up as a measurement.

> **The transferable lesson.** A calibrated overlay settles in one image what
> statistics argue about for an hour. If a quantity is visible, look at it.

The eyes were found the same way — cluster the bright desaturated sclera
texels into two groups, fit an ellipse to each, then check by overlay. The
answer came out asymmetric:

```python
EYES = {"L": dict(cx=-0.229, cz=0.519, rx=0.077, rz=0.087),
        "R": dict(cx= 0.157, cz=0.519, rx=0.080, rz=0.086)}
```

Left at −0.229, right at +0.157. That is not measurement error — **the model is
genuinely asymmetric**, as generated models often are. Know that before you
"correct" it and make both eyes wrong.

### Two curves, not one

This detail costs nothing to get right at the start and is painful later:

```python
FIT   = dict(cx=-0.025, cz=0.3038, curv=2.90, hw=0.135)   # the ORIGINAL smile
MOUTH = dict(cx=-0.036, cz=0.3038, curv=2.90, hw=0.132)   # the NEW mouth
```

`FIT` records where the painted smile actually is. It is a **measurement** and
never changes. `MOUTH` is where you decided to put the new mouth; it is a
**setting** and you will move it. Erasing reads `FIT`; cutting, morphing and
repainting read `MOUTH`.

Drive both from one curve and moving the mouth also moves the eraser — so the
old smile creeps back out from under the new one. (The original smile sat at
−0.025 while the muzzle centres on −0.032 and the nose on −0.041: the *model*
is off-centre, which is exactly why "centre the mouth" needed a second curve.)

---

## 3 · Mesh surgery

`02_scripts/cutmouth.py`. Seven steps, and the order is not negotiable.

### Step 1: weld. Everything depends on this.

Ask the source mesh how many boundary edges it has — edges belonging to exactly
one face, i.e. the border of a hole — and it answers **98,812**.

That number is a lie, and understanding why is the single most important piece
of 3D knowledge in this project.

To give one point on a surface two different UV coordinates (because a texture
seam runs through it), the format stores that point **twice**, at identical
coordinates, once per UV. These are *split vertices*. Geometrically the surface
is closed; topologically it is shredded into islands.

Consequences, both of which bit me:

- **Smoothing tears the model apart.** A Laplacian pass moves each vertex
  toward the average of its neighbours — but each twin only *has* neighbours on
  its own side of the seam. The twins get pulled in different directions, and
  every seam rips open. I ran this and produced a face covered in cracks, then
  spent an hour looking for a bug in my smoothing code. The code was fine.
- **Real defects hide among the fakes.** There was a crack beside the mouth I
  assumed my cut had made. It was in the source file all along, invisible
  among 98,812 false positives.

```python
weld_and_fill(ob, dist=1e-5)
# boundary edges  98,812 → 131
# duplicate verts 54,826 removed
# the real crack closes on its own
```

Per-loop UVs are untouched, so nothing about the texturing changes.

> If you ever must smooth *without* welding: group coincident vertices, average
> over the **combined** neighbourhood, and write the one result back to every
> twin. `relax_region()` does this. But weld if you can.

### Step 2: relax the old crease

The sculpted smile groove is about **0.27** wide. The hole for the visemes is
**0.14**. Cut the middle out and the outer thirds survive as two hard creases
either side of the new mouth — scars.

`flatten_crease()` relaxes that band back into the muzzle, tapering to zero at
the cut rim and at the corners, so no suspiciously flat patch appears where the
groove used to be.

### Step 3: cut

`cut()` deletes the faces inside the mouth envelope. One rule:

> **Restrict every boundary operation to the region you mean.**

My first cavity pass extruded *every* boundary edge in the mesh and produced
**307,628 faces**. The hat has its own open edges. So does the base. Any
operation phrased as "for each boundary edge" will find them. `_in_mouth()`
exists purely to say "these edges, not those".

### Step 4: straighten the rim

The mesh is triangle soup with no edge loops, so the cut edge comes out ragged.
`smooth_boundary(ob, iters=14, strength=0.7)` averages each rim vertex toward
its two rim neighbours only. The interior is not touched.

### Step 5: the mouth interior

Three attempts, and the failures are instructive:

1. **A small ball behind the hole.** Renders as a lit grey lump — you are
   looking at the *outside* of a sphere. Convex where it needed to be concave.
2. **A ball big enough to be concave from the front.** Pokes out through the
   chin.
3. **Extrude the hole's own rim inward.** ✅ Welded to the lips, so it can never
   separate from them and can never escape the head. And because ring 0 *is*
   the rim, when a viseme opens the lips the cavity opens with them, free.

The general form of that lesson: **derive the new geometry from the geometry it
must stay attached to**, rather than placing an independent object nearby and
hoping the two keep agreeing.

### Steps 6–7: tongue, then join

A small separate blob, joined into the main mesh *before* shape keys are added,
so every morph target carries it. Add it after and it stays behind while the
mouth moves.

---

## 4 · Morph targets

`02_scripts/geo.py`, `visemes.py`, `eyes.py`.

### What a morph target is

A morph target (blend shape, shape key) is a second copy of the vertex
positions. The renderer blends:

```
V_final = V_base + Σ  wᵢ · (V_targetᵢ − V_base)
```

with each weight `wᵢ` between 0 and 1. glTF stores the deltas sparsely, so a
target that moves 3,000 of 60,000 vertices costs 3,000 entries, not 60,000.
This is why a face rig with eight targets is cheap enough for a phone.

Everything below is about producing good `V_targetᵢ` arrays.

### The base pose is the mouth CLOSED

All targets blend *from the base mesh*. So the base has to be the neutral pose
you want to return to — a closed mouth. But the mesh you just cut has a hole in
it.

`sealed()` collapses the cut rim onto the lip line:

```python
WC_ENV = -0.006     # centre of the cut envelope
SEAL   = 0.018      # residual opening: 1.8% of the full height
def sealed(co):
    return displace(co, RX, RZ * SEAL, WC_ENV, purse=0.004)
```

That `purse=0.004` is worth a sentence. Lips that meet *exactly* let the dark
cavity show through as a hairline. Pushing them 4 mm forward makes them overlap
slightly, and the seam disappears.

**This base is now the reference for everything else you ever add.** Eye keys
are built from `base`, not from the raw mesh:

```python
base = sealed(co)
...
k.data.foreach_set("co", blink(base, sides).ravel())
```

Because a shape key stores **absolute positions**, a blink built on the
open-mouthed original silently drags the mouth back open every time it blends
in. I shipped that bug once: blinking reopened the mouth.

### Displacement, not rescaling

My first deformation rescaled local coordinates over the falloff region. It
tore the muzzle apart, and the reason is worth internalising:

> A **scale** moves a vertex by a fraction of *its own coordinate*. A vertex far
> from the origin therefore moves a long way. Over a wide falloff, distant
> vertices move much more than near ones — the opposite of what a falloff is
> for.

The working version computes each vertex's offset as the **difference between
two rim shapes** and attenuates it with distance. Bounded by a few millimetres
no matter how far the falloff reaches. If a deformation ever explodes at the
edges, check whether you multiplied a coordinate when you meant to add to it.

### One envelope, five visemes

```python
VISEMES = {                # rx     rz      wc     corner  purse  teeth  open
    "A": _v(0.066, 0.041, -0.009,  0.000,  0.000, 0.000, 1.00),
    "I": _v(0.098, 0.015,  0.001,  0.010, -0.008, 0.006, 0.32),
    "U": _v(0.036, 0.028, -0.003, -0.010,  0.018, 0.000, 0.48),
    "E": _v(0.082, 0.026, -0.003,  0.006,  0.000, 0.004, 0.58),
    "O": _v(0.049, 0.038, -0.007, -0.008,  0.018, 0.000, 0.74),
}
MAXR = dict(rx=0.070, rz=0.041)     # the size the hole is actually CUT at
```

Read those rows as phonetics. い is the widest and flattest (`rx` 0.098,
`rz` 0.015) — a slit. う is the narrowest, and protrudes (`purse` 0.018). あ is
the roundest and the only one at full jaw (`open` 1.00). お is small and pursed.
え sits between あ and い. That is the standard Japanese five-vowel system, and
it is why five targets are enough for this language when English needs a dozen.

The cut size (`MAXR`) is deliberately **between** the widest and narrowest
viseme, not at the widest. Cut at い's width and う has to contract its rim by
most of the mouth's half-width, which crumples the geometry into a wrinkle.
Sizing in the middle keeps every viseme within a few millimetres of the rim it
was cut from.

> Generalisable: when several poses share one piece of geometry, size that
> geometry for the **middle** of the range, not an extreme.

### Blink with no eyelids

There are no eyelids to rotate. The eyes are near-flat domes with the iris
painted on.

So don't rotate anything — **collapse the eye vertically onto a line**. Because
the iris is painted on the surface, squashing the surface squashes the eye. It
reads correctly.

```python
SLIT  = 0.032   # vertical extent surviving at full closure
LIDUP = 0.02    # the collapse line, above the eye centre
FLAT  = 0.014   # dome sinks back into the socket
DROP  = 0.007   # the whole lid area settles downward
```

`LIDUP` is the one that matters. The collapse line sits *just above* centre:
high enough to read as an upper lid coming down, low enough that the line lands
on the dark iris. Put it higher and you get a bright sliver of sclera, which
reads as a glint rather than a closed eye.

Three targets are exported — `Blink`, `BlinkL`, `BlinkR` — so you can wink.

---

## 5 · Editing the texture

The geometry is only half of a mouth. The other half is painted on, and the
old smile is still there.

### The atlas is unusable by hand

Auto-generated UVs, fragmented into dozens of small islands. There is no
"mouth" region in UV space to select and paint.

**The fix is to stop working in UV space.** `projpaint.py` rasterises every
triangle in UV space and records, for each texel, its **3D position on the
model**. Now you can paint as a function of *where the point is on the face*,
and island boundaries stop existing as a concept.

This trick — bake a texel→3D map, then treat the texture as a function of
position — is the general answer to "the UVs are a mess".

### Erasing the old smile without leaving a smear

Three things `erase_smile()` has to get right, each learned the hard way:

- **Fill from the same side of the lip line.** The muzzle is cream below and
  tan above. Pull replacement pixels from both sides and you smear one into
  the other, producing a grey band exactly where the mouth used to be.
- **Weight neighbours by distance, not a plain median.** Near the corners the
  source set thins out, and an unweighted median goes blocky. It produced a
  jagged flap beside the mouth that looked exactly like torn geometry — and I
  chased it as a mesh bug for three rounds before rendering the model in flat
  clay, seeing clean geometry, and realising the problem was in the texture.
- **Feather the band edge.** A hard swap leaves a visible seam where the
  erased region ends.

> **The debugging lesson.** When something looks wrong, first establish *which
> layer* it is in. A clay render (no textures) answers "geometry or texture?"
> in one image. I skipped that and lost hours.

### Painting a new smile back

A completely blank muzzle is most of why a closed face reads as artificial. So
draw a clean line along the *new* curve.

One counter-intuitive parameter: the fade must start at **88%** of the
half-width (`fade_lo=0.88`). Normally you would fade from halfway out. But the
middle of this line is where the hole is — the only part of it you ever see is
the outer segment near the corners. A fade starting halfway erases precisely
the visible part.

---

## 6 · Export, and the glTF details that matter

```python
bpy.ops.export_scene.gltf(filepath=OUT + "/tanuki",
                          export_format='GLTF_SEPARATE',
                          export_morph=True,
                          export_morph_normal=False,
                          export_animations=False)
```

- `GLTF_SEPARATE` writes `tanuki.gltf` + `tanuki.bin` + textures as separate
  files, so the textures can be recompressed (to WebP, here) without
  re-exporting.
- `export_morph_normal=False` roughly halves the file. Recomputed normals per
  morph are barely visible on a stylised character and cost as much as the
  positions.
- Target **names** ride in `mesh.extras.targetNames`. Without them three.js
  gives you `morphTargetInfluences[3]` and no way to know which vowel that is.

**The gotcha that will catch you at load time:** this GLB has three primitives
(face, cavity, tongue), so three.js builds **three meshes**, each carrying its
own copy of all eight targets. Drive one and the mouth opens while the tongue
stays put. `_bind()` collects every mesh that has a given target name and
writes all of them:

```js
this.object.traverse((o) => {
  const dict = o.morphTargetDictionary;
  if (!dict || !o.morphTargetInfluences) return;
  for (const name of ALL)
    if (name in dict) this.byName.get(name).push({ mesh: o, index: dict[name] });
});
```

---

## 7 · Japanese text becomes timing

`06_web/lib/jp_kana.py` and `jp_lipsync.py`.

### Why Japanese is the easy case

English is **stress-timed**: syllables are wildly unequal, and "comfortable"
collapses to three beats in speech. Getting English timing right without a
phoneme aligner is genuinely hard.

Japanese is **mora-timed**: every mora takes roughly the same beat. So a single
constant is already a decent model:

```python
MORA = 0.135        # seconds per mora
PEAK = 0.45         # where in the slot the vowel reaches full opening
CLOSE_LEAD = 0.35   # how early the lips shut before a bilabial
```

And there are only five vowels, so five morph targets cover the language.

### Parsing text into morae

Not the same as counting characters. `jp_kana.py` handles:

| feature | example | rule |
|---|---|---|
| **youon** (small ya/yu/yo) | きゃ | **one** mora, not two. Vowel is the small kana's. |
| **sokuon** (small tsu) | がっこう | a full beat with **no vowel** — a held closure |
| **hatsuon** | ん | a beat with the lips together or nearly so |
| **choon** | ラーメン | holds the **previous** vowel; not a new attack |
| **bilabials** | ま び ぽ | the lips must physically **close before** the vowel |
| **devoicing** | です → "des" | /i/ and /u/ between voiceless consonants: formed, barely voiced |

Devoicing is the detail that most improves the look. です with a full う at the
end looks like the tanuki is saying "desu" as two loud syllables. It isn't.

```python
if m.vowel in ("i", "u") and prev_kana[-1] in DEVOICE_AFTER:
    w *= 0.55      # formed but weak
```

Bilabials are the other one. /m/, /b/, /p/ are *made* by closing the lips, so
the closure has to be there before the vowel opens — otherwise the mouth is
already open on the ま and the whole word reads wrong.

### From morae to a track

Each mora emits events; `tracks()` converts events to sparse keyframes with one
rule that matters:

> At every event, **exactly one** viseme is driven and the rest are pinned to
> zero.

Without that, a linear interpolator leaves the previous vowel decaying while
the next one rises, and you get two mouths open at once — a rubbery blur
instead of a crossfade.

### Applying this to another language

The contract is the track JSON, so you need to replace only one file. What you
need is (a) a way to split text into timed units, and (b) a map from each unit
to a mouth shape. For a language with more vowel contrasts you would add morph
targets in `visemes.py` and rebuild. For English specifically, don't hand-roll
the timing — use a forced aligner and feed its output straight into the track
format.

---

## 8 · Stop guessing the timing: take it from the audio

This is the part that produced the biggest visible improvement, and the part
where I was most wrong at first.

### The bug: 700 ms of lag

Symptom: the mouth ran visibly behind the voice and got worse toward the end of
each sentence.

Two causes stacked:

**(a) TTS pads with silence.** The clip is 2.6 s but the speech starts at 0.18 s
and ends at 2.31 s. Fitting the mora track to the *file* duration therefore ran
the mouth about 40% too slow. Fix: measure the speech span and fit to that.

```python
def speech_span(path, floor_db=-40.0, pad=0.03):   # tanuki_tts_server.py
    ...                                            # first/last frame above the floor
```

**(b) Uniform mora timing is only an average.** Even fitted to the right span,
real TTS stretches phrase-final morae, compresses unstressed ones, and pauses
at commas for however long it likes. Correcting the average leaves the mouth
drifting *inside* the sentence and snapping back at the end.

### The fix: dynamic time warping

Both signals describe the same event in different units:

- the **track** predicts how open the mouth should be over time
- the **recording's energy envelope** shows how open it actually was

DTW finds the monotonic mapping between two sequences that minimises total
distance — the classic use is matching two utterances at different speaking
rates. Here it retimes the predicted curve onto the real one.

```python
FRAME, HOP = 0.025, 0.010      # 25 ms window, 10 ms step

def envelope(path, sr=16000):
    rms = ...                                    # per frame
    db  = 20 * np.log10(rms / rms.max())
    return np.clip((db + 45.0) / 45.0, 0, 1)     # −45 dB floor

def _dtw_path(a, b, band=0.25):                  # Sakoe–Chiba band
    ...
```

Two safeguards, both important:

- **The Sakoe–Chiba band** (`band=0.25`) forbids the path from wandering more
  than 25% of the sentence length away from the diagonal. Unconstrained DTW
  will happily map one long vowel onto half the sentence if that lowers the
  cost. The band encodes "the estimate was roughly right".
- **Keep the warp only if it helps** (`min_corr=0.15`). Compute the correlation
  before and after; if warping did not improve it, discard it and use the
  uniform track. A bad alignment is worse than none, and this makes the feature
  safe to leave on by default.

This needs **no model, no training and no calibration**. It works with any TTS
voice and any language the parser handles.

### Measured result, on your own TTS

`06_web/check_sync.py` runs it over a set of phrases:

| | mean correlation |
|---|---|
| uniform mora timing | **0.686** |
| after DTW alignment | **0.881** |
| gain | **+0.194** |
| residual lag | 0 to −10 ms |

The gains sort by whether the phrase contains commas or sokuon — exactly where
uniform mora timing is blind. That pattern is the evidence that the mechanism
works for the reason claimed, rather than just producing a bigger number.

### What that correlation number actually means

`06_web/what_correlation_means.png` shows it: grey filled area = how loud the
recording is over time; blue line = how open the rig says the mouth should be.
Correlation asks "do these two rise and fall together?"

| value | what it looks like |
|---|---|
| below 0.3 | the mouth is flapping to its own rhythm |
| 0.5 – 0.7 | recognisably related, visibly drifting |
| above 0.85 | tracking closely |

It never reaches 1.0, and it shouldn't: loudness and openness are related but
not identical. /i/ is loud with a nearly shut mouth. A score of 1.0 would mean
your mouth model had become a volume meter.

---

## 9 · The runtime driver

`06_web/src/tanuki-lipsync.js`. Three modes: `idle`, `track` (a script), `live`
(analyse the audio as it plays).

### Smoothing: attack ≠ release

```js
this.attack  = 0.022;   // seconds
this.release = 0.055;
// per frame, frame-rate independent:
current += (goal − current) * (1 − Math.exp(−dt / tau));
```

Two things here are deliberate.

**Asymmetry.** A mouth snaps open and eases shut. Equal times read as rubbery.

**Short constants.** An exponential filter lags its input by roughly its own
time constant. 45 ms of attack is 45 ms of the mouth trailing the voice — right
at the edge of perceptible. Smoothing is not free; it is latency you are
choosing to spend.

**`1 − exp(−dt/τ)`, not a fixed `α`.** A fixed per-frame blend factor makes the
animation faster on a 144 Hz monitor than a 60 Hz one. This form does not.
(Every smoother in the project uses it: the driver, the body, the bands.)

### Clear every channel each frame

```js
for (const n of ALL) this.goal[n] = 0;      // then re-drive whatever applies
```

This looks wasteful and is load-bearing. Before it existed, `goal.Blink` was
only ever *written* when a track carried a Blink channel — so in idle mode the
first blink raised it to 1.0 and, because `_tickBlink` combines with
`Math.max`, nothing could bring it back down. **The eyes shut on the first
blink and stayed shut.**

The consequence to remember: `setViseme()` is washed out on the next tick. To
*hold* a value use `setOverride('Blink', 1)`, released with
`setOverride('Blink', null)`. Overrides are applied last, after the track and
the idle blink, precisely so they survive the reset.

### Idle blink

```js
blinkGap = [2.2, 5.5];                  // random, never evenly spaced
const DOWN = 0.055, HOLD = 0.03, UP = 0.075;   // fast down, slower up
```

Symmetric timing reads as a twitch. Evenly spaced blinks are one of the
clearest tells that something is animated rather than alive. And the timer
re-arms when a blink **starts**, not when it ends — decrementing during the
blink leaves it already negative on the finishing frame, which restarts it
immediately and produces a permanent flutter. (Yes, that happened.)

### Sync: measured, not dialled

At one point this was a slider the user dragged until it looked right. That was
unfinished work disguised as a feature — the correct value is a property of the
listener's hardware, and it changes when they switch to Bluetooth mid-session.

`audio.currentTime` reports the **decoder** position. The sound still has to
cross the output buffer and the hardware. The Web Audio API measures exactly
that:

```js
const out  = ctx.outputLatency;     // ~10 ms wired, 150 ms+ Bluetooth
const base = ctx.baseLatency;
this.measuredLatency = out > 0 ? out : (base > 0 ? base + 0.02 : 0.04);
```

Never fall back to zero. Zero latency is never true; a small typical value is
wrong by less.

On top of that, a deliberate **30 ms lead**:

```js
this.lead = 0.03;
timeShift() { return measuredLatency + lead + offset; }
```

Two reasons pointing the same way:

1. Real speech is **anticipatory** — the lips start forming a vowel during the
   preceding consonant. A mouth that moves exactly on the sound already looks a
   beat late.
2. The perceptual tolerance is **asymmetric**. The broadcast standards all
   agree that early is safer than late:

| standard | audio may lead video by | audio may lag video by |
|---|---|---|
| ITU-R BT.1359 (detectability) | 45 ms | 125 ms |
| ATSC IS-191 | 15 ms | 45 ms |
| EBU R37 | 40 ms | 60 ms |
| film practice | ±22 ms | |

Erring early is roughly three times safer than erring late. So lead.

### Two failure modes worth knowing

**Reusing one `<audio>` element.** `createMediaElementSource` can be called
only **once per element**, so the element is reused and the node cached against
it. But a reused element is parked at the previous clip's end, so the second
`speak()` sampled the track past its last key and never moved the mouth. Hence
`el.currentTime = 0`.

**`ended` is not guaranteed.** A stalled buffer, a decode error, or a device
with no audio output all leave it unfired — and then the promise never settles,
which in a chat UI means the send button stays disabled forever. There is a
timer at clip length + 2 s as a safety net. *Any* promise that resolves on a
media event needs one.

### Live mode, when there is no script

`formants.js` estimates formants per frame with LPC and picks the nearest
Japanese vowel. Two calibration points:

- **LPC order ≈ sr/1000 + 4.** At the textbook order 12, the two close formants
  of /o/ merge into a single pole and every /o/ misclassifies.
- **Partial speaker adaptation, exponent 0.35 not 1.0.** Full normalisation
  divides by the utterance's own median, which depends on which vowels happen
  to occur — a phrase heavy in /a/ drags every other vowel out of position.

Use live mode for microphone input or a streamed voice. If you have the text,
use the track: it knows about consonants, and no acoustic method can recover a
/p/ that is silent by definition.

---

## 10 · The body, and why one number was not enough

`06_web/src/bands.js`, `body.js`.

There are no bones, so the only thing that can move is the whole object's
transform. That is enough: a slow breath, a weight shift, a nod. A perfectly
still body under a moving mouth is what makes an avatar look like a puppet.

### The first version was subtly wrong

It drove all of that from one number: how open the mouth was. That is a good
**mouth** signal and a bad **body** signal, because it is a function of *which
vowel is being said*. The tanuki leaned forward on あ and went still on い —
not because the sentence had a shape, but because /i/ is a narrow vowel.

### Speech is roughly three signals, not one

| band | Hz | what it is | what it drives |
|---|---|---|---|
| low | 70–260 | the voiced fundamental | torso engagement, breath depth |
| mid | 260–2200 | F1/F2 — perceived loudness | lean and bob |
| high → `hit` | 2600–7000 | frication, plosive bursts | head accents |

The `hit` signal is the interesting one. A consonant is an **event**, not a
level, so what gets used is the **rise** of the high band, half-wave rectified,
firing an impulse that decays over ~0.2 s. The head ticks once and recovers.
Nods now land on the plosives instead of on a fixed 1.55 Hz sine drifting
across the sentence.

### Two details that make it work on real audio

**Automatic gain control.** Each band carries a running peak: instant attack,
~6 dB/s decay. A band is reported as its position between a noise floor and
that peak. Without this, a fixed dB range means the body is dead on a quiet
edge-tts clip and pinned on a loud VOICEVOX one.

**Different time constants — 0.18 s, 0.09 s, 0.03 s.** Heavy things settle
slowly. Flattening these out throws away the entire point of splitting the
bands.

**No lead on the bands.** The mouth is read `timeShift()` early; the bands are
read at playback position. So the body trails the mouth by 30–40 ms — which is
the right way round. Lips anticipate a sound; torsos do not.

**Fallback.** With no audio graph — an external clock, a refused
`AudioContext`, a muted tab — `synth()` manufactures the bands from mouth
openness, i.e. the old behaviour. Blunter, but the body stays in character
instead of stopping dead. `body.bandDrive = false` forces it, and `player.html`
has a checkbox to A/B it mid-sentence.

### The risk that had to be handled

Calling `createMediaElementSource` **permanently** routes that element's sound
through the AudioContext. If the context can't be resumed, the audio is
silenced forever. So the graph is only built after checking
`ctx.state === 'running'`, and the whole thing is best-effort: failing loses
the band signal, which is cosmetic, and never the voice, which is not.

---

## 11 · Making it look sharp

The face occupies **under 2% of the texture atlas — about 287×287 texels** —
and on screen it is always magnified. That is a ceiling set by the source
model, not by the renderer. Three fixes, in order of how much they buy:

1. **Sharpen the texture at bake time** (`sharpen_textures.py`). Gradient-
   weighted unsharp masking: boundaries tighten, flat fur is left alone. Does
   more than every render setting combined and costs nothing at runtime.
2. **Anisotropic filtering** — off by default in three.js, free to enable.
3. **Contrast-adaptive sharpening** on the final image (FidelityFX-style CAS,
   ~0.25).

A 4096 Lanczos upscale added almost nothing on top of step 1, so the textures
stay at 2048 WebP.

> I got this wrong twice before getting it right: my first two attempts were
> render settings — tone mapping, exposure, filtering. Wrong layer. The
> information simply was not in the image yet. **Find the layer that is losing
> the information before tuning the layers downstream of it.**

**The postprocessing trap.** `EffectComposer` renders into a linear target, so
tone mapping and sRGB conversion stop happening automatically — without an
`OutputPass` the image comes out washed and orange. And the final pass must
write **opaque alpha**, or the canvas is transparent and nothing appears at
all. Both of those cost me a debugging round each.

---

## 12 · The server, and wiring it to your bot

`06_web/tanuki_tts_server.py` — Python standard library only.

```bash
pip install edge-tts pykakasi     # both optional, both recommended
python tanuki_tts_server.py       # → http://localhost:8080
```

| endpoint | what it does |
|---|---|
| `GET /` | redirects to `chatbot.html` |
| `GET /api/status` | which TTS engine is active |
| `POST /api/say` | `{text}` → `{audio, track, kana, duration, align}` |
| `GET /media/<file>` | the synthesised audio |

TTS backends are tried in order and the first available wins: **voicevox**
(local, best Japanese) → **edge** → **gtts** → **offline** (a formant synth, so
the demo works with no network at all — and with no SciPy either; its one
2-pole resonator has a numpy fallback, because a backend whose job is "never
hard-fail" must not have an optional dependency).

Availability is not the same as *working*, so on `auto` a backend that throws
drops to the next one and the response carries `fallback_from` rather than an
error. An explicitly chosen engine never falls back — you asked for that one.

**A defaults trap worth remembering.** `chatbot.html` posts `{text, blink}` and
no `voice`. The server filled that in as `None` and passed it on, so the
signature default never applied:

```python
def tts_edge(text, path, voice="ja-JP-NanamiNeural", ...):   # looks safe
fn(spoken, path, voice=None, rate=rate)                      # → voice is None
```

edge-tts type-checks it and raises `TypeError: voice must be str`. A default
argument protects you when a parameter is **omitted**, never when it is passed
explicitly as `None`. Anywhere a value crosses an HTTP boundary, coerce at the
point of use — `voice = voice or EDGE_VOICE` — rather than trusting a default
several frames up the stack.

What `say()` does, in order: synthesise (cached by SHA-1 of text+voice+rate) →
find the speech span → build the mora track fitted to that span → shift it back
into file time → DTW-align it to the recording → return audio URL + track.

`protocol_version = "HTTP/1.1"` matters: with HTTP/1.0 the browser reopens a
connection per request, and while the 19 MB model is streaming the small `/api`
calls beside it queue long enough to look like the server is down.

### The integration

One function in `chatbot.html`, marked with a banner comment:

```js
async function askYourBot(userText) {
  const r = await fetch('/your/chat/endpoint', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: userText }),
  });
  return (await r.json()).reply;      // Japanese text
}
```

Everything after that is unchanged: the reply goes to `/api/say`, and the
result goes to `tanuki.speak({ audio, track })`.

If your bot already produces audio elsewhere, you only need the track — POST
the same text to `/api/say` and use its `track` with your own audio, or call
`playTrack(track, () => myPlayer.currentTime)` to drive from any clock you own.

---

## 12b · Latency, and why "make it faster" started with a stopwatch

A chat avatar is judged on the gap between pressing Send and the mouth moving.
Everything above is about *correctness*; this is about that gap.

### First, find out where it goes

Guessing here is expensive, so the first move was to time each stage rather
than optimise the one that felt slow. On a 4.9 s clip:

```
  synthesis (engine-dependent)     ← the elephant
  duration_of   (ffprobe spawn)   :  49 ms
  speech_span   (ffmpeg spawn)    :  51 ms
  build_track                     :   0.4 ms
  align         (ffmpeg spawn #2) : 107 ms
  ----------------------------------------
  non-TTS overhead                : 207 ms   in 3 process spawns
  a REPEATED line                 : 186 ms   ← should have been zero
```

Two things stand out, and neither is what I would have guessed:

- **The same audio was decoded three times, in three separate processes** —
  once for its duration, once for the silence trim, once for the alignment
  envelope. Each spawn also wrote and re-read a temp WAV.
- **A repeated line cost nearly as much as a new one.** The audio was cached;
  everything derived from it was not.

Fixes: decode once and pass the frames around (`analyse()`); ask ffmpeg for raw
samples on stdout instead of a temp file; cache the whole response, not just
the clip. 207 ms → 101 ms, three spawns → one, repeats → ~0.

### Then find the part that dominates everything else

Synthesis. And it scales with the length of the text, which is why a long reply
feels so much worse than a short one. No amount of shaving milliseconds off the
server touches it.

The insight is that speech is *already divided* — at sentence boundaries — and
the user only needs the **first** sentence to start:

```
one shot   [------- synthesise whole reply -------][play ...]
queued     [synth 1][play 1.............][play 2.......][play 3...]
                    [synth 2][synth 3]   (overlapped, ahead of playback)
```

Time-to-first-sound stops depending on the length of the reply. Measured in a
real browser, four sentences, synthesis modelled on edge-tts: **2.74 s → 0.76
s**, and the total *also* dropped from 8.96 s to 7.36 s, because each clip's
silence padding gets skipped rather than played.

With a streaming LLM it compounds: `feed()` dispatches each sentence as soon as
punctuation closes it, so synthesis overlaps generation.

> The general shape: **first make the work smaller, then overlap what is
> left.** Sentence chunking is both — each unit is cheaper *and* the units
> pipeline.

### The delay you feel is not always the delay you have

Printing the whole reply the moment it arrives and *then* starting the voice
makes the eye finish reading before the mouth has moved. The wait is the same
length either way; revealed in step with the audio it reads as a character
talking, revealed all at once it reads as a broken avatar. Cheap fix, large
effect: `onChunk` appends each sentence to the bubble as it starts being
spoken.

Related: the first chunk is cut short (18 characters, comma breaks allowed)
because it is the only one anybody waits for. Later chunks are longer, because
they are synthesised behind the one playing, and more text gives the engine
better intonation. Optimise the piece on the critical path; leave the rest
alone.

### Stop estimating when the engine will just tell you

Everything in §7 and §8 — mora timing, then DTW onto the energy envelope — is
inference. It exists because most TTS gives you a WAV and nothing else.

VOICEVOX gives you the plan. `/audio_query` returns every mora with its
consonant and vowel and how long each will last, and you can then drive the
mouth from the same numbers that generated the sound. It even marks devoiced
vowels in upper case (`U` for the /u/ of です) — the exact distinction
`jp_lipsync` has to guess from surrounding consonants.

That is the difference between an estimate corrected after the fact and ground
truth. It also removes the whole decode-and-align stage: a VOICEVOX request
costs a WAV header read and a dictionary walk.

The units of `consonant_length` and `vowel_length` are not documented, and this
is exactly the sort of thing a version bump changes quietly. So nothing assumes
they are seconds: the durations are summed, compared with the real length of
the audio that came out, and the whole path is abandoned for the estimating one
if they disagree by more than 20%.

> **Never trust an undocumented unit. Check it against the artifact it
> describes, and make the check part of the code, not part of the testing you
> did once.**

### The mouth freezes when the clock stops

The driver reads the track at `audio.currentTime`. A **paused** clip's clock
does not move — so when the queue cuts a sentence short and waits before the
next one, nothing advances the track and the mouth holds whatever shape it had
at the cut. Between sentences, and after the last one, the character sits there
with its mouth open.

Nothing else was ever going to close it: the track's own closing keyframes are
past the cut point, and they are never reached. One line fixes it — put the rig
back to rest at the end of each chunk — but the interesting part is how nearly
it was missed.

**The first measurement said the bug was there. It was measuring wrong.** I
sampled mouth openness for 300 ms after each cut, got 0.85, and had my culprit.
The window ran past the start of the *next* sentence, where the mouth opens
because it is supposed to. Narrowing it to the silence itself gave 0.01.

**And the fix's own test passed with the fix removed** — sometimes. Whether the
mouth freezes depends on where the cut lands relative to the track: land on a
closing keyframe and it is shut anyway. Two runs of the same test gave 0.01 and
0.25. A check that only fires when it gets unlucky is not a check.

So the guardrail forces the condition instead of hoping for it: a second pass
cuts every sentence 0.3 s early, guaranteeing the track is mid-vowel at the cut.
That is deterministic — **0.82 open with the fix removed, 0.23 with it in**.

> Two rules earned here. **Check that a measurement window contains only what
> you think it contains.** And **prove a guardrail fails**: break the code on
> purpose and watch it go red, or you have written decoration.

### Two hangs that only a queue could expose

Sending lines back to back put weight on paths that a single line never
stressed, and both bugs were silent — no error, just no sound.

**`ctx.resume()` does not reject when it is blocked; it never settles.**
`speak()` awaited `measureLatency()` and the band graph *before* `play()`. Both
need an AudioContext, and a context suspended by the autoplay policy leaves
that promise pending for ever. Neither is needed to make sound — one trims the
mouth by tens of milliseconds, the other drives the body — so both moved to
*after* `play()`, and every resume is now raced against a 250 ms timeout.

> Rule: nothing on the path to producing output may await something that is
> allowed to never finish.

**A seek makes `loadeddata` unreachable.** `speak()` set `currentTime = 0` to
un-park a reused element, then waited for `readyState >= 2`. Assigning
`currentTime` starts a *seek*, a seek drops readyState back below
`HAVE_CURRENT_DATA` — and `loadeddata` only ever fires **once per resource**.
So it waited for an event that could never arrive, and the line played only
when a safety timer fired seconds later. The wait was unnecessary anyway:
`play()` is happy on a buffering element.

Both were found by timestamping every step in the browser rather than reading
the code again. The log showed `speak:enter` with no matching `play()` — which
localises the bug to nine lines without a single hypothesis.

---

## 13 · How to check your own work

Every claim in this project was verified by something that could have said
"no". This is the most portable part of the method.

| question | how it was answered |
|---|---|
| Is the mouth curve right? | draw it on the texture, render, look |
| Geometry bug or texture bug? | render in flat clay — no textures, no lighting |
| Did the mesh operation do what I meant? | count boundary edges / faces before and after |
| Is the lip-sync actually in sync? | `check_sync.py` — correlation against the real audio envelope |
| Does the sync number mean anything? | plot both curves (`what_correlation_means.png`) and look at them |
| Does the page still work after a change? | headless Chromium, real audio, assert on the values |

That last one is worth showing, because it is cheap and almost nobody does it
for a graphics change. The band-drive work was verified by playing a synthetic
clip — a voiced segment, then a burst of frication — through a real
`AudioContext` in headless Chromium and asserting on the readings:

```
voiced segment     low 0.99   mid 1.00   hit 0.00
frication segment  high 0.81  hit 0.86
```

Voicing lights the low band and fires no accents; frication fires accents and
does not light the low band. That is the mechanism working for the stated
reason — not just "it looked fine when I ran it".

---

## 14 · Recipes

> **Before you run the offline scripts.** Everything in `02_scripts/` needs
> Blender as a Python module (`pip install bpy`) and was written against the
> build environment's absolute paths — `sys.path.insert(0, "/home/claude/tanu")`
> in `build_model.py`, its `OUT` constant, and the `--out` default in
> `tune_mouth.py`. Point those three at your own folders before the first run.
> The runtime half (`06_web/`) has no such dependency: it is self-contained and
> runs as-is.

### Move or resize the mouth

Edit `MOUTH` in `02_scripts/visemes.py`:

```python
MOUTH = dict(cx=-0.036, cz=0.3038, curv=2.90, hw=0.132, scale=1.00)
```

| knob | effect |
|---|---|
| `cx` | left / right. More negative moves it left. The nose is at −0.041. |
| `cz` | up / down — the lowest point of the mouth line |
| `curv` | how much the corners ride up |
| `hw` | half-width, centre to corner |
| `scale` | multiplies every viseme's opening size |

Preview before committing, then rebuild:

```bash
python 02_scripts/tune_mouth.py --cx -0.050 -0.036 -0.022 --open A
python 02_scripts/tune_mouth.py --cz 0.29 0.3038 0.318
python 02_scripts/build_model.py
```

Then copy `07_web_model/*` into `06_web/model/`.

### Change how far a vowel opens

The `VISEMES` table in `visemes.py`. `rx`/`rz` are the opening's half-size,
`wc` its vertical offset, `corner` pulls the lip corners out or in, `purse`
protrudes them, `open` is the jaw contribution.

### Tune the body

```js
new BodyMotion(group, {
  breathRate: 0.23, swayAmount: 0.016, nodAmount: 0.030,
  speechSmooth: 0.10, accentNod: 0.020, accentDecay: 0.20,
  bandDrive: true,
});
```

### Adjust the sync by hand (you shouldn't need to)

```js
tanuki.lead = 0.03;        // anticipation, seconds
tanuki.offset = 0;         // manual trim on top of the measured latency
tanuki.autoLatency = true; // leave this on
```

### Put it on a different character

The offline half is specific to this mesh; the runtime half is not. In order:

1. Measure the new model's mouth and eyes (§2). This is most of the work.
2. Re-run the surgery with new `MOUTH` / `EYES` values (§3).
3. Keep the same **eight target names** — `A I U E O Blink BlinkL BlinkR`.
4. `06_web/` then works unchanged, because it only ever refers to those names.

---

## 15 · Glossary

| term | meaning |
|---|---|
| **morph target** / blend shape / shape key | a stored second set of vertex positions; the renderer blends base → target by a weight |
| **viseme** | the visible mouth shape for a sound. Many phonemes share one viseme — /p/, /b/, /m/ look identical |
| **mora** | Japanese timing unit. きゃ is one; っ and ん are each one |
| **split vertex** | one surface point stored twice so each copy can carry a different UV. The cause of the 98,812 fake holes |
| **boundary edge** | an edge with exactly one face — the border of a hole, real or fake |
| **UV atlas** | the 2D layout the texture is painted in |
| **formant** | a resonance of the vocal tract. F1/F2 identify a vowel |
| **LPC** | linear predictive coding; models the vocal tract as a filter, which is how formants are found |
| **DTW** | dynamic time warping; the best monotonic alignment of two sequences at different rates |
| **Sakoe–Chiba band** | a constraint stopping a DTW path from straying far from the diagonal |
| **CAS** | contrast-adaptive sharpening; sharpens flat areas more than detailed ones |

---

## 16 · Where the limits are

Honest about what is not solved:

- **Texture resolution is a source-model ceiling.** ~287×287 texels for the
  face. Sharpening bought real detail; nothing short of re-atlasing the head
  onto its own 2048² island, or regenerating the source at 4K, buys more.
- **`PEAK = 0.45`** — where in each mora the vowel reaches full opening — is
  not honestly tuned. The only test audio available came from the same mora
  model, so tuning it against that would be measuring the ruler with itself.
  Tuning it needs hand-labelled speech.
- **Kanji needs `pykakasi`.** Without it, give the pipeline kana.
- **No emotion channel.** There are no brow, cheek or eye-shape targets, so the
  character can speak but cannot look pleased about it. The route is the same
  as the visemes: sculpt the pose from the sealed base, export as another named
  target, drive it with `setOverride`.

---

## 17 · What cost me the most time

| symptom | actual cause |
|---|---|
| face covered in cracks after smoothing | split vertices at UV seams — weld first |
| 307,628 stray faces | a boundary op hit every open edge in the mesh, not just the mouth |
| muzzle tore apart when deforming | rescaled coordinates instead of displacing |
| mouth interior a lit grey lump | looking at the outside of a convex blob |
| blink reopened the mouth | eye keys built on the raw mesh, not the sealed base |
| jagged flap beside the mouth | a texture fill artifact — I debugged the wrong layer for three rounds |
| whole image washed and orange | `EffectComposer` without `OutputPass` |
| canvas completely blank | the final pass passed the render target's alpha through |
| eyes shut on the first blink, forever | `goal.Blink` never reset, combined with `Math.max` |
| second `speak()` did nothing | reused `<audio>` still parked at the previous line's end |
| 700 ms of lip-sync lag | TTS silence padding, then non-uniform real timing |
| `/o/` always misclassified | LPC order too low to separate its two close formants |
| `TypeError: voice must be str` from the chatbot | an explicit `None` overrode a default argument |
| queued lines silently never played | `speak()` awaited `ctx.resume()`, which never settles when blocked |
| a line played only after a 3.5 s safety timer | waited for `loadeddata`, which cannot fire again after a seek |

If there is one habit to take from all of this: **decide which layer the
problem is in before you start fixing it.** Half of those rows are cases where
I was working confidently in the wrong layer.
