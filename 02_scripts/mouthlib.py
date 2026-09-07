"""Shared mouth geometry helpers for the tanuki viseme rig."""
import numpy as np

# Mouth centre-line, fitted to the painted smile + verified against markers.
# Parametrised by t in [-1, 1] (left corner -> right corner).
MOUTH_HALF_W = 0.112      # x at the corners
MOUTH_Z_BOT  = 0.325      # z at centre of the smile
MOUTH_Z_CURV = 4.35       # z = Z_BOT + CURV * x^2  (corners ride up)
NOSE_Z       = 0.414
JAW_PIVOT    = np.array([0.0, -0.16, 0.455])   # hinge for the small jaw drop

def mouth_curve(t):
    """t in [-1,1] -> (x, z) on the smile line."""
    t = np.asarray(t, dtype=np.float64)
    x = MOUTH_HALF_W * t
    z = MOUTH_Z_BOT + MOUTH_Z_CURV * x**2
    return x, z

def snap_to_face(co, x, z, r=0.030, front_pct=15):
    """Nearest FRONT-of-muzzle surface point to a target (x, z).
    Returns real surface positions - composing (x, min_y, z) floats the
    point off a curved surface, which is what broke the first fit."""
    out = []
    for xi, zi in zip(np.atleast_1d(x), np.atleast_1d(z)):
        m = (np.abs(co[:,0]-xi) < r) & (np.abs(co[:,2]-zi) < r) & (co[:,1] < -0.20)
        s = co[m]
        if len(s) == 0:
            out.append([xi, np.nan, zi]); continue
        s = s[s[:,1] <= np.percentile(s[:,1], front_pct)]
        k = np.argmin((s[:,0]-xi)**2 + (s[:,2]-zi)**2)
        out.append(s[k])
    return np.array(out, dtype=np.float64)

def mouth_points(co, n=25):
    """Sampled 3D points along the mouth line, snapped to the surface."""
    t = np.linspace(-1, 1, n)
    x, z = mouth_curve(t)
    return snap_to_face(co, x, z)

def dist_to_mouth(co, curve):
    """Per-vertex distance to the mouth centre-line (min over sampled points)."""
    d = np.full(len(co), 1e9, dtype=np.float32)
    for p in curve:
        d = np.minimum(d, np.linalg.norm(co - p, axis=1))
    return d

def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t*t*(3 - 2*t)
