"""Blender-side renderer used by render.py. Not meant to be called directly.

blender -b --factory-startup -P blender_render.py -- MODEL OUT_PREFIX MODE [args]
  MODE sheet               10 named views of the whole model
  MODE closeup             front / side / above of a (cropped) part, tight framing
  MODE pick VIEW u,v ...   ray-cast pixels of a closeup VIEW render back to 3D points
"""
import math
import sys

import bpy
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:]
model, prefix, mode = argv[0], argv[1], argv[2]
RES = 900

bpy.ops.wm.read_factory_settings(use_empty=True)
ext = model.lower().rsplit(".", 1)[-1]
if ext == "stl":
    bpy.ops.wm.stl_import(filepath=model)
elif ext == "ply":
    bpy.ops.wm.ply_import(filepath=model)
elif ext == "obj":  # keep the file's own axes (our OBJs are already Z-up)
    bpy.ops.wm.obj_import(filepath=model, forward_axis="Y", up_axis="Z")
else:
    bpy.ops.import_scene.gltf(filepath=model)
meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
for o in meshes:
    o.data.materials.clear()
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
ext_v, size = hi - lo, (hi - lo).length

scene = bpy.context.scene
scene.render.engine = "BLENDER_WORKBENCH"
scene.render.resolution_x = scene.render.resolution_y = RES
sh = scene.display.shading
sh.light = "STUDIO"
sh.color_type = "SINGLE"
sh.single_color = (0.8, 0.8, 0.8)
sh.show_cavity = True
sh.cavity_type = "BOTH"
sh.cavity_ridge_factor, sh.cavity_valley_factor = 1.5, 1.5
sh.curvature_ridge_factor, sh.curvature_valley_factor = 1.5, 1.5
# Shadows make raised flat details (letters on a plate) visible: same-facing faces otherwise
# shade identically and the detail vanishes into its background.
sh.show_shadows = True
sh.shadow_intensity = 0.35  # light: strong shadows were mistaken for dark paint/defects
scene.display.light_direction = (0.35, -0.45, 0.82)
scene.display.shadow_shift = 0.05
scene.world = bpy.data.worlds.new("w")
scene.world.color = (0.18, 0.2, 0.24)
cam_data = bpy.data.cameras.new("cam")
cam_data.type = "ORTHO"
cam = bpy.data.objects.new("cam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam


CORNERS = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]


def aim(az, el, target, zoom):
    """Point the camera; frame the model's projected outline (works for long/flat parts too)."""
    a, e = math.radians(az), math.radians(el)
    cam.location = target + Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e))) * size * 3
    rot = (target - cam.location).to_track_quat("-Z", "Y")
    cam.rotation_euler = rot.to_euler()
    right, up = rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
    w = max(c.dot(right) for c in CORNERS) - min(c.dot(right) for c in CORNERS)
    h = max(c.dot(up) for c in CORNERS) - min(c.dot(up) for c in CORNERS)
    cam_data.ortho_scale = max(w, h) * 1.08 * zoom
    return rot, cam_data.ortho_scale


def frac(f):
    return Vector([lo[i] + ext_v[i] * f[i] for i in range(3)])


SHEET = {  # name: (azimuth, elevation, zoom, target as bbox fraction)
    "front": (0, 5, 1.0, (0.5, 0.5, 0.5)), "back": (180, 5, 1.0, (0.5, 0.5, 0.5)),
    "left": (-90, 5, 1.0, (0.5, 0.5, 0.5)), "right": (90, 5, 1.0, (0.5, 0.5, 0.5)),
    "top": (0, 89, 1.0, (0.5, 0.5, 0.5)), "bottom": (0, -89, 1.0, (0.5, 0.5, 0.5)),
    "front_34": (35, 20, 1.0, (0.5, 0.5, 0.5)), "back_34": (215, 20, 1.0, (0.5, 0.5, 0.5)),
    "upper_closeup": (15, 15, 0.5, (0.5, 0.45, 0.75)), "lower_closeup": (15, 15, 0.5, (0.5, 0.45, 0.25)),
}
CLOSEUP = {"front": (0, 5), "side": (40, 15), "above": (0, 40), "below": (0, -55)}

if mode == "sheet":
    for name, (az, el, zoom, f) in SHEET.items():
        aim(az, el, frac(f), zoom)
        scene.render.filepath = f"{prefix}_{name}.png"
        bpy.ops.render.render(write_still=True)
elif mode == "closeup":
    for name, (az, el) in CLOSEUP.items():
        aim(az, el, (lo + hi) / 2, 1.0)
        scene.render.filepath = f"{prefix}_{name}.png"
        bpy.ops.render.render(write_still=True)
elif mode == "pick":
    view, pix = argv[3], [tuple(map(float, p.split(","))) for p in argv[4:]]
    az, el = CLOSEUP[view]
    rot, scale = aim(az, el, (lo + hi) / 2, 1.0)
    fwd, right, up = rot @ Vector((0, 0, -1)), rot @ Vector((1, 0, 0)), rot @ Vector((0, 1, 0))
    dg = bpy.context.evaluated_depsgraph_get()
    for u, v in pix:
        origin = cam.location + right * ((u / RES - 0.5) * scale) + up * ((0.5 - v / RES) * scale)
        hit, p, *_ = scene.ray_cast(dg, origin, fwd)
        print("PICK", f"{u:g},{v:g}", "->", ",".join(f"{c:.2f}" for c in p) if hit else "miss")
print("RENDER_DONE")
