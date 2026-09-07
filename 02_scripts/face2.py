import bpy, math, mathutils
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath="/home/claude/tanu/tanu_base.glb")
sc=bpy.context.scene
w=bpy.data.worlds.new("W"); sc.world=w; w.use_nodes=True
w.node_tree.nodes["Background"].inputs[1].default_value=1.6
sc.render.resolution_x=760; sc.render.resolution_y=760
cd=bpy.data.cameras.new("C"); cam=bpy.data.objects.new("C",cd); sc.collection.objects.link(cam); sc.camera=cam
cd.lens=55
NOSE=mathutils.Vector((0,-0.60,0.42))
def look(target,ang,elev,d):
    a=math.radians(ang); e=math.radians(elev)
    off=mathutils.Vector((math.sin(a)*math.cos(e),-math.cos(a)*math.cos(e),math.sin(e)))*d
    cam.location=target+off
    cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
T=mathutils.Vector((0,0,0.42))
sc.render.engine='BLENDER_EEVEE'
for ang,el,nm in [(0,0,'f'),(30,0,'q'),(0,-25,'up')]:
    look(T,ang,el,1.45); sc.render.filepath=f"/home/claude/tanu/F_tex_{nm}.png"; bpy.ops.render.render(write_still=True)
sc.render.engine='BLENDER_WORKBENCH'
sh=sc.display.shading; sh.light='STUDIO'; sh.color_type='SINGLE'; sh.single_color=(0.75,0.75,0.75)
sh.show_cavity=True; sh.cavity_type='BOTH'; sh.curvature_ridge_factor=2.0; sh.curvature_valley_factor=2.0
for ang,el,nm in [(0,0,'f'),(30,0,'q'),(0,-25,'up'),(80,0,'s')]:
    look(T,ang,el,1.45); sc.render.filepath=f"/home/claude/tanu/F_clay_{nm}.png"; bpy.ops.render.render(write_still=True)
# tight mouth-region clay
look(mathutils.Vector((0,0,0.33)),0,-10,0.95); sc.render.filepath="/home/claude/tanu/F_clay_mouth.png"; bpy.ops.render.render(write_still=True)
