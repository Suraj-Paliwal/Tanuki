import bpy, numpy as np, math, mathutils
co=np.load("/home/claude/tanu/co.npy")
def surf(x,z,r=0.02):
    s=co[(np.abs(co[:,0]-x)<r)&(np.abs(co[:,2]-z)<r)]
    return None if len(s)==0 else s[np.argmin(s[:,1])]
pts={}
for name,(x,z) in {"nose":(0,0.41),"m_c":(0,0.335),"m_L":(-0.12,0.355),"m_R":(0.12,0.355),
                   "m_lo":(0,0.30),"chin":(0,0.26),"m_hi":(0,0.365)}.items():
    p=surf(x,z); pts[name]=p; print(name,p)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath="/home/claude/tanu/tanu_base.glb")
sc=bpy.context.scene
mat=bpy.data.materials.new("R"); mat.use_nodes=True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value=(1,0,0,1)
for n,p in pts.items():
    if p is None: continue
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.012,location=(float(p[0]),float(p[1])-0.008,float(p[2])))
    o=bpy.context.object; o.data.materials.append(mat)
w=bpy.data.worlds.new("W"); sc.world=w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[1].default_value=1.6
sc.render.resolution_x=760; sc.render.resolution_y=760
sc.render.engine='BLENDER_WORKBENCH'
sh=sc.display.shading; sh.light='STUDIO'; sh.color_type='MATERIAL'; sh.show_cavity=True
cd=bpy.data.cameras.new("C"); cam=bpy.data.objects.new("C",cd); sc.collection.objects.link(cam); sc.camera=cam
cd.lens=55
T=mathutils.Vector((0,0,0.36))
for ang,el,nm in [(0,0,'f'),(35,0,'q'),(0,-30,'up')]:
    a=math.radians(ang);e=math.radians(el)
    cam.location=T+mathutils.Vector((math.sin(a)*math.cos(e),-math.cos(a)*math.cos(e),math.sin(e)))*1.30
    cam.rotation_euler=(T-cam.location).to_track_quat('-Z','Y').to_euler()
    sc.render.filepath=f"/home/claude/tanu/MK_{nm}.png"; bpy.ops.render.render(write_still=True)
