# -*- coding: utf-8 -*-
"""Mouth geometry and Japanese viseme definitions.

TWO curves, and keeping them apart matters
------------------------------------------
FIT   where the model's ORIGINAL painted smile actually is. Measured by
      overlaying candidate curves on calibrated renders. Used only for erasing
      that smile and for relaxing the sculpted groove it left behind.

MOUTH where the NEW mouth goes. Free to move. Everything downstream - the cut,
      the morph targets, the painted lip line - reads from here.

If you drive both from one curve, nudging the mouth also moves the eraser and
the old smile creeps back out from under it.
"""
import numpy as np

# ── the original smile, as measured. Don't change these. ───────────────────
FIT = dict(cx=-0.025, cz=0.3038, curv=2.90, hw=0.135)

# ── the new mouth. THIS is the tunable block. ──────────────────────────────
#   cx    horizontal centre. The nose sits at -0.041 and the muzzle centres on
#         -0.032, so a mouth at -0.025 reads as offset to the right.
#   cz    height of the lowest point of the mouth line
#   curv  how much the corners ride up: z = cz + curv * u^2
#   hw    half-width, centre to corner
#   scale overall size multiplier for every viseme opening
MOUTH = dict(cx=-0.036, cz=0.3038, curv=2.90, hw=0.132, scale=1.00)

def _line(cfg, x):
    u = np.clip(np.asarray(x) - cfg["cx"], -cfg["hw"], cfg["hw"])
    return cfg["cz"] + cfg["curv"] * u * u

def _uw(cfg, P):
    u = P[..., 0] - cfg["cx"]
    uc = np.clip(u, -cfg["hw"], cfg["hw"])
    return u, P[..., 2] - (cfg["cz"] + cfg["curv"] * uc * uc)

def uw(P):        return _uw(MOUTH, P)        # mouth-local (u, w)
def uw_fit(P):    return _uw(FIT, P)          # local to the ORIGINAL smile
def zline(x):     return _line(MOUTH, x)
def zline_fit(x): return _line(FIT, x)

# kept for older imports
XC, ZC, CURV, HW = MOUTH["cx"], MOUTH["cz"], MOUTH["curv"], MOUTH["hw"]

# The cut envelope is a MIDDLE size, not the largest viseme. One hole serves
# both the wide slit of I and the small purse of U; cutting at I's width forces
# U to contract its rim by most of the mouth's half-width, which crumples it.
MAXR = dict(rx=0.070 * MOUTH["scale"], rz=0.041 * MOUTH["scale"])

def _v(rx, rz, wc, corner, purse, teeth, open_):
    s = MOUTH["scale"]
    return dict(rx=rx*s, rz=rz*s, wc=wc*s, corner=corner*s,
                purse=purse*s, teeth=teeth*s, open=open_)

# rx, rz  half-size of the opening      wc  vertical offset from the lip line
# corner  lip corners out (+) / in (-)  purse  forward protrusion
# teeth   upper teeth band              open   jaw contribution
VISEMES = {
    "A": _v(0.066, 0.041, -0.009,  0.000,  0.000, 0.000, 1.00),
    "I": _v(0.098, 0.015,  0.001,  0.010, -0.008, 0.006, 0.32),
    "U": _v(0.036, 0.028, -0.003, -0.010,  0.018, 0.000, 0.48),
    "E": _v(0.082, 0.026, -0.003,  0.006,  0.000, 0.004, 0.58),
    "O": _v(0.049, 0.038, -0.007, -0.008,  0.018, 0.000, 0.74),
}
ORDER = ["A", "I", "U", "E", "O"]

C_INNER  = (34, 19, 21)
C_THROAT = (18,  9, 11)
C_TONGUE = (150, 74, 80)
C_LIP    = (74, 47, 44)
C_TEETH  = (238, 234, 224)
