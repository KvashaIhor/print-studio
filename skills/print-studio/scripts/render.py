"""Inspection renders for 3D-print models (headless Blender, matcap + cavity shading).

  sheet   MODEL OUT.png [--ref IMG] [--compare OTHER_MODEL]
          10 views (front/back/left/right/top/bottom/3-4 views/upper & lower close-ups) in one
          sheet; --ref adds the reference image as a tile; --compare renders a second model and
          puts the sheets side by side per view (e.g. raw AI output vs. processed).
  closeup MODEL OUT.png (--box x0 x1 y0 y1 z0 z1 | --at X Y Z --radius R)
          Crop a region (bbox fractions, or a cube of +-R mm around a point) and render
          front/side/above/below at high zoom. Tiles are 600 px; the crop is saved as
          OUT_crop.stl for `pick`. --at takes three numbers (negatives fine) or "X,Y,Z".
  pick    OUT.png VIEW u,v [u,v ...]
          Map pixel(s) of a closeup tile (600 px tile coordinates; VIEW front|side|above|below)
          to 3D model coordinates in mm. Use it to locate a defect, then fix_spot.py.

View convention: "front" looks at the model from -Y towards +Y (so model the side a person
looks at facing -Y), "left" from -X, "right" from +X, "top" from +Z, "bottom" from -Z.
Shading: soft cast shadows + cavity lines; a dark patch that moves with the light is a shadow.
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import ps_config  # noqa: E402

CFG = ps_config.load()
BLENDER = CFG["blender"]
TILE = 600


def blender(*args):
    p = subprocess.run([BLENDER, "-b", "--factory-startup", "-P", str(HERE / "blender_render.py"), "--", *map(str, args)],
                       capture_output=True, text=True)
    if "RENDER_DONE" not in p.stdout:
        raise SystemExit("blender failed:\n" + (p.stdout + p.stderr)[-2000:])
    return p.stdout


def compose(tiles, cols, out, labels):
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * TILE, rows * (TILE + 24)), (40, 40, 40))
    d = ImageDraw.Draw(sheet)
    for i, (img, lab) in enumerate(zip(tiles, labels)):
        x, y = (i % cols) * TILE, (i // cols) * (TILE + 24)
        sheet.paste(img.convert("RGB").resize((TILE, TILE)), (x, y + 24))
        d.text((x + 8, y + 6), lab, fill=(255, 220, 0))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    return out


def cmd_sheet(a):
    names = ["front", "back", "left", "right", "top", "bottom", "front_34", "back_34", "upper_closeup", "lower_closeup"]
    with tempfile.TemporaryDirectory() as td:
        blender(Path(a.model).resolve(), f"{td}/a", "sheet")
        tiles = [Image.open(f"{td}/a_{n}.png") for n in names]
        labels = names[:]
        if a.compare:
            blender(Path(a.compare).resolve(), f"{td}/b", "sheet")
            tiles = [t for n, ta in zip(names, tiles) for t in (ta, Image.open(f"{td}/b_{n}.png"))]
            labels = [l for n in names for l in (f"{n} - {Path(a.model).stem}", f"{n} - {Path(a.compare).stem}")]
        if a.ref:
            tiles.insert(0, Image.open(a.ref))
            labels.insert(0, "reference")
        out = compose(tiles, 4, a.out, labels)
    print(f"sheet -> {out}")


def parse_xyz(tokens):
    vals = [float(v) for t in tokens for v in t.replace(",", " ").split()]
    if len(vals) != 3:
        raise SystemExit("--at needs three numbers: --at X Y Z (or --at=X,Y,Z)")
    return np.array(vals)


def cmd_closeup(a):
    m = trimesh.load(a.model, force="mesh")
    if a.at:
        c = parse_xyz(a.at)
        lo, hi = c - a.radius, c + a.radius
    else:
        b = np.array(a.box).reshape(3, 2)
        lo, hi = m.bounds[0] + m.extents * b[:, 0], m.bounds[0] + m.extents * b[:, 1]
    crop = Path(a.out).with_name(Path(a.out).stem + "_crop.stl")
    if m.is_watertight:  # exact solid intersection: no shards from long triangles
        import manifold3d as m3d
        man = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(m.vertices, np.float32), tri_verts=np.asarray(m.faces, np.uint32)))
        box = m3d.Manifold.cube(tuple(hi - lo)).translate(tuple(lo))
        o = (man ^ box).to_mesh()
        part = trimesh.Trimesh(np.asarray(o.vert_properties)[:, :3], np.asarray(o.tri_verts))
    else:  # raw / leaky meshes: keep faces whose centre is inside (long triangles may look like shards)
        tc = m.triangles_center
        keep = np.all((tc >= lo) & (tc <= hi), axis=1)
        part = m.submesh([np.where(keep)[0]], append=True) if keep.any() else trimesh.Trimesh()
    if len(part.faces) == 0:
        raise SystemExit("crop is empty: check --box fractions / --at coordinates")
    Path(crop).parent.mkdir(parents=True, exist_ok=True)
    part.export(crop)
    with tempfile.TemporaryDirectory() as td:
        blender(crop.resolve(), f"{td}/c", "closeup")
        views = ["front", "side", "above", "below"]
        compose([Image.open(f"{td}/c_{v}.png") for v in views], 4, a.out, [f"closeup {v}" for v in views])
    print(f"closeup -> {a.out}  (crop saved as {crop}; pick with: render.py pick {a.out} front u,v)")


def cmd_pick(a):
    crop = Path(a.image).with_name(Path(a.image).stem + "_crop.stl")
    if not crop.exists():
        raise SystemExit(f"no crop file next to {a.image}; run closeup first")
    scale = 900 / TILE  # tile px -> render px
    px = [",".join(str(float(v) * scale) for v in p.split(",")) for p in a.pixels]
    out = blender(crop.resolve(), "/dev/null", "pick", a.view, *px)
    for line in out.splitlines():
        if line.startswith("PICK"):
            print(line)


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
s = sub.add_parser("sheet"); s.add_argument("model"); s.add_argument("out"); s.add_argument("--ref"); s.add_argument("--compare")
c = sub.add_parser("closeup"); c.add_argument("model"); c.add_argument("out")
c.add_argument("--box", type=float, nargs=6, metavar=("x0", "x1", "y0", "y1", "z0", "z1"))
c.add_argument("--at", nargs="+"); c.add_argument("--radius", type=float, default=8.0)
p = sub.add_parser("pick"); p.add_argument("image"); p.add_argument("view", choices=["front", "side", "above", "below"]); p.add_argument("pixels", nargs="+")
if __name__ == "__main__":
    a = ap.parse_args()
    {"sheet": cmd_sheet, "closeup": cmd_closeup, "pick": cmd_pick}[a.cmd](a)
