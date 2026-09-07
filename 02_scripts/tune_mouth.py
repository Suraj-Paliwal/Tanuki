# -*- coding: utf-8 -*-
"""Mouth position tuner.

Renders a grid of candidate mouth settings so you can pick by eye, then copy
the numbers into the MOUTH block at the top of visemes.py and rebuild.

    python tune_mouth.py --cx -0.048 -0.036 -0.024      # sweep left/right
    python tune_mouth.py --cz 0.29 0.3038 0.318         # sweep up/down
    python tune_mouth.py --scale 0.85 1.0 1.15          # sweep size
    python tune_mouth.py --cx -0.045 -0.036 --open A    # with the mouth open

Each cell is a full rebuild - cut, cavity, shape keys - because moving the
mouth changes where the HOLE goes, not just where a texture is drawn. That is
also why this is a render grid and not a live browser slider: the geometry has
to be recut for every value.

Rendered with Blender's Workbench engine for speed, so the mouth cavity shows
up white rather than dark - it has no texture and Workbench paints untextured
surfaces flat. Judge position and size here, not colour.
"""
import argparse, itertools, os, sys
import bpy, numpy as np
sys.path.insert(0, "/home/claude/tanu")

def render_variant(cx, cz, hw, scale, open_key, out, res=560):
    # visemes must be re-imported per variant: MOUTH is read at import time by
    # geo and cutmouth, so the modules have to be reloaded to see new numbers.
    import importlib
    import visemes
    visemes.MOUTH.update(cx=cx, cz=cz, hw=hw, scale=scale)
    visemes.XC, visemes.ZC = cx, cz
    visemes.HW = hw
    visemes.MAXR = dict(rx=0.070 * scale, rz=0.041 * scale)
    for m in ("geo", "cutmouth", "painter"):
        if m in sys.modules: importlib.reload(sys.modules[m])
    import renderlib as R
    from geo import sealed, viseme_pose
    from cutmouth import (weld_and_fill, flatten_crease, cut, smooth_boundary,
                          mouth_bag, add_tongue, surface_y_at_mouth)

    ob = R.load()
    R.set_basecolor("/home/claude/tanu/new_sharp_basecolor.png")
    weld_and_fill(ob); flatten_crease(ob); cut(ob)
    smooth_boundary(ob, iters=14, strength=0.7); mouth_bag(ob)
    n = len(ob.data.vertices); a = np.empty(n * 3, np.float32)
    ob.data.vertices.foreach_get("co", a); co = a.reshape(n, 3)
    add_tongue(None, surface_y_at_mouth(co))
    ob.shape_key_add(name="Basis", from_mix=False)
    ob.data.shape_keys.key_blocks["Basis"].data.foreach_set(
        "co", sealed(co).astype(np.float32).ravel())
    if open_key:
        k = ob.shape_key_add(name=open_key, from_mix=False)
        k.data.foreach_set("co", viseme_pose(co, open_key).astype(np.float32).ravel())
        k.value = 1.0
    R.setup('BLENDER_WORKBENCH', res=res)
    cam = R.camera(55)
    R.shot(out, cam, (-0.03, 0, 0.355), 0, 0, 1.45)

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cx",    nargs="*", type=float, default=[-0.036])
    p.add_argument("--cz",    nargs="*", type=float, default=[0.3038])
    p.add_argument("--hw",    nargs="*", type=float, default=[0.132])
    p.add_argument("--scale", nargs="*", type=float, default=[1.0])
    p.add_argument("--open",  default=None, choices=[None, "A", "I", "U", "E", "O"])
    p.add_argument("--out",   default="/home/claude/tanu/mouth_tuner.png")
    a = p.parse_args()

    combos = list(itertools.product(a.cx, a.cz, a.hw, a.scale))
    print(f"rendering {len(combos)} variants…")
    tiles = []
    for i, (cx, cz, hw, sc) in enumerate(combos):
        f = f"/tmp/tune_{i:02d}.png"
        render_variant(cx, cz, hw, sc, a.open, f)
        tiles.append((f, f"cx={cx:+.3f} cz={cz:.4f} hw={hw:.3f} x{sc:.2f}"))
        print(f"  {i+1}/{len(combos)}  {tiles[-1][1]}")

    from PIL import Image, ImageDraw, ImageFont
    F = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    fnt = ImageFont.truetype(F, 15)
    crop = (150, 170, 470, 450)
    ims = [(Image.open(f).convert("RGB").crop(crop), t) for f, t in tiles]
    cols = min(3, len(ims)); rows = (len(ims) + cols - 1) // cols
    w, h = ims[0][0].size
    sheet = Image.new("RGB", (w * cols + 6 * (cols - 1), (h + 22) * rows), (248, 248, 248))
    d = ImageDraw.Draw(sheet)
    for i, (im, t) in enumerate(ims):
        x = (i % cols) * (w + 6); y = (i // cols) * (h + 22)
        sheet.paste(im, (x, y)); d.text((x + 4, y + h + 4), t, font=fnt, fill=(25, 25, 25))
    sheet.save(a.out)
    print("wrote", a.out)

if __name__ == "__main__":
    main()
