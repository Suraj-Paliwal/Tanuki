import bpy, numpy as np
from PIL import Image
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath="/home/claude/tanu/tanu_base.glb")
ob=[o for o in bpy.data.objects if o.type=='MESH'][0]; m=ob.data
nv=len(m.vertices); nl=len(m.loops)
co=np.empty(nv*3,dtype=np.float32); m.vertices.foreach_get("co",co); co=co.reshape(nv,3)
lv=np.empty(nl,dtype=np.int32); m.loops.foreach_get("vertex_index",lv)
uv=np.empty(nl*2,dtype=np.float32); m.uv_layers[0].data.foreach_get("uv",uv); uv=uv.reshape(nl,2)
# per-vertex uv (first loop wins)
vuv=np.zeros((nv,2),dtype=np.float32); seen=np.zeros(nv,bool)
order=np.argsort(lv)
vuv[lv[order]]=uv[order]
tex=np.asarray(Image.open("/home/claude/tanu/tex_basecolor.jpg").convert("RGB"),dtype=np.float32)/255.0
H,W,_=tex.shape
px=np.clip((vuv[:,0]*W).astype(int),0,W-1)
py=np.clip(((1-vuv[:,1])*H).astype(int),0,H-1)
vcol=tex[py,px]
lum=vcol.mean(1)
np.save("/home/claude/tanu/vuv.npy",vuv); np.save("/home/claude/tanu/vcol.npy",vcol); np.save("/home/claude/tanu/co.npy",co)
print("verts",nv,"loops",nl)
# muzzle region: front of face, below nose
mask_region=(co[:,1]<-0.30)&(co[:,2]>0.20)&(co[:,2]<0.55)&(np.abs(co[:,0])<0.35)
print("region verts",mask_region.sum())
dark=mask_region&(lum<0.18)
print("dark verts in region",dark.sum())
if dark.sum():
    d=co[dark]
    print("dark bbox",d.min(0),d.max(0))
    print("dark centroid",d.mean(0))
    # split: nose is a compact blob higher up; mouth is a wide thin arc lower
    for z0 in np.arange(0.20,0.56,0.02):
        s=d[(d[:,2]>=z0)&(d[:,2]<z0+0.02)]
        if len(s): print(f"  z {z0:.2f} n={len(s):5d} xrange {s[:,0].min():+.3f}..{s[:,0].max():+.3f} ymin {s[:,1].min():+.3f}")
