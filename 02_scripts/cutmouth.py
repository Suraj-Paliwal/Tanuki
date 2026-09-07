"""Cut the mouth open and drop a mouth bag + tongue in behind it."""
import bpy, bmesh, numpy as np, sys
sys.path.insert(0,"/home/claude/tanu")
from visemes import uw, XC, ZC, MAXR
from geo import local, WC_ENV

def _in_mouth(co_arr, idx, qmax=1.9):
    """The source mesh is not watertight - the hat and several seams have
    their own open edges. Every boundary operation has to be restricted to
    the rim we just cut, or it rebuilds the whole model."""
    u, w, q = local(co_arr[idx])
    return q < qmax

def smooth_boundary(ob, iters=12, strength=0.65):
    """Relax the cut edge.

    The face is AI-generated triangle soup with no edge loops, so a hole cut
    through it comes out ragged. Averaging each boundary vertex toward its two
    boundary neighbours straightens the rim without touching the interior."""
    import bmesh
    import numpy as _np
    n = len(ob.data.vertices)
    arr = _np.empty(n*3, _np.float32); ob.data.vertices.foreach_get("co", arr)
    arr = arr.reshape(n, 3)
    ok = set(_np.nonzero(_in_mouth(arr, _np.arange(n)))[0].tolist())
    bm = bmesh.new(); bm.from_mesh(ob.data)
    for _ in range(iters):
        loop = [v for v in bm.verts if v.is_boundary and v.index in ok]
        if not loop: break
        upd = {}
        for v in loop:
            nb = [e.other_vert(v) for e in v.link_edges if e.is_boundary]
            if len(nb) < 2: continue
            avg = sum((n.co for n in nb), type(v.co)((0, 0, 0))) / len(nb)
            upd[v] = v.co.lerp(avg, strength)
        for v, c in upd.items(): v.co = c
    bm.to_mesh(ob.data); bm.free()

def cut(ob, margin=1.0):
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n*3, np.float32); me.vertices.foreach_get("co", co); co = co.reshape(n,3)
    u, w, q = local(co)
    front = co[:,1] < -0.36
    inside = (q < margin) & front
    bm = bmesh.new(); bm.from_mesh(me); bm.verts.ensure_lookup_table()
    kill = [f for f in bm.faces if all(inside[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=kill, context='FACES')
    bm.to_mesh(me); bm.free()
    return len(kill)

def mouth_bag(ob, depth=0.090, rings=(0.88, 0.60, 0.30), taper_z=0.55):
    """Extrude the hole's own rim inward to form the mouth cavity.

    Two earlier attempts placed a separate blob behind the face. A convex blob
    renders as a lit lump; a blob big enough to be concave pokes out through
    the chin. Extruding the rim itself avoids both: the cavity is welded to
    the lip line, so it can never separate from it and never escapes the head.
    Ring 0 *is* the rim, so when a viseme opens the lips the cavity mouth
    opens with them and no gap can appear.
    """
    import bmesh, mathutils
    me = ob.data
    import numpy as _np
    n = len(me.vertices)
    arr = _np.empty(n*3, _np.float32); me.vertices.foreach_get("co", arr)
    arr = arr.reshape(n, 3)
    ok = set(_np.nonzero(_in_mouth(arr, _np.arange(n)))[0].tolist())
    bm = bmesh.new(); bm.from_mesh(me)
    bm.edges.ensure_lookup_table(); bm.verts.ensure_lookup_table()
    bedges = [e for e in bm.edges if e.is_boundary and all(v.index in ok for v in e.verts)]
    if not bedges:
        bm.free(); return 0
    loop0 = list({v for e in bedges for v in e.verts})
    c = mathutils.Vector((0, 0, 0))
    for v in loop0: c += v.co
    c /= len(loop0)
    made = []
    cur = bedges
    for i, sc in enumerate(rings):
        ret = bmesh.ops.extrude_edge_only(bm, edges=cur)
        vs = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMVert)]
        es = [g for g in ret["geom"] if isinstance(g, bmesh.types.BMEdge) and g.is_boundary]
        made += [g for g in ret["geom"] if isinstance(g, bmesh.types.BMFace)]
        dy = depth * (i + 1) / len(rings)
        for v in vs:
            off = v.co - c
            v.co = mathutils.Vector((c.x + off.x * sc,
                                     v.co.y + dy,
                                     c.z + off.z * (sc * taper_z + (1 - taper_z))))
        cur = es
    fill = bmesh.ops.holes_fill(bm, edges=cur)
    made += [f for f in fill.get("faces", [])]
    # cavity faces look inward: we see the far wall through the opening
    bmesh.ops.recalc_face_normals(bm, faces=made)
    bmesh.ops.reverse_faces(bm, faces=made)
    m = bpy.data.materials.new("MouthInner"); m.use_nodes = True
    m.use_backface_culling = False
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (0.055, 0.019, 0.022, 1)
    b.inputs["Roughness"].default_value = 0.82
    me.materials.append(m); mi = len(me.materials) - 1
    for f in made:
        if f.is_valid: f.material_index = mi
    n = len(made)
    bm.to_mesh(me); bm.free()
    return n

def add_tongue(ob_co_center, y_surf):
    cx, cz = XC, ZC + WC_ENV
    bpy.ops.mesh.primitive_uv_sphere_add(segments=40, ring_count=20, radius=1.0,
                                         location=(cx, y_surf + 0.055, cz - 0.021))
    tn = bpy.context.object; tn.name = "Tongue"
    tn.scale = (0.052, 0.032, 0.012)
    m2 = bpy.data.materials.new("Tongue"); m2.use_nodes = True
    b2 = m2.node_tree.nodes["Principled BSDF"]
    b2.inputs["Base Color"].default_value = (0.44, 0.14, 0.155, 1)
    b2.inputs["Roughness"].default_value = 0.45
    tn.data.materials.append(m2)
    bpy.context.view_layer.objects.active = tn
    bpy.ops.object.transform_apply(scale=True); bpy.ops.object.shade_smooth()
    return tn

def surface_y_at_mouth(co):
    u, w = uw(co)
    near = (np.abs(u) < 0.05) & (np.abs(w - WC_ENV) < 0.03) & (co[:,1] < -0.36)
    return float(np.median(co[near,1])) if near.sum() else -0.50


def weld_and_fill(ob, dist=1e-5, max_sides=64):
    """Weld coincident vertices, then fill whatever holes are genuinely left.

    The source mesh reports 98,812 boundary edges, but almost none are real
    holes - they are UV seams stored as split vertices sitting at identical
    coordinates. Welding collapses those to 131. The handful that survive are
    actual gaps in the surface, and they have to be filled before any
    smoothing: relaxing the vertices around an open boundary drags it wider and
    turns a pinhole into the torn flap you can see beside the mouth.
    """
    import bmesh
    bm = bmesh.new(); bm.from_mesh(ob.data)
    before = sum(1 for e in bm.edges if e.is_boundary)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=dist)
    welded = sum(1 for e in bm.edges if e.is_boundary)
    holes = [e for e in bm.edges if e.is_boundary]
    if holes:
        bmesh.ops.holes_fill(bm, edges=holes, sides=max_sides)
    left = sum(1 for e in bm.edges if e.is_boundary)
    bm.to_mesh(ob.data); bm.free()
    return dict(before=before, after_weld=welded, after_fill=left)


def _weld(arr, edges, tol=1e-5):
    """Group coincident vertices and build adjacency over the groups.

    This mesh stores every UV seam as split vertices: one point on the surface
    exists two or three times at identical coordinates. Smoothing them
    independently pulls the twins apart and rips the seam open - which is
    exactly what a naive Laplacian pass does to this model. Welding first, then
    writing one result back to every twin, makes seams impossible to break.
    """
    import numpy as _np
    key = _np.round(arr / tol).astype(_np.int64)
    _, gid, inv = _np.unique(key, axis=0, return_index=True, return_inverse=True)
    g = inv                                   # group id per vertex
    ng = g.max() + 1
    ge = _np.unique(_np.sort(g[edges], axis=1), axis=0)
    ge = ge[ge[:, 0] != ge[:, 1]]
    return g, ng, ge


def _smooth_groups(pos, ge, ng, weight, iters, strength):
    """Laplacian iterations on welded groups, per-group weight in 0..1."""
    import numpy as _np
    a, b = ge[:, 0], ge[:, 1]
    deg = _np.bincount(a, minlength=ng) + _np.bincount(b, minlength=ng)
    deg = _np.maximum(deg, 1)[:, None]
    p = pos.copy()
    w = weight[:, None]
    for _ in range(iters):
        acc = _np.zeros_like(p)
        _np.add.at(acc, a, p[b])
        _np.add.at(acc, b, p[a])
        avg = acc / deg
        p = p + (avg - p) * (strength * w)
    return p


def relax_region(ob, weight_fn, iters=25, strength=0.6, tol=1e-5):
    """Weld-safe Laplacian relaxation. `weight_fn(arr) -> per-vertex 0..1`."""
    import numpy as _np
    me = ob.data
    n = len(me.vertices)
    arr = _np.empty(n * 3, _np.float32); me.vertices.foreach_get("co", arr)
    arr = arr.reshape(n, 3).astype(_np.float64)
    ne = len(me.edges)
    ev = _np.empty(ne * 2, _np.int32); me.edges.foreach_get("vertices", ev)
    edges = ev.reshape(ne, 2)

    g, ng, ge = _weld(arr, edges, tol)
    gpos = _np.zeros((ng, 3)); cnt = _np.bincount(g, minlength=ng)[:, None]
    _np.add.at(gpos, g, arr); gpos /= _np.maximum(cnt, 1)

    vw = _np.clip(weight_fn(arr), 0, 1)
    gw = _np.zeros(ng); _np.maximum.at(gw, g, vw)
    if gw.max() <= 0:
        return 0
    out = _smooth_groups(gpos, ge, ng, gw, iters, strength)
    me.vertices.foreach_set("co", out[g].astype(_np.float32).ravel())
    me.update()
    return int((gw > 1e-3).sum())


def flatten_crease(ob, iters=28, band=0.050, qmin=1.02, strength=0.55):
    """Smooth away the stumps of the original sculpted smile.

    The source smile is a groove about twice as wide as the hole cut for the
    visemes, so cutting the middle out leaves the outer thirds behind as two
    creases either side of the mouth. This relaxes that band back into the
    muzzle, fading to zero at the cut rim and at the mouth corners so no flat
    patch appears where the groove used to be.
    """
    import numpy as _np
    from visemes import uw, HW

    def weight(arr):
        u, w = uw(arr)
        _, _, q = local(arr)
        front = arr[:, 1] < -0.36
        tb = _np.clip(_np.abs(w - WC_ENV) / band, 0, 1)
        t_band = 1.0 - tb ** 3
        t_rim = _np.clip((q - qmin) / 0.30, 0, 1)
        t_out = 1.0 - _np.clip((_np.abs(u) - (HW - 0.02)) / 0.06, 0, 1)
        return t_band * t_rim * t_out * front

    return relax_region(ob, weight, iters=iters, strength=strength)
