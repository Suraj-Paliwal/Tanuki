"""Build the rigged tanuki and export it as GLB with viseme morph targets."""
import bpy, numpy as np, sys
sys.path.insert(0,"/home/claude/tanu")
import renderlib as R
from geo import sealed, viseme_pose
from cutmouth import cut, smooth_boundary, mouth_bag, add_tongue, surface_y_at_mouth
from visemes import ORDER

OUT = "/home/claude/tanu/tanuki_visemes.glb"

def get_co(ob):
    n=len(ob.data.vertices); a=np.empty(n*3,np.float32)
    ob.data.vertices.foreach_get("co",a); return a.reshape(n,3)

ob = R.load()
R.set_basecolor("/home/claude/tanu/tex_lips.jpg")
print("cut faces      :", cut(ob))
smooth_boundary(ob, iters=14, strength=0.7)
print("cavity faces   :", mouth_bag(ob))

co = get_co(ob)
tongue = add_tongue(None, surface_y_at_mouth(co))
# join the tongue in so it is covered by the morph targets and travels with
# the jaw instead of hanging in space when the mouth opens
bpy.ops.object.select_all(action='DESELECT')
tongue.select_set(True); ob.select_set(True)
bpy.context.view_layer.objects.active = ob
bpy.ops.object.join()
co = get_co(ob)
print("verts after join:", len(co))

ob.shape_key_add(name="Basis", from_mix=False)
ob.data.shape_keys.key_blocks["Basis"].data.foreach_set(
    "co", sealed(co).astype(np.float32).ravel())
for v in ORDER:
    k = ob.shape_key_add(name=v, from_mix=False)
    k.data.foreach_set("co", viseme_pose(co, v).astype(np.float32).ravel())
    k.slider_min, k.slider_max = 0.0, 1.0
    k.value = 0.0        # otherwise the GLB ships with every viseme at 1.0
                         # and the model loads with all five mouths at once
print("shape keys     :", [k.name for k in ob.data.shape_keys.key_blocks])

bpy.ops.wm.save_as_mainfile(filepath="/home/claude/tanu/tanuki_visemes.blend")
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB',
                          export_morph=True, export_morph_normal=False,
                          export_apply=False)
print("exported", OUT)
