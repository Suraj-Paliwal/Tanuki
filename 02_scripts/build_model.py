# -*- coding: utf-8 -*-
"""Build the rigged tanuki and export it for the web.

Pipeline, in the order that matters:

  1. weld + fill   The source stores every UV seam as split vertices - 98,812
                   boundary edges that are not really holes. Welding collapses
                   them to 131 and closes a real crack beside the mouth.
                   Everything after this depends on it: smoothing a mesh with
                   split vertices tears the seams open.
  2. relax crease  The original sculpted smile is twice as wide as the hole we
                   cut, so its outer thirds would be left behind as two scars.
  3. cut           Remove the faces inside the mouth envelope.
  4. smooth rim    Straighten the ragged cut edge.
  5. cavity        Extrude the rim inward; a mouth interior welded to the lips.
  6. tongue        Small separate blob, joined so morphs carry it.
  7. shape keys    Base pose = mouth SEALED. Every viseme opens from there.
"""
import bpy, numpy as np, sys, os, shutil, json
sys.path.insert(0, "/home/claude/tanu")
import renderlib as R
from geo import sealed, viseme_pose
from cutmouth import (weld_and_fill, flatten_crease, cut, smooth_boundary,
                      mouth_bag, add_tongue, surface_y_at_mouth)
from visemes import ORDER, MOUTH
from eyes import blink

OUT = "/mnt/user-data/outputs/Tanuki/07_web_model"

def get_co(ob):
    n = len(ob.data.vertices); a = np.empty(n * 3, np.float32)
    ob.data.vertices.foreach_get("co", a); return a.reshape(n, 3)

def route_textures(files):
    """Assign maps by shader link, not by image name: the imported images are
    called Image_0/1/2 with no filepath, so a name test gives every slot the
    albedo."""
    def load(f): return bpy.data.images.load("/home/claude/tanu/" + f, check_existing=True)
    def src(sock):
        if not sock.links: return None
        n = sock.links[0].from_node
        if n.type == 'TEX_IMAGE': return n
        if n.type == 'NORMAL_MAP': return src(n.inputs['Color'])
        if n.type == 'SEPARATE_COLOR': return src(n.inputs[0])
        for i in n.inputs:
            g = src(i)
            if g: return g
        return None
    for m in bpy.data.materials:
        if not m.use_nodes: continue
        b = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not b: continue
        for sock, f in files:
            if sock in b.inputs:
                node = src(b.inputs[sock])
                if node: node.image = load(f)

def build(textures=None):
    ob = R.load()
    print("  weld+fill      ", weld_and_fill(ob))
    print("  crease relaxed ", flatten_crease(ob))
    print("  faces cut      ", cut(ob))
    smooth_boundary(ob, iters=14, strength=0.7)
    print("  cavity faces   ", mouth_bag(ob))
    co = get_co(ob)
    t = add_tongue(None, surface_y_at_mouth(co))
    bpy.ops.object.select_all(action='DESELECT')
    t.select_set(True); ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()
    co = get_co(ob)
    if textures: route_textures(textures)

    base = sealed(co)
    ob.shape_key_add(name="Basis", from_mix=False)
    ob.data.shape_keys.key_blocks["Basis"].data.foreach_set(
        "co", base.astype(np.float32).ravel())
    for v in ORDER:
        k = ob.shape_key_add(name=v, from_mix=False)
        k.data.foreach_set("co", viseme_pose(co, v).astype(np.float32).ravel())
        k.slider_min, k.slider_max, k.value = 0.0, 1.0, 0.0
    # Eye keys come off the SEALED base: a shape key stores absolute positions,
    # so a blink built on the open-mouthed mesh reopens the mouth when blended.
    for nm, sides in [("Blink", ("L", "R")), ("BlinkL", ("L",)), ("BlinkR", ("R",))]:
        k = ob.shape_key_add(name=nm, from_mix=False)
        k.data.foreach_set("co", blink(base, sides).astype(np.float32).ravel())
        k.slider_min, k.slider_max, k.value = 0.0, 1.0, 0.0
    print("  verts          ", len(co))
    return ob

if __name__ == "__main__":
    shutil.rmtree(OUT, ignore_errors=True); os.makedirs(OUT, exist_ok=True)
    print("mouth config:", MOUTH)
    build([("Base Color", "new_sharp_basecolor.png"),
           ("Normal",     "sharp_normal.png"),
           ("Roughness",  "hq_metalrough.png"),
           ("Metallic",   "hq_metalrough.png")])
    bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, "tanuki"),
                              export_format='GLTF_SEPARATE', export_morph=True,
                              export_morph_normal=False, export_animations=False)
    print("exported ->", sorted(os.listdir(OUT)))
