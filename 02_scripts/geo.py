"""Geometry side of the viseme rig.

The mouth is cut once to an envelope large enough for every viseme. The
exported BASE mesh is the mouth *closed* - the rim is collapsed onto the lip
line so the hole has near-zero area and reads as the original smile. Each
viseme is then a morph target that re-opens the rim to its own size, which is
the shape glTF morph targets need: everything blends from the neutral pose.

Deformation is expressed as bounded *rim displacement*, not as a rescaling of
the local coordinates. Rescaling u and w over the falloff region moves distant
vertices by a fraction of their own (large) coordinate, which tears the whole
muzzle apart; rim displacement is capped by the difference between two mouth
sizes, a few millimetres at most.
"""
import numpy as np
from visemes import uw, MOUTH, VISEMES, MAXR
XC, ZC, CURV, HW = MOUTH['cx'], MOUTH['cz'], MOUTH['curv'], MOUTH['hw']

WC_ENV = -0.006          # centre of the cut envelope in w
RX, RZ = MAXR["rx"], MAXR["rz"]
Q_OUT  = 2.05            # past this q the face is untouched
SEAL   = 0.018           # residual opening of the sealed base

def local(co):
    u, w = uw(co)
    q = np.sqrt((u / RX) ** 2 + ((w - WC_ENV) / RZ) ** 2)
    return u, w, q

def front_mask(co):
    """Only the front of the muzzle may move. Without this the jaw term
    reaches the whole lower body - the character has no neck, so 'below the
    mouth line' is most of the model."""
    return (co[:, 1] < -0.34) & (np.abs(co[:, 0] - XC) < 0.34) & (co[:, 2] > 0.16) & (co[:, 2] < 0.52)

def decay(q):
    """1 at the rim, 0 outside Q_OUT, smooth."""
    t = np.clip((q - 1.0) / (Q_OUT - 1.0), 0.0, 1.0)
    return 1.0 - t * t * (3 - 2 * t)

def displace(co, rx, rz, wc, purse=0.0, corner=0.0, jaw=0.0, dent=0.0):
    """Absolute positions for one mouth state.

    rx, rz, wc  target opening; the rim moves from the envelope to this shape
    purse       forward (-Y) lip protrusion
    corner      lip corners slide out (+) / purse in (-)
    jaw         small downward pull below the mouth
    dent        push the surface *inside* the opening back into the head
                (only meaningful when the mouth has not been cut)
    """
    P = co.copy()
    u, w, q = local(co)
    # direction of each vertex around the rim
    cu = u / RX
    cw = (w - WC_ENV) / RZ
    n = np.maximum(np.sqrt(cu * cu + cw * cw), 1e-9)
    cu, cw = cu / n, cw / n                     # unit (cos, sin) around the ellipse
    # where that rim direction lands on the target opening vs the envelope
    du = (rx - RX) * cu
    dw = (wc - WC_ENV) + (rz - RZ) * cw
    k = decay(q)
    inside = q < 1.0
    k = np.where(inside, q * 0.85 + 0.15, k)    # inside the hole, ease toward the centre
    k = k * front_mask(co)                      # never touch the back of the head
    P[:, 0] += du * k
    P[:, 2] += dw * k
    # lip corners
    if corner:
        P[:, 0] += corner * k * np.sign(u) * np.clip(np.abs(cu), 0, 1) ** 2
    # forward lip protrusion
    if purse:
        P[:, 1] -= purse * k
    # jaw drop under the mouth, on its own local falloff
    if jaw:
        below = np.clip((WC_ENV - w) / 0.075, 0, 1)
        chin  = np.exp(-((u / 0.17) ** 2 + ((w - WC_ENV) / 0.115) ** 2)) * front_mask(co)
        P[:, 2] -= jaw * below * chin
    # dent the sealed surface inward so a closed mouth still reads as open
    if dent:
        P[:, 1] += dent * np.clip(1.0 - q * q, 0, 1) ** 0.8
    return P

def sealed(co):
    """Closed base pose: rim collapsed to a slit on the lip line, with the
    lips pushed very slightly forward so they overlap rather than meet
    exactly - an exact meeting lets the mouth bag show through."""
    return displace(co, RX, RZ * SEAL, WC_ENV, purse=0.004)

def viseme_pose(co, name, dent=0.0):
    v = VISEMES[name]
    return displace(co, v["rx"], v["rz"], WC_ENV + v["wc"],
                    purse=v["purse"], corner=v["corner"],
                    jaw=0.011 * v["open"], dent=dent * v["open"])

def viseme_delta(co, name, dent=0.0):
    """Morph-target delta measured from the sealed base."""
    return viseme_pose(co, name, dent) - sealed(co)
