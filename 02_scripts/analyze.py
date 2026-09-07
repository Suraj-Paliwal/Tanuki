import bpy, numpy as np
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath="/home/claude/tanu/tanu_base.glb")
me=[o for o in bpy.data.objects if o.type=='MESH'][0]
m=me.data
n=len(m.vertices)
co=np.empty(n*3); m.vertices.foreach_get("co",co); co=co.reshape(n,3)
np.save("/home/claude/tanu/co.npy",co)
print("bbox", co.min(0), co.max(0))
# nose = most -Y in upper half
up=co[co[:,2]>0.1]
i=np.argmin(up[:,1]); print("most-forward upper vert (nose tip?):", up[i])
# histogram of min-y per z slice
for z0 in np.arange(-0.1,1.01,0.05):
    sl=co[(co[:,2]>=z0)&(co[:,2]<z0+0.05)]
    if len(sl): print(f"z {z0:+.2f} n={len(sl):6d} minY={sl[:,1].min():+.3f} widthX={sl[:,0].max()-sl[:,0].min():.3f}")
# edge length stats
el=[]
import random
edges=m.edges
idx=random.sample(range(len(edges)),3000)
for i in idx:
    a,b=edges[i].vertices; el.append(np.linalg.norm(co[a]-co[b]))
el=np.array(el); print("edge len mean",el.mean(),"median",np.median(el),"p10",np.percentile(el,10),"p90",np.percentile(el,90))
print("total edges",len(edges),"tris",len(m.polygons))
# is mesh manifold / closed? check non-manifold quickly via edge-face count
from collections import Counter
