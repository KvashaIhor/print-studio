"""2D -> 3D: lithophanes, image reliefs, SVG extrusions, text signs/keychains, cookie cutters.

  lithophane IMAGE OUT.stl [--width 100] [--min 0.8] [--max 3.2] [--border 3] [--crop x0 y0 x1 y1]
             [--gamma 1.0] [--no-autocontrast] [--foot DEPTH] [--flat] [--res 0.2]
             Dark = thick. Stands upright on a foot (print it that way: 0.12 mm layers, 100% infill
             or 4 walls, supports OFF, white PLA). The relief side faces -Y (= "front"): that side
             faces the room. Thickness is limited so nothing overhangs > 45 deg when printed upright
             (also chamfers the ledge under the top frame). Writes OUT_preview.png: how it looks
             back-lit.
  relief     IMAGE OUT.stl [--width 80] [--base 2] [--height 3] [--invert] [--threshold T]
             Bright = high (--invert flips). --threshold 0.5 makes a crisp two-level logo/sign.
  svg        FILE.svg OUT.stl [--height 3] [--width 60] [--base 0] [--margin 3]
  text       "TEXT" OUT.stl [--size 10] [--height 2] [--base 2] [--margin 3] [--hole 4] [--font F]
             Name tags, keychains (--hole adds a keyring hole on the left), signs.
  cookie     FILE.svg OUT.stl [--width 70] [--height 12] [--wall 0.8] [--flange 3] [--flange-h 1.5]
"""
import argparse
from pathlib import Path

import numpy as np
import trimesh
from PIL import Image, ImageOps


def heightfield_solid(H, res):
    """Watertight solid from a height grid H (mm, rows=y, cols=x), bottom at z=0."""
    ny, nx = H.shape
    xs, ys = np.arange(nx) * res, (ny - 1 - np.arange(ny)) * res  # image row 0 = top
    X, Y = np.meshgrid(xs, ys)
    top = np.c_[X.ravel(), Y.ravel(), H.ravel()]
    bot = np.c_[X.ravel(), Y.ravel(), np.zeros(H.size)]
    V = np.vstack([top, bot])
    idx = np.arange(H.size).reshape(ny, nx)
    a, b, c, d = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, :-1].ravel(), idx[1:, 1:].ravel()
    off = H.size
    F = [np.c_[a, c, b], np.c_[b, c, d], np.c_[a + off, b + off, c + off], np.c_[b + off, d + off, c + off]]
    for edge in (idx[0, :], idx[:, -1], idx[-1, ::-1], idx[::-1, 0]):  # walk the rim, close the sides
        e0, e1 = edge[:-1], edge[1:]
        F += [np.c_[e0, e0 + off, e1], np.c_[e1, e0 + off, e1 + off]]
    m = trimesh.Trimesh(V, np.vstack(F), process=True)
    m.fix_normals()
    return m


def load_gray(path, width_mm, res, crop=None, autocontrast=False, gamma=1.0):
    img = ImageOps.exif_transpose(Image.open(path)).convert("L")
    if crop:  # fractions of the image: x0 y0 x1 y1 (top-left origin)
        W, H = img.size
        img = img.crop((int(crop[0] * W), int(crop[1] * H), int(crop[2] * W), int(crop[3] * H)))
    if autocontrast:
        img = ImageOps.autocontrast(img, cutoff=0.5)
    w = int(round(width_mm / res)) + 1  # n samples span (n-1)*res = width_mm exactly
    h = int(round(img.height * (w - 1) / img.width)) + 1
    g = np.asarray(img.resize((w, h), Image.LANCZOS), float) / 255.0
    return g ** gamma if gamma != 1.0 else g


def report(m, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    m.export(path)
    print(f"{path}: {np.round(m.extents, 2)} mm, volume {m.volume / 1000:.2f} cm3, "
          f"watertight={m.is_watertight}, bodies={m.body_count}")


def cmd_lithophane(a):
    import ps_config
    cfg = ps_config.load()
    g = load_gray(a.image, a.width - 2 * a.border, a.res, a.crop, not a.no_autocontrast, a.gamma)
    H = a.min + (1 - g) * (a.max - a.min)
    b = int(round(a.border / a.res))
    if b:
        H = np.pad(H, b, constant_values=a.max)  # solid frame
    if not a.flat:
        # Printed upright, a row that is thicker than the row below it overhangs. Limit the growth
        # per row (going up = towards row 0) to the printer's overhang angle; this also turns the
        # ledge under the top frame into a chamfer. Rows run from top (0) to bottom (n-1).
        step = a.res * np.tan(np.radians(cfg["max_overhang_deg"]))
        before = H.copy()
        for r in range(H.shape[0] - 2, -1, -1):
            np.minimum(H[r], H[r + 1] + step, out=H[r])
        changed = (np.abs(before - H) > 1e-6).mean() * 100
        print(f"self-supporting: thinned {changed:.2f}% of pixels so nothing overhangs > {cfg['max_overhang_deg']} deg")
    # back-lit preview: light through white PLA falls off ~exponentially with thickness
    # (~10x more light through 0.8 mm than through 3.2 mm), shown with display gamma
    T = np.exp(-0.96 * (H - H.min()))
    T = T ** (1 / 2.2)
    prev = str(Path(a.output).with_name(Path(a.output).stem + "_preview.png"))
    Path(prev).parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((T * 255).astype(np.uint8)).save(prev)
    m = heightfield_solid(H, a.res)
    if not a.flat:  # stand it up: image plane = XZ, relief faces -Y, plus a foot for stability
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
        m.apply_translation(-m.bounds[0])
        height = m.extents[2]
        depth = a.foot or max(12.0, 0.28 * height)  # deep enough not to tip on a windowsill
        foot = trimesh.creation.box([m.extents[0], depth, 2.0])
        foot.apply_translation([m.extents[0] / 2, m.extents[1] / 2, 1.0])
        m.apply_translation([0, 0, 1.6])
        import manifold3d as m3d
        mm = lambda t: m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(t.vertices, np.float32), tri_verts=np.asarray(t.faces, np.uint32)))
        u = (mm(m) + mm(foot)).to_mesh()
        m = trimesh.Trimesh(np.asarray(u.vert_properties)[:, :3], np.asarray(u.tri_verts), process=True)
        print(f"upright, foot {depth:.0f} mm deep; relief side faces -Y (front) - turn it towards the room")
    report(m, a.output)
    print(f"back-lit preview -> {prev}")


def cmd_relief(a):
    g = load_gray(a.image, a.width, a.res, a.crop, False, 1.0)
    if a.invert:
        g = 1 - g
    if a.threshold is not None:
        g = (g >= a.threshold).astype(float)
    report(heightfield_solid(a.base + g * a.height, a.res), a.output)


def b123d_export(part, path):
    from build123d import export_stl
    export_stl(part, path, tolerance=0.02, angular_tolerance=0.1)
    m = trimesh.load(path, force="mesh", process=True)
    report(m, path)


def svg_faces(path, width):
    from build123d import Face, import_svg, scale
    shapes = import_svg(path)
    faces = [f for s in shapes for f in s.faces()] or [Face(w) for s in shapes for w in s.wires() if w.is_closed]
    if not faces:
        raise SystemExit("no closed shapes found in the SVG (convert strokes to paths/fills first)")
    from build123d import Compound
    comp = Compound(faces)
    bb = comp.bounding_box()
    f = width / bb.size.X if width else 1.0
    comp = scale(comp, (f, f, 1))
    bb = comp.bounding_box()
    from build123d import Pos
    return Pos(-bb.min.X, -bb.min.Y, 0) * comp


def cmd_svg(a):
    from build123d import Box, Pos, extrude
    sh = svg_faces(a.svg, a.width)
    part = extrude(sh, amount=a.height)
    if a.base > 0:
        bb = sh.bounding_box()
        plate = Pos(bb.center().X, bb.center().Y, -a.base / 2) * Box(bb.size.X + 2 * a.margin, bb.size.Y + 2 * a.margin, a.base)
        part = Pos(0, 0, a.base) * (part + plate)
    b123d_export(part, a.output)


def cmd_text(a):
    from build123d import Align, Cylinder, Pos, RectangleRounded, Text, extrude
    kw = {"font": a.font} if a.font else {}
    t = Text(a.text, font_size=a.size, align=(Align.CENTER, Align.CENTER), **kw)
    bb = t.bounding_box()
    part = Pos(0, 0, a.base) * extrude(t, amount=a.height)
    if a.base > 0:
        w, h = bb.size.X + 2 * a.margin, bb.size.Y + 2 * a.margin
        extra = (a.hole + 2 * 2.0) if a.hole else 0
        plate = extrude(Pos(-extra / 2, 0) * RectangleRounded(w + extra, h, min(h / 2 - 0.01, 3)), amount=a.base)
        if a.hole:
            plate -= Pos(-w / 2 - extra / 2, 0, a.base / 2) * Cylinder(a.hole / 2, a.base * 3)
        part = part + plate
    b123d_export(part, a.output)


def cmd_cookie(a):
    from build123d import extrude, offset
    sh = svg_faces(a.svg, a.width)
    faces = sh.faces()
    outer = max(faces, key=lambda f: f.area)  # cutter follows the outline only
    wall = extrude(offset(outer, a.wall) - outer, amount=a.height)
    flange = extrude(offset(outer, a.wall + a.flange) - outer, amount=a.flange_h)
    b123d_export(wall + flange, a.output)


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("lithophane"); p.add_argument("image"); p.add_argument("output")
p.add_argument("--width", type=float, default=100); p.add_argument("--min", type=float, default=0.8); p.add_argument("--max", type=float, default=3.2)
p.add_argument("--border", type=float, default=3); p.add_argument("--flat", action="store_true"); p.add_argument("--res", type=float, default=0.2)
p.add_argument("--crop", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"), help="crop, image fractions")
p.add_argument("--gamma", type=float, default=1.0, help=">1 darkens midtones (thicker), <1 lightens")
p.add_argument("--no-autocontrast", action="store_true"); p.add_argument("--foot", type=float, help="foot depth mm")
p = sub.add_parser("relief"); p.add_argument("image"); p.add_argument("output")
p.add_argument("--width", type=float, default=80); p.add_argument("--base", type=float, default=2); p.add_argument("--height", type=float, default=3)
p.add_argument("--invert", action="store_true"); p.add_argument("--threshold", type=float); p.add_argument("--res", type=float, default=0.2)
p.add_argument("--crop", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"))
p = sub.add_parser("svg"); p.add_argument("svg"); p.add_argument("output"); p.add_argument("--height", type=float, default=3)
p.add_argument("--width", type=float, default=60); p.add_argument("--base", type=float, default=0); p.add_argument("--margin", type=float, default=3)
p = sub.add_parser("text"); p.add_argument("text"); p.add_argument("output"); p.add_argument("--size", type=float, default=10)
p.add_argument("--height", type=float, default=2); p.add_argument("--base", type=float, default=2); p.add_argument("--margin", type=float, default=3)
p.add_argument("--hole", type=float, default=0); p.add_argument("--font")
p = sub.add_parser("cookie"); p.add_argument("svg"); p.add_argument("output"); p.add_argument("--width", type=float, default=70)
p.add_argument("--height", type=float, default=12); p.add_argument("--wall", type=float, default=0.8)
p.add_argument("--flange", type=float, default=3); p.add_argument("--flange-h", type=float, default=1.5)
if __name__ == "__main__":
    a = ap.parse_args()
    globals()[f"cmd_{a.cmd}"](a)
