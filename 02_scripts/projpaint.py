"""Rasterise the mouth-region triangles into UV space so the 2048x2048 texture
can be painted by 3D position instead of by UV island (the atlas is fragmented)."""
import numpy as np, sys
sys.path.insert(0,"/home/claude/tanu")
from mouthlib import mouth_points, dist_to_mouth

def build_texel_map(co, tris, uvs, size=2048, region_mask=None):
    """tris: (T,3) vertex indices. uvs: (T,3,2) per-corner UV.
    Returns pos (size,size,3) float32 and cov (size,size) bool."""
    pos = np.zeros((size,size,3), np.float32)
    cov = np.zeros((size,size), bool)
    P = co[tris]                                   # (T,3,3)
    px = uvs[...,0]*size
    py = (1.0-uvs[...,1])*size
    x0 = np.floor(px.min(1)).astype(int); x1 = np.ceil(px.max(1)).astype(int)
    y0 = np.floor(py.min(1)).astype(int); y1 = np.ceil(py.max(1)).astype(int)
    for i in range(len(tris)):
        ax,bx,cx = px[i]; ay,by,cy = py[i]
        den = (by-cy)*(ax-cx) + (cx-bx)*(ay-cy)
        if abs(den) < 1e-12: continue
        X0=max(x0[i]-1,0); X1=min(x1[i]+2,size); Y0=max(y0[i]-1,0); Y1=min(y1[i]+2,size)
        if X0>=X1 or Y0>=Y1: continue
        gx,gy = np.meshgrid(np.arange(X0,X1)+0.5, np.arange(Y0,Y1)+0.5)
        l1 = ((by-cy)*(gx-cx) + (cx-bx)*(gy-cy))/den
        l2 = ((cy-ay)*(gx-cx) + (ax-cx)*(gy-cy))/den
        l3 = 1.0-l1-l2
        m = (l1>=-0.002)&(l2>=-0.002)&(l3>=-0.002)
        if not m.any(): continue
        p = (l1[m,None]*P[i,0] + l2[m,None]*P[i,1] + l3[m,None]*P[i,2])
        ys = gy[m].astype(int); xs = gx[m].astype(int)
        pos[ys,xs] = p; cov[ys,xs] = True
    return pos, cov

def select_region(co, tris, curve, radius):
    d = dist_to_mouth(co, curve)
    return (d[tris] < radius).any(1), d
