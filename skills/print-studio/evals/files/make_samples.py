"""Regenerate the synthetic eval inputs (no third-party content):
  sample_picture.png  a simple landscape with a full tonal range (for lithophane / relief tests)
  sample_figure.stl   a 70 mm snowman-like figure, watertight (for modify tests: plinth, text, pocket)
Run: python make_samples.py   (needs pillow, numpy, manifold3d, trimesh)
"""
from pathlib import Path

import manifold3d as m3d
import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent

# picture: sky gradient, sun, two mountain ridges, a lake with a reflection
W, H = 640, 448
sky = np.linspace(235, 120, H // 2)[:, None].repeat(W, 1)
img = Image.fromarray(np.vstack([sky, np.full((H - H // 2, W), 70.0)]).astype(np.uint8), "L")
d = ImageDraw.Draw(img)
d.ellipse((440, 60, 520, 140), fill=250)
d.polygon([(0, 250), (120, 120), (210, 200), (330, 90), (470, 230), (640, 150), (640, 260), (0, 260)], fill=105)
d.polygon([(0, 260), (90, 200), (260, 245), (400, 180), (640, 250), (640, 275), (0, 275)], fill=55)
d.rectangle((0, 275, W, H), fill=160)
for y in range(285, H, 14):
    d.line((40, y, W - 40, y), fill=185, width=2)
img = img.filter(ImageFilter.GaussianBlur(1.2)).convert("RGB")
img.save(HERE / "sample_picture.png")

# figure: three stacked spheres + a carrot nose, flat bottom
s = lambda r, z, x=0, y=0: m3d.Manifold.sphere(r, 96).translate((x, y, z))
body = s(17, 15) + s(12.5, 39) + s(9, 58)
nose = m3d.Manifold.cylinder(9, 2.2, 0.4, 32).rotate((90, 0, 0)).translate((0, -7.5, 59))
fig = (body + nose) - m3d.Manifold.cube((80, 80, 20), center=True).translate((0, 0, -8))
mesh = fig.to_mesh()
t = trimesh.Trimesh(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts))
t.apply_translation((0, 0, -t.bounds[0, 2]))
t.export(HERE / "sample_figure.stl")
print("picture", img.size, "| figure", np.round(t.extents, 1), "mm, watertight", t.is_watertight)
