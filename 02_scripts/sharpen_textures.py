# -*- coding: utf-8 -*-
"""Edge-aware sharpening for the tanuki's texture maps.

The face occupies about 287x287 texels of the source atlas, so on screen it is
always magnified. Bilinear magnification of a soft source is what reads as
"blurry". Sharpening the texture beforehand costs nothing at runtime and
recovers most of the perceived crispness.

Tested against a 4096 Lanczos upscale: the extra resolution added almost
nothing on top of the sharpening, so this stays at 2048 and the GPU keeps its
VRAM.
"""
import numpy as np
from PIL import Image, ImageFilter

def edge_sharpen(img, radius=1.1, base=0.55, edge=1.15, edge_scale=5.0):
    """Unsharp mask weighted by local gradient.

    A flat unsharp mask over the whole atlas turns the fur into noise and rings
    the nose with a dark halo. Weighting by gradient magnitude concentrates the
    effect on real boundaries - mask edges, the nose, the eye rims - and leaves
    smooth areas alone.
    """
    a = np.asarray(img).astype(np.float32)
    det = a - np.asarray(img.filter(ImageFilter.GaussianBlur(radius))).astype(np.float32)
    g = np.asarray(img.convert('L').filter(ImageFilter.FIND_EDGES)).astype(np.float32)
    g = np.asarray(Image.fromarray(g.astype(np.uint8))
                   .filter(ImageFilter.GaussianBlur(1.0))).astype(np.float32)
    w = np.clip(g / edge_scale, 0, 1)[..., None]
    return Image.fromarray(np.clip(a + det * (base + edge * w), 0, 255).astype(np.uint8))

if __name__ == "__main__":
    import os
    base = Image.open('hq_basecolor.png').convert('RGB')
    edge_sharpen(base).save('sharp_basecolor.png')
    # Normal maps are a vector field, not a picture - over-sharpening one makes
    # the lighting swim. Gentle settings only.
    nrm = Image.open('hq_normal.png').convert('RGB')
    edge_sharpen(nrm, radius=0.9, base=0.25, edge=0.5, edge_scale=7.0).save('sharp_normal.png')
    for a, b, q in [('sharp_basecolor.png','sharp_basecolor.webp',94),
                    ('sharp_normal.png','sharp_normal.webp',94),
                    ('hq_metalrough.png','sharp_metalrough.webp',90)]:
        Image.open(a).convert('RGB').save(b,'WEBP',quality=q,method=6)
        print(f"  {b:26s} {Image.open(b).size[0]}px  {os.path.getsize(b)//1024} KB")
