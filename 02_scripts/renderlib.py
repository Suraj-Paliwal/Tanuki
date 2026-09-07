"""Rendering helpers: load the tanuki, swap textures, frame the face."""
import bpy, math, mathutils, os

GLB = "/home/claude/tanu/tanu_base.glb"

def load(glb=GLB):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=glb)
    return [o for o in bpy.data.objects if o.type == 'MESH'][0]

def set_basecolor(path):
    img = bpy.data.images.load(path, check_existing=False)
    for m in bpy.data.materials:
        if not m.use_nodes: continue
        bsdf = next((n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if not bsdf: continue
        lk = bsdf.inputs['Base Color'].links
        if lk and lk[0].from_node.type == 'TEX_IMAGE':
            lk[0].from_node.image = img

def world(strength=1.0, colour=(1, 1, 1, 1)):
    w = bpy.data.worlds.new("W"); bpy.context.scene.world = w; w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs[0].default_value = colour
    bg.inputs[1].default_value = strength

def three_point(target, size=1.0):
    def lamp(name, kind, loc, energy, sz=1.0):
        d = bpy.data.lights.new(name, kind); d.energy = energy
        if kind == 'AREA': d.size = sz
        o = bpy.data.objects.new(name, d); bpy.context.scene.collection.objects.link(o)
        o.location = loc
        o.rotation_euler = (mathutils.Vector(target) - mathutils.Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        return o
    lamp("key",  'AREA', (-0.9, -1.3,  1.2), 260, 1.4)
    lamp("fill", 'AREA', ( 1.1, -1.0,  0.5),  90, 1.6)
    lamp("rim",  'AREA', ( 0.2,  1.2,  1.0), 140, 1.2)

def camera(lens=55):
    sc = bpy.context.scene
    cd = bpy.data.cameras.new("C"); cd.lens = lens
    cam = bpy.data.objects.new("C", cd); sc.collection.objects.link(cam); sc.camera = cam
    return cam

def aim(cam, target, ang=0.0, elev=0.0, dist=1.2):
    t = mathutils.Vector(target); a = math.radians(ang); e = math.radians(elev)
    cam.location = t + mathutils.Vector((math.sin(a)*math.cos(e), -math.cos(a)*math.cos(e), math.sin(e))) * dist
    cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()

def eevee_scene(strength=0.55):
    world(strength)
    three_point(FACE)

def setup(engine='BLENDER_EEVEE', res=620, samples=16):
    sc = bpy.context.scene
    sc.render.engine = engine
    sc.render.resolution_x = res; sc.render.resolution_y = res
    sc.render.image_settings.file_format = 'PNG'
    if engine == 'BLENDER_EEVEE':
        try: sc.eevee.taa_render_samples = samples
        except Exception: pass
        # raytraced occlusion: without it the world light floods the mouth
        # cavity and the interior renders as flat grey instead of dark
        try:
            sc.eevee.use_raytracing = True
            sc.eevee.ray_tracing_options.use_denoise = True
        except Exception: pass
    if engine == 'BLENDER_WORKBENCH':
        sh = sc.display.shading
        sh.light = 'STUDIO'; sh.color_type = 'TEXTURE'
        sh.show_cavity = True; sh.cavity_type = 'BOTH'
    return sc

def shot(path, cam, target, ang=0, elev=0, dist=1.2):
    aim(cam, target, ang, elev, dist)
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)

FACE = (0, 0, 0.345)
