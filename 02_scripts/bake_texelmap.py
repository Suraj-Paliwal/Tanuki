import bpy, numpy as np, sys, time
sys.path.insert(0,"/home/claude/tanu")
from mouthlib import mouth_points, dist_to_mouth
from projpaint import build_texel_map
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath="/home/claude/tanu/tanu_base.glb")
m=[o for o in bpy.data.objects if o.type=='MESH'][0].data
nv=len(m.vertices); nl=len(m.loops); nt=len(m.polygons)
co=np.empty(nv*3,np.float32); m.vertices.foreach_get("co",co); co=co.reshape(nv,3)
lv=np.empty(nl,np.int32); m.loops.foreach_get("vertex_index",lv)
uv=np.empty(nl*2,np.float32); m.uv_layers[0].data.foreach_get("uv",uv); uv=uv.reshape(nl,2)
lt=np.empty(nt*3,np.int32); m.polygons.foreach_get("loop_start",lt[:nt])
ls=lt[:nt]
loops3=np.c_[ls,ls+1,ls+2]
tris=lv[loops3]; uvs=uv[loops3]
np.save("/home/claude/tanu/tris.npy",tris); np.save("/home/claude/tanu/uvs.npy",uvs)
curve=mouth_points(co,25); np.save("/home/claude/tanu/curve.npy",curve)
d=dist_to_mouth(co,curve); np.save("/home/claude/tanu/dmouth.npy",d)
sel=(d[tris]<0.22).any(1)
print("tris total",nt,"selected",sel.sum())
t0=time.time()
pos,cov=build_texel_map(co,tris[sel],uvs[sel])
print("raster %.1fs covered texels %d"%(time.time()-t0,cov.sum()))
np.save("/home/claude/tanu/texel_pos.npy",pos); np.save("/home/claude/tanu/texel_cov.npy",cov)
