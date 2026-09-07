# -*- coding: utf-8 -*-
"""Write viseme tracks onto the rigged tanuki's shape keys in Blender."""
import bpy

def apply(ob, data, fps=None, clear=True):
    fps = fps or bpy.context.scene.render.fps
    kb = ob.data.shape_keys.key_blocks
    if clear and ob.data.shape_keys.animation_data:
        ob.data.shape_keys.animation_data_clear()
    for v, keys in data["tracks"].items():
        if v not in kb: continue
        for t, w in keys:
            kb[v].value = float(w)
            kb[v].keyframe_insert("value", frame=1 + t * fps)
    for fc in _fcurves(ob.data.shape_keys.animation_data.action):
        for k in fc.keyframe_points:
            k.interpolation = 'BEZIER'
            k.handle_left_type = k.handle_right_type = 'AUTO_CLAMPED'
    return int(1 + data["duration"] * fps)

def _fcurves(act):
    """Blender 4.4+ moved F-curves into slotted actions; older builds keep
    them on the action itself."""
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    out = []
    for layer in act.layers:
        for strip in layer.strips:
            for cb in getattr(strip, "channelbags", []):
                out += list(cb.fcurves)
    return out
