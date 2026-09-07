import bpy, math, mathutils, sys
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath="/home/claude/tanu/tanu_base.glb")
objs=[o for o in bpy.data.objects]
print("OBJECTS:",[(o.name,o.type) for o in objs])
me=[o for o in objs if o.type=='MESH'][0]
print("verts",len(me.data.vertices),"polys",len(me.data.polygons),"materials",[m.name for m in me.data.materials])
print("shapekeys", me.data.shape_keys)
bb=[me.matrix_world @ mathutils.Vector(c) for c in me.bound_box]
mn=mathutils.Vector((min(v.x for v in bb),min(v.y for v in bb),min(v.z for v in bb)))
mx=mathutils.Vector((max(v.x for v in bb),max(v.y for v in bb),max(v.z for v in bb)))
print("bbox min",mn,"max",mx,"size",mx-mn)
ctr=(mn+mx)/2; size=max((mx-mn))
# lighting
w=bpy.data.worlds.new("W"); bpy.context.scene.world=w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[0].default_value=(1,1,1,1)
w.node_tree.nodes["Background"].inputs[1].default_value=1.5
sc=bpy.context.scene
sc.render.engine='BLENDER_EEVEE'
sc.render.resolution_x=512; sc.render.resolution_y=640
sc.render.film_transparent=False
cam_data=bpy.data.cameras.new("C"); cam=bpy.data.objects.new("C",cam_data); sc.collection.objects.link(cam); sc.camera=cam
def shot(angle_deg, elev, dist_mul, target, out, focal=50):
    cam_data.lens=focal
    a=math.radians(angle_deg); e=math.radians(elev)
    d=size*dist_mul
    cam.location=target+mathutils.Vector((math.sin(a)*math.cos(e),-math.cos(a)*math.cos(e),math.sin(e)))*d
    dirv=target-cam.location
    cam.rotation_euler=dirv.to_track_quat('-Z','Y').to_euler()
    sc.render.filepath=out; bpy.ops.render.render(write_still=True)
for ang,name in [(0,'front'),(35,'q'),(90,'side')]:
    shot(ang,5,1.6,ctr,f"/home/claude/tanu/full_{name}.png")
# head closeup: top 22% of bbox
head=mathutils.Vector((ctr.x,ctr.y,mn.z+(mx.z-mn.z)*0.90))
for ang,name in [(0,'front'),(30,'q'),(75,'side')]:
    shot(ang,0,0.30,head,f"/home/claude/tanu/head_{name}.png",focal=70)
