# How this was built

A working guide to the tanuki rig — what each piece does, why it does it that
way, and which parts fought back. Written so you can change any of it yourself.

---

## The shape of the whole thing

```
tanu_base.glb  ──►  02_scripts/build_model.py  ──►  07_web_model/tanuki.gltf
                          │                                   │
                    visemes.py   ← the settings                │
                    geo.py       ← how the mouth deforms       │
                    cutmouth.py  ← surgery on the mesh         │
                    painter.py   ← edits to the texture        ▼
                    eyes.py      ← blink              06_web/ chatbot.html
                                                              │
04_pipeline/  Japanese text ──► viseme track ─────────────────┘
```

Two halves. **Offline** (Python + Blender) turns your file into a model with
morph targets. **Runtime** (JavaScript) decides which targets to move and when.
They meet at a JSON track: `{"A": [[0.61, 1.0], ...], ...}` — time, weight.

---

## Part 1 — Finding things on a model nobody labelled

Your file arrived as one unnamed mesh. No bones, no landmarks, no "this is the
mouth". So the first job was measurement.

**Locating the mouth.** I fitted a parabola `z = cz + curv·(x−cx)²` to the
painted smile by drawing candidate curves onto the texture in bright colours,
rendering the head, and comparing against the real smile. Three rounds of
guess-render-compare. Purely numerical fits kept failing because the eye
patches and the nose's underside are darker than the smile and dominated any
brightness-based search.

**The lesson**: when you can render, render. A calibrated overlay settles in
one image what statistics argue about for an hour.

**Locating the eyes** worked the same way — find the bright desaturated sclera
texels, cluster into two groups, fit an ellipse to each, then check by overlay.
Measured centres came out asymmetric (left eye at x = −0.245, right at +0.178)
because the model genuinely is asymmetric. Worth knowing before you "fix" it.

---

## Part 2 — Preparing the mesh

### Weld first. Everything depends on it.

The source reports **98,812 boundary edges**. Almost none are holes. They are
UV seams stored as *split vertices*: one point on the surface saved two or
three times at identical coordinates so each copy can carry a different UV.

This matters enormously:

- **Smoothing tears the model apart.** Each twin only sees neighbours on its
  own side of the seam, so a Laplacian pass pulls them in different directions
  and every seam rips open. I did exactly this and produced a face covered in
  cracks.
- **Real defects hide among the fakes.** There was a crack beside the mouth
  that looked like a leftover seam from my own cut. It was in the source file
  the whole time.

`weld_and_fill()` merges vertices within 1e-5. Boundary edges drop 98,812 →
131, the crack closes on its own, and 54,826 duplicate vertices disappear.
Per-loop UVs survive untouched, so nothing about the texturing changes.

If you ever need to smooth without welding, group coincident vertices first,
average across the combined neighbourhood, and write one result back to every
twin — `relax_region()` in `cutmouth.py` does this.

### Relaxing the old smile

The sculpted smile groove is ~0.27 wide; the hole cut for the visemes is 0.14.
Cutting the middle leaves the outer thirds behind as two creases either side of
the mouth — the "scars". `flatten_crease()` relaxes that band back into the
muzzle, tapering to zero at the cut rim and at the corners so no flat patch
appears where the groove was.

### Cutting the mouth

`cut()` deletes faces inside the envelope. Two things to watch:

- **Restrict every boundary operation to the region you mean.** My first
  `mouth_bag()` extruded *every* boundary edge in the mesh and generated
  307,628 faces. The hat has its own open edges.
- **The cut edge comes out ragged** because the mesh is triangle soup with no
  edge loops. `smooth_boundary()` averages each rim vertex toward its two rim
  neighbours — 14 passes straightens it without touching the interior.

### The mouth interior

Three attempts:

1. A small ball behind the hole → renders as a lit grey lump. You are looking
   at the *outside* of a sphere.
2. A ball big enough to be concave → pokes out through the chin.
3. **Extrude the hole's own rim inward.** Welded to the lips, so it can never
   separate from them and can never escape the head. Ring 0 *is* the rim, so
   when a viseme opens the lips the cavity opens with them.

---

## Part 3 — The morph targets

### The base pose is the mouth CLOSED

glTF morph targets all blend from the base mesh, so the base has to be the
neutral pose. `sealed()` collapses the cut rim onto the lip line, leaving a
slit 0.0095 tall instead of an 0.083 hole. Each viseme reopens it.

The lips are pushed forward by 0.004 in the sealed pose so they overlap
slightly. Meeting exactly lets the cavity show through as a dark line.

### Displacement, not rescaling

My first deformation rescaled the local coordinates over the falloff region.
That moves a distant vertex by a fraction of its own (large) coordinate, and it
tore the whole muzzle apart. The working version moves each vertex by the
difference between two rim shapes — bounded by a few millimetres no matter how
far the falloff reaches.

### One envelope, five visemes

The cut is sized *between* the widest viseme (い, rx 0.098) and the narrowest
(う, rx 0.036). Cutting at い's width forces う to contract its rim by most of
the mouth's half-width, which crumples the geometry. Sizing in between keeps
every viseme within a few millimetres of the rim it was cut from.

### Blink, with no eyelids

The eyes are near-flat domes with the iris painted on. There is nothing to
rotate. Each eye collapses vertically onto a line instead — and because the
iris is painted on the surface, squashing the surface squashes the eye.

The collapse line sits *just* above centre: high enough to read as an upper lid
descending, low enough that the line lands on the dark iris. Put it higher and
you get a bright sliver of sclera that looks like a glint, not a closed eye.

**Eye keys are built from the sealed base, not the raw mesh.** A shape key
stores absolute positions, so a blink built on the open-mouthed original drags
the mouth back open whenever it blends in. Same rule for anything you add.

---

## Part 4 — Editing the texture

### The UV atlas is unusable by hand

Auto-generated and fragmented across dozens of small islands. Painting by
island is hopeless. Instead every mouth-region texel gets its **3D position**
baked (`projpaint.py` rasterises the triangles in UV space), so the mouth is
painted as a function of position and island boundaries stop mattering.

### Two curves, kept apart

`FIT` is where the *original* smile is — used only for erasing it.
`MOUTH` is where the *new* mouth goes — used for cutting, morphing, painting.

Drive both from one curve and nudging the mouth also moves the eraser, so the
old smile creeps back out from under it.

### Erasing without leaving a smear

Three things it has to get right:

- Fill from the **same side** of the lip line. The muzzle runs cream below and
  tan above; pulling from both smears one into the other.
- Weight the neighbours by **distance**, not a plain median. Near the corners
  the source set thins out and an unweighted median produces a blocky jagged
  patch that looks exactly like torn geometry. I chased that as a mesh bug.
- **Feather the band edge.** A hard swap leaves a seam where the smile ended.

### Putting a smile back

A blank muzzle is most of why a closed face reads as artificial. `paint_smile()`
draws a clean line along the new curve. Its fade has to start very late (88% of
the half-width) because the middle of the line is where the hole is — the only
part you ever see is the outer half, and a natural-looking fade from halfway
erases precisely the visible segment.

---

## Part 5 — Sharpness

The face occupies **under 2% of the atlas, about 287×287 texels**. On screen it
is always magnified. Three fixes, in order of how much they buy:

1. **Sharpen the texture at bake time** (`sharpen_textures.py`). Gradient-
   weighted unsharp, so boundaries tighten and flat fur is left alone. Does
   more than every render setting combined and costs nothing at runtime.
2. **Anisotropic filtering** — off by default in three.js, free.
3. **Contrast-adaptive sharpening** on the final image, ~0.25.

A 4096 Lanczos upscale added almost nothing on top of the sharpening, so the
textures stay at 2048.

**The postprocessing trap**: EffectComposer renders into a linear target, so
tone mapping and sRGB conversion stop happening — without an `OutputPass` the
image comes out washed and orange. And the final pass must write opaque alpha,
or the canvas is transparent and nothing appears at all.

---

## Part 6 — The runtime

### Japanese timing

Japanese is mora-timed: every mora takes about the same beat, so one duration
per mora is a good first approximation. On top of that: きゃ is **one** mora,
not two; っ and ん are beats with no vowel; ー holds the previous vowel; the
lips must close before ま/ば/ぱ; and い/う devoice between voiceless consonants
(です → "des") so they open less.

Pass `total` set to the real audio duration. Mora timing is an estimate and
drifts over a sentence.

### Driving from audio

LPC formants per frame, nearest Japanese vowel. Two things it needs:

- **LPC order ≈ sr/1000 + 4.** At order 12 the two close formants of /o/ merge
  into one pole and every /o/ misclassifies.
- **Partial speaker adaptation** (exponent 0.35, not 1.0). Full normalisation
  divides by the utterance's own median, which depends on which vowels happen
  to occur — a phrase heavy in /a/ drags every other vowel out of place.

### Body movement

No bones, so only the whole object can move. That is enough: a slow breath, a
weight shift, and a nod on the stressed syllables. The body **lags** the mouth
(smoothed over ~0.1s) or it twitches on every consonant instead of riding the
phrase. Applied to a wrapper group so it never fights your own placement.

---

## Changing things

**Move or resize the mouth** — edit `MOUTH` at the top of `visemes.py`:

```python
MOUTH = dict(cx=-0.036, cz=0.3038, curv=2.90, hw=0.132, scale=1.00)
```

| knob | what it does |
|---|---|
| `cx` | left / right. More negative moves it left. Nose is at −0.041. |
| `cz` | up / down — the lowest point of the mouth line |
| `curv` | how much the corners ride up |
| `hw` | half-width, centre to corner |
| `scale` | multiplies every viseme's opening size |

Preview before committing:

```bash
python 02_scripts/tune_mouth.py --cx -0.050 -0.036 -0.022 --open A
python 02_scripts/tune_mouth.py --cz 0.29 0.3038 0.318
```

Then rebuild: `python 02_scripts/build_model.py`

**Change how far a vowel opens** — the `VISEMES` table in `visemes.py`.
`rx`/`rz` are the opening's half-size, `wc` its vertical offset, `corner` pulls
the lip corners out or in, `purse` protrudes them.

**Tune the body motion** — options to `new BodyMotion(group, {...})`:
`breathRate`, `swayAmount`, `nodAmount`, `speechSmooth`. Set `enabled = false`
to switch it off.

**Change the sharpening** — `sharpen_textures.py`, then rebuild.

---

## Things that cost me time

| symptom | cause |
|---|---|
| face covered in cracks after smoothing | split vertices at UV seams; weld first |
| 307,628 stray faces | boundary op hit every open edge in the mesh, not just the mouth |
| muzzle tore apart when deforming | rescaled coordinates instead of displacing |
| mouth interior a lit grey lump | looking at the outside of a convex blob |
| whole image washed and orange | EffectComposer without `OutputPass` |
| canvas completely blank | final pass passed the render target's alpha through |
| blink reopened the mouth | eye keys built on the raw mesh, not the sealed base |
| jagged flap beside the mouth | texture fill artifact, not geometry — I chased the wrong layer |
| second `speak()` did nothing | reused `<audio>` still parked at the previous line's end |
| `/o/` always misclassified | LPC order too low to separate its two close formants |
