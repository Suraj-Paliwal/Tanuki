# -*- coding: utf-8 -*-
"""Blink morph targets.

The tanuki has no eyelids. The eyes are near-flat domes with the iris, pupil
and highlight painted straight onto them, so there is no lid geometry to
rotate down. What works instead is collapsing each eye vertically onto a line:
because the iris is painted on the surface, squashing the surface squashes the
painted eye with it, which is exactly how a cartoon blink reads.

The collapse line sits slightly above centre rather than through it, so the
motion looks like an upper lid coming down instead of the eye imploding.
"""
import numpy as np

# fitted by overlaying candidate ellipses on calibrated renders; the face is
# asymmetric, so the two eyes do not mirror
EYES = {
    "L": dict(cx=-0.229, cz=0.519, rx=0.077, rz=0.087),
    "R": dict(cx= 0.157, cz=0.519, rx=0.080, rz=0.086),
}
Q_OUT = 1.45      # lid skin still moves a little out to here
SLIT  = 0.032     # how much vertical extent survives when fully closed
LIDUP = 0.02      # closure line, as a fraction of rz above the eye centre
                  # (near centre on purpose: the surface collapses onto this
                  # line, so putting it through the dark iris gives a dark
                  # closed eye instead of a bright sliver of sclera)
FLAT  = 0.014     # how far the dome sinks back into the socket
DROP  = 0.007     # the whole lid area settles slightly downward

def _q(co, e):
    return np.sqrt(((co[:, 0] - e["cx"]) / e["rx"]) ** 2 +
                   ((co[:, 2] - e["cz"]) / e["rz"]) ** 2)

def blink(co, sides=("L", "R"), amount=1.0):
    """Absolute positions with the named eyes closed."""
    P = co.copy()
    front = co[:, 1] < -0.12
    for s in sides:
        e = EYES[s]
        q = _q(co, e)
        t = np.clip((q - 1.0) / (Q_OUT - 1.0), 0.0, 1.0)
        k = (1.0 - t * t * (3 - 2 * t)) * front * amount
        if not k.any():
            continue
        z_lid = e["cz"] + e["rz"] * LIDUP
        shrink = SLIT + (1.0 - SLIT) * (1.0 - k)
        P[:, 2] = np.where(k > 0, z_lid + (P[:, 2] - z_lid) * shrink, P[:, 2])
        P[:, 2] -= DROP * k
        P[:, 1] += FLAT * k * np.clip(1.0 - (q / Q_OUT) ** 2, 0, 1)
    return P
