# -*- coding: utf-8 -*-
import bpy, sys, os, json, subprocess
sys.path.insert(0,"/home/claude/tanu"); sys.path.insert(0,"/home/claude/tanu/pipeline")
import renderlib as R
from jp_lipsync import build
from apply_tracks import apply

TEXT = "こんにちは、たぬきです"
# a blink lands mid-phrase; the idle blink track is part of the demo now
FPS, RES, SAMP = 24, 440, 6
OUT = "/home/claude/tanu/frames"
os.makedirs(OUT, exist_ok=True)

bpy.ops.wm.open_mainfile(filepath="/mnt/user-data/outputs/Tanuki/05_model/tanuki_visemes.blend")
ob = next(o for o in bpy.data.objects if o.type=='MESH')
sc = bpy.context.scene
sc.render.fps = FPS
data = build(TEXT, mora_dur=0.135, fps=FPS, blink=True)
last = apply(ob, data, FPS)
print("frames:", last, "duration %.2f"%data["duration"])

R.setup('BLENDER_EEVEE', res=RES, samples=SAMP)
R.eevee_scene(0.55)
cam = R.camera(60)
R.aim(cam, (-0.02, 0, 0.50), 0, 3, 1.75)
sc.render.filepath = OUT + "/f_"
sc.frame_start, sc.frame_end = 1, last
import time; t0=time.time()
bpy.ops.render.render(animation=True)
print("rendered %d frames in %.0fs"%(last, time.time()-t0))
json.dump(data, open("/home/claude/tanu/pipeline/demo_track.json","w"), ensure_ascii=False, indent=1)
