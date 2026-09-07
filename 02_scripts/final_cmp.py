import bpy, numpy as np, sys
sys.path.insert(0,"/home/claude/tanu")
import renderlib as R
from geo import sealed, viseme_pose
from cutmouth import cut, smooth_boundary, mouth_bag, add_tongue, surface_y_at_mouth
from visemes import ORDER
RES, SAMP, DIST = 560, 12, 1.15
def get_co(ob):
    n=len(ob.data.vertices); a=np.empty(n*3,np.float32)
    ob.data.vertices.foreach_get("co",a); return a.reshape(n,3)

# ---- A : texture swap ----
ob=R.load(); R.setup('BLENDER_EEVEE',res=RES,samples=SAMP); R.eevee_scene(0.5)
cam=R.camera(55)
for tag,f in [("closed","basecolor"),("A","A"),("I","I"),("U","U"),("E","E"),("O","O")]:
    R.set_basecolor(f"/home/claude/tanu/tex_{f}.jpg")
    R.shot(f"/home/claude/tanu/FA_{tag}.png",cam,R.FACE,0,0,DIST)

# ---- B : cut open + cavity ----
ob=R.load(); R.set_basecolor("/home/claude/tanu/tex_lips.jpg")
cut(ob); smooth_boundary(ob,iters=14,strength=0.7); mouth_bag(ob)
co=get_co(ob); add_tongue(None, surface_y_at_mouth(co))
ob.shape_key_add(name="Basis",from_mix=False)
ob.data.shape_keys.key_blocks["Basis"].data.foreach_set("co",sealed(co).astype(np.float32).ravel())
for v in ORDER:
    k=ob.shape_key_add(name=v,from_mix=False); k.data.foreach_set("co",viseme_pose(co,v).astype(np.float32).ravel())
bpy.ops.wm.save_as_mainfile(filepath="/home/claude/tanu/tanu_visemes.blend")
R.setup('BLENDER_EEVEE',res=RES,samples=SAMP); R.eevee_scene(0.5)
cam=R.camera(55); kb=ob.data.shape_keys.key_blocks
for v in ORDER: kb[v].value=0.0
R.shot("/home/claude/tanu/FB_closed.png",cam,R.FACE,0,0,DIST)
for v in ORDER:
    for x in ORDER: kb[x].value=0.0
    kb[v].value=1.0
    R.shot(f"/home/claude/tanu/FB_{v}.png",cam,R.FACE,0,0,DIST)

# ---- C : closed deform ----
ob=R.load(); R.set_basecolor("/home/claude/tanu/tex_basecolor.jpg")
co=get_co(ob); ob.shape_key_add(name="Basis",from_mix=False)
for v in ORDER:
    k=ob.shape_key_add(name=v,from_mix=False)
    k.data.foreach_set("co",viseme_pose(co,v,dent=0.045).astype(np.float32).ravel())
R.setup('BLENDER_EEVEE',res=RES,samples=SAMP); R.eevee_scene(0.5)
cam=R.camera(55); kb=ob.data.shape_keys.key_blocks
R.shot("/home/claude/tanu/FC_closed.png",cam,R.FACE,0,0,DIST)
for v in ORDER:
    for x in ORDER: kb[x].value=0.0
    kb[v].value=1.0
    R.shot(f"/home/claude/tanu/FC_{v}.png",cam,R.FACE,0,0,DIST)
print("done")
