# -*- coding: utf-8 -*-
import bpy, numpy as np, sys, os
sys.path.insert(0,"/home/claude/tanu"); sys.path.insert(0,"/home/claude/tanu/pipeline")
import renderlib as R
from geo import sealed, viseme_pose
from cutmouth import cut, smooth_boundary, mouth_bag, add_tongue, surface_y_at_mouth
from visemes import ORDER
from eyes import blink
from jp_lipsync import build
from apply_tracks import apply

OUTDIR = "/mnt/user-data/outputs/Tanuki/05_model"
os.makedirs(OUTDIR, exist_ok=True)

def get_co(ob):
    n=len(ob.data.vertices); a=np.empty(n*3,np.float32)
    ob.data.vertices.foreach_get("co",a); return a.reshape(n,3)

def swap_textures():
    """Point each map at its recompressed file.

    Matching by image name does not work here: the GLB's images arrive named
    Image_0/1/2 with no filepath, so a name test silently gives every slot the
    base colour. Follow the shader links instead - whatever feeds Base Color
    is the albedo, whatever feeds a Normal Map node is the normal, and
    whatever feeds Metallic/Roughness is the ORM map.
    """
    def load(f):
        return bpy.data.images.load("/home/claude/tanu/" + f, check_existing=True)
    def src_image(socket):
        if not socket.links: return None
        n = socket.links[0].from_node
        if n.type == 'TEX_IMAGE': return n
        if n.type == 'NORMAL_MAP': return src_image(n.inputs['Color'])
        if n.type == 'SEPARATE_COLOR': return src_image(n.inputs[0])
        for i in n.inputs:
            got = src_image(i)
            if got: return got
        return None
    for m in bpy.data.materials:
        if not m.use_nodes: continue
        bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not bsdf: continue
        for socket, f in [("Base Color", "opt_basecolor.jpg"),
                          ("Normal",     "opt_normal.jpg"),
                          ("Roughness",  "opt_metalrough.jpg"),
                          ("Metallic",   "opt_metalrough.jpg")]:
            if socket not in bsdf.inputs: continue
            node = src_image(bsdf.inputs[socket])
            if node: node.image = load(f)

ob = R.load()
cut(ob); smooth_boundary(ob, iters=14, strength=0.7); mouth_bag(ob)
co = get_co(ob)
t = add_tongue(None, surface_y_at_mouth(co))
bpy.ops.object.select_all(action='DESELECT')
t.select_set(True); ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.join()
co = get_co(ob)
swap_textures()

ob.shape_key_add(name="Basis", from_mix=False)
ob.data.shape_keys.key_blocks["Basis"].data.foreach_set("co", sealed(co).astype(np.float32).ravel())
base = sealed(co)
for v in ORDER:
    k = ob.shape_key_add(name=v, from_mix=False)
    k.data.foreach_set("co", viseme_pose(co, v).astype(np.float32).ravel())
    k.slider_min, k.slider_max, k.value = 0.0, 1.0, 0.0
# Eye keys are built from the SEALED base, not the raw mesh: a shape key
# stores absolute positions, so a blink built on the open-mouthed original
# would drag the mouth back open whenever it was blended in.
for nm, sides in [("Blink", ("L", "R")), ("BlinkL", ("L",)), ("BlinkR", ("R",))]:
    k = ob.shape_key_add(name=nm, from_mix=False)
    k.data.foreach_set("co", blink(base, sides).astype(np.float32).ravel())
    k.slider_min, k.slider_max, k.value = 0.0, 1.0, 0.0

bpy.ops.wm.save_as_mainfile(filepath=OUTDIR + "/tanuki_visemes.blend", compress=True)
bpy.ops.export_scene.gltf(filepath=OUTDIR + "/tanuki_visemes.glb",
                          export_format='GLB', export_morph=True,
                          export_morph_normal=False, export_animations=False)
print("rig exported", os.path.getsize(OUTDIR + "/tanuki_visemes.glb")//1024, "KB")

# animated copy: the same rig with こんにちは、たぬきです baked in
sc = bpy.context.scene; sc.render.fps = 30
data = build("こんにちは、たぬきです", fps=30, blink=True)
last = apply(ob, data, 30)
sc.frame_start, sc.frame_end = 1, last
bpy.ops.export_scene.gltf(filepath=OUTDIR + "/tanuki_demo_konnichiwa.glb",
                          export_format='GLB', export_morph=True,
                          export_morph_normal=False, export_animations=True,
                          export_frame_range=True)
print("animated exported", os.path.getsize(OUTDIR + "/tanuki_demo_konnichiwa.glb")//1024, "KB")
