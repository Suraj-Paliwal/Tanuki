"""Paint viseme mouths onto the base-colour texture by 3D projection.

The GLB's UV atlas is auto-generated and fragmented, so the mouth is scattered
across dozens of tiny islands. Painting by island is hopeless; instead every
mouth-region texel carries its baked 3D position, and the mouth is drawn as a
function of that position. Island boundaries stop mattering.
"""
import numpy as np
from scipy.spatial import cKDTree
from visemes import uw, uw_fit, FIT, VISEMES, HW, C_INNER, C_THROAT, C_TONGUE, C_LIP, C_TEETH

def local_coords(P):
    """Local to the NEW mouth - used when painting the new lip line."""
    return uw(P)

def local_fit(P):
    """Local to the ORIGINAL smile - used when erasing it. These diverge as
    soon as the mouth is moved, and erasing on the wrong one leaves a ghost."""
    return uw_fit(P)

def erase_smile(tex, pos, cov, band=0.028, src_lo=0.034, src_hi=0.095, k=48):
    """Remove the painted-on smile, filling from clean muzzle fur.

    Three things this has to get right, all learned the hard way:

    - Fill from the SAME SIDE of the lip line. The muzzle runs cream below and
      tan above; pulling from both sides smears one into the other.
    - Weight the k neighbours by distance rather than taking a plain median.
      Near the mouth corners the source set thins out, and an unweighted median
      there produces the blocky jagged patch that looked like torn geometry.
    - Feather the edge of the band. A hard swap between filled and original
      pixels leaves a visible seam exactly where the old smile ended.
    """
    ys, xs = np.nonzero(cov)
    P = pos[cov]
    s, w = local_fit(P)
    face = (np.abs(s) < FIT["hw"] + 0.030) & (np.abs(w) < 0.110) & (P[:, 1] < -0.34)
    out = tex.astype(np.float32).copy()
    for sign in (+1, -1):
        src = face & (np.abs(w) >= src_lo) & (np.abs(w) <= src_hi) & (np.sign(w) == sign)
        sel = face & (np.abs(w) < band) & ((np.sign(w) == sign) | (np.abs(w) < 0.004))
        if src.sum() < k or sel.sum() == 0:
            continue
        tree = cKDTree(P[src])
        d, idx = tree.query(P[sel], k=k)
        cols = tex[ys[src][idx], xs[src][idx]].astype(np.float32)      # (n,k,3)
        wgt = 1.0 / (d + 1e-4) ** 2
        wgt /= wgt.sum(1, keepdims=True)
        fill = (cols * wgt[..., None]).sum(1)
        # feather: full fill on the line, tapering to nothing at the band edge
        a = np.clip(1.0 - (np.abs(w[sel]) / band) ** 2, 0, 1)[:, None]
        out[ys[sel], xs[sel]] = out[ys[sel], xs[sel]] * (1 - a) + fill * a
    return np.clip(out, 0, 255).astype(np.uint8)

def _feather(d, edge):
    """d < 0 inside. Returns 1 inside, 0 outside, smooth across `edge`."""
    return np.clip(0.5 - d / edge, 0.0, 1.0)

def paint_mouth(tex, pos, cov, viseme, strength=1.0):
    """Composite one viseme's open mouth onto an already-erased texture."""
    v = VISEMES[viseme] if isinstance(viseme, str) else viseme
    ys, xs = np.nonzero(cov)
    P = pos[cov]
    s, w = local_coords(P)
    front = (P[:, 1] < -0.38) & (np.abs(s) < HW + 0.012)
    rx, rz, wc = v["rx"], v["rz"], v["wc"]
    # signed-ish distance to the opening ellipse, in metres
    q = np.sqrt((s / rx) ** 2 + ((w - wc) / rz) ** 2)
    d = (q - 1.0) * min(rx, rz)
    out = tex.astype(np.float32).copy()

    def blend(mask_alpha, colour):
        a = (mask_alpha * strength)[:, None]
        if a.max() <= 0: return
        out[ys, xs] = out[ys, xs] * (1 - a) + np.array(colour, np.float32) * a

    # lip ring just outside the opening
    blend(front * _feather(np.abs(d) - 0.007, 0.006) * 0.85, C_LIP)
    # mouth interior
    inner = front * _feather(d, 0.004)
    blend(inner, C_INNER)
    # throat shading: darker toward the upper-centre of the opening
    depth = np.clip(1.0 - q, 0, 1) ** 0.7
    blend(inner * depth * 0.75 * np.clip((w - wc) / rz + 0.4, 0, 1), C_THROAT)
    # tongue filling the lower part of the opening
    tw = (w - wc) / rz
    blend(inner * _feather(tw + 0.30, 0.35) * 0.95, C_TONGUE)
    # upper teeth band
    if v.get("teeth", 0) > 0:
        band = inner * _feather(0.92 - tw, 0.25)
        blend(band * 0.95, C_TEETH)
    return np.clip(out, 0, 255).astype(np.uint8)

def paint_smile(tex, pos, cov, hw=None, width=0.0065, darkness=0.90,
                fade_lo=0.88, fade_hi=1.04):
    """Draw a clean lip line along the whole mouth, on the NEW curve.

    Erasing the original smile leaves the muzzle blank, and a blank muzzle is
    most of why the closed face reads as artificial - a shut mouth should still
    show a mouth.

    The middle of this line sits where the hole is, so the only part you ever
    see is the outer half running to the corners. The fade therefore has to
    start very late: fading from halfway out, which is the natural-looking
    choice, fades away precisely the segment that is visible and the mouth goes
    blank again.
    """
    import numpy as np
    from visemes import MOUTH
    hw = hw if hw is not None else MOUTH["hw"]
    ys, xs = np.nonzero(cov)
    P = pos[cov]
    s, w = local_coords(P)
    front = P[:, 1] < -0.36
    t = np.clip(np.abs(s) / hw, 0, 1)
    fade = np.clip((fade_hi - t) / (fade_hi - fade_lo), 0, 1)
    a = front * _feather(np.abs(w) - width * 0.5, width) * fade * darkness
    out = tex.astype(np.float32).copy()
    aa = np.clip(a, 0, 1)[:, None]
    out[ys, xs] = out[ys, xs] * (1 - aa) + np.array(C_LIP, np.float32) * aa
    return np.clip(out, 0, 255).astype(np.uint8)


def paint_lips(tex, pos, cov, rx, rz, wc, ring=0.007, shadow=0.022):
    """Static lip ring + inner shadow around the cut opening.

    With a real hole in the mesh, only the *shape* has to be geometry. Lip
    colour and the soft shadow where the muzzle turns into the mouth are the
    same in every viseme, so they can be baked into the texture and cost
    nothing at runtime.
    """
    import numpy as np
    ys, xs = np.nonzero(cov)
    P = pos[cov]
    s, w = local_coords(P)
    front = P[:, 1] < -0.36
    q = np.sqrt((s / rx) ** 2 + ((w - wc) / rz) ** 2)
    d = (q - 1.0) * min(rx, rz)
    out = tex.astype(np.float32).copy()
    def blend(a, colour):
        a = np.clip(a, 0, 1)[:, None]
        out[ys, xs] = out[ys, xs] * (1 - a) + np.array(colour, np.float32) * a
    # Only the rim matters: everything inside the opening is cut away, so
    # painting a dark interior there is wasted and can bleed outward past the
    # rim when the texture is filtered. Keep it to a thin ring and a shallow
    # contact shadow just outside it.
    blend(front * _feather(np.abs(d) - ring * 0.5, ring) * 0.35, C_LIP)
    blend(front * _feather(d - 0.002, shadow * 0.5) * 0.20, (58, 36, 34))
    return np.clip(out, 0, 255).astype(np.uint8)
