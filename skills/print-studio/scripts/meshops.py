"""Modify existing watertight meshes with exact solid booleans (manifold3d). All sizes in mm.

  scale     IN OUT (--factor F | --height H | --width W | --fit X Y Z)
  transform IN OUT [--rotate RX RY RZ] [--translate X Y Z] [--mirror x|y|z] [--to-bed]
  cut       IN OUT_PREFIX --at H [--axis z] [--pins N --pin-d 5 --pin-depth 6] [--no-flip]
            -> OUT_PREFIX_lower.stl, _upper.stl (cut face down, ready to print), _pins.stl
  hollow    IN OUT --wall 2.0 [--drain 5] [--pitch 0.5]
  boolean   IN OUT [--add A.stl ...] [--subtract B.stl ...]   (operands used in place)
  text      IN OUT --text "ABC" --side front|back|left|right|top [--letter-height 6 | --size 8.5]
            [--depth 1.0] [--engrave] [--wrap] [--height-at Z] [--offset U V] [--font "Arial Black"]
            --wrap bends the text around a vertical axis: use it on round bases/cylinders.
  pocket    IN OUT --d 10.3 --depth 3.2 [--shape cyl|hex] [--at X Y] [--side bottom|top] [--roof cone|flat]
            bottom pockets get a 45 deg cone roof by default so no support fills them.
  plinth    IN OUT [--shape round|rect] [--margin 3] [--height 4] [--chamfer 0.8]
            prints its centre/radius and the --height-at to use for text on it.
Coordinates are space-separated numbers (negative values fine).
Every command prints size/volume and whether the result is a single watertight body.
"""
import argparse
import tempfile
from pathlib import Path

import manifold3d as m3d
import numpy as np
import trimesh

UP = np.array([0.0, 0.0, 1.0])


def load(path):
    m = trimesh.load(path, force="mesh", process=True)
    if not m.is_watertight:
        raise SystemExit(f"{path} is not watertight: run solidify.py first")
    return m


def to_man(m):
    man = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                                tri_verts=np.asarray(m.faces, np.uint32)))
    if man.status() != m3d.Error.NoError:
        raise SystemExit(f"manifold rejected the mesh: {man.status()}")
    return man


def to_tri(man):
    o = man.to_mesh()
    return trimesh.Trimesh(np.asarray(o.vert_properties)[:, :3], np.asarray(o.tri_verts), process=True)


def save(m, path, label=""):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    m.export(path)
    print(f"{label}{path}: {np.round(m.extents, 2)} mm, volume {m.volume / 1000:.2f} cm3, "
          f"watertight={m.is_watertight}, bodies={m.body_count}")
    if not m.is_watertight:
        raise SystemExit(f"FAILED: {path} is not watertight (a bug in this operation, not your model): "
                         "don't continue from it")
    if m.body_count > 1:
        vols = sorted((abs(b.volume) / 1000 for b in m.split(only_watertight=False)), reverse=True)
        print(f"  WARNING: {m.body_count} separate pieces ({', '.join(f'{v:.2f}' for v in vols[:5])} cm3) - "
              f"intended? (e.g. a cut that also clipped a tail/ear tip; choose another height)")


def to_bed(m):
    m.apply_translation([-m.bounds[:, 0].mean(), -m.bounds[:, 1].mean(), -m.bounds[0, 2]])
    return m


def cylinder(d, h, z0=0.0, xy=(0, 0), seg=64):
    return m3d.Manifold.cylinder(h, d / 2, d / 2, seg).translate((xy[0], xy[1], z0))


# ---------------------------------------------------------------- commands
def cmd_scale(a):
    m = load(a.input)
    if a.factor:
        f = a.factor
    elif a.height:
        f = a.height / m.extents[2]
    elif a.width:
        f = a.width / m.extents[0]
    else:
        f = min(np.array(a.fit) / m.extents)
    m.apply_scale(f)
    save(m, a.output, f"scaled x{f:.4f} -> ")


def cmd_transform(a):
    m = load(a.input)
    if a.mirror:
        s = np.eye(4)
        s["xyz".index(a.mirror), "xyz".index(a.mirror)] = -1
        m.apply_transform(s)
        m.invert()  # mirroring flips winding
    if a.rotate:
        for ax, deg in zip(np.eye(3), a.rotate):
            if deg:
                m.apply_transform(trimesh.transformations.rotation_matrix(np.radians(deg), ax, m.centroid))
    if a.translate:
        m.apply_translation(a.translate)
    if a.to_bed:
        to_bed(m)
    save(m, a.output)


def pin_spots(section_polys, n, d, margin):
    """Pick n pin centres inside a cut cross-section, as far from its edges (and each other) as possible."""
    from matplotlib.path import Path as MPath
    from scipy import ndimage
    pts = np.vstack(section_polys)
    lo, hi = pts.min(0) - 1, pts.max(0) + 1
    res = 0.2
    gx, gy = np.meshgrid(np.arange(lo[0], hi[0], res), np.arange(lo[1], hi[1], res), indexing="ij")
    q = np.c_[gx.ravel(), gy.ravel()]
    inside = np.zeros(len(q), bool)
    for poly in section_polys:  # even-odd fill handles holes in the section
        inside ^= MPath(poly).contains_points(q)
    inside = inside.reshape(gx.shape)
    dist = ndimage.distance_transform_edt(inside) * res
    spots = []
    for _ in range(n):
        i = np.unravel_index(np.argmax(dist), dist.shape)
        if dist[i] < d / 2 + margin:
            break
        c = np.array([gx[i], gy[i]])
        spots.append(c)
        dist[np.hypot(gx - c[0], gy - c[1]) < max(3 * d, (hi - lo).max() / (n + 1))] = 0
    return spots


def cmd_cut(a):
    m = load(a.input)
    axis = "xyz".index(a.axis)
    R = np.eye(4)
    if axis != 2:  # rotate so the cut axis becomes Z, cut, rotate back
        R = trimesh.transformations.rotation_matrix(np.pi / 2, [0, 1, 0] if axis == 0 else [1, 0, 0])
        if axis == 1:
            R = trimesh.transformations.rotation_matrix(-np.pi / 2, [1, 0, 0])
        m.apply_transform(R)
    man = to_man(m)
    upper, lower = man.split_by_plane((0.0, 0.0, 1.0), float(a.at))
    pins = None
    if a.pins:
        polys = [np.asarray(p) for p in man.slice(float(a.at)).to_polygons()]
        spots = pin_spots(polys, a.pins, a.pin_d, margin=1.2)
        if len(spots) < a.pins:
            print(f"warning: only room for {len(spots)} pin(s) of {a.pin_d} mm in this section")
        hole_d, hole_h = a.pin_d + a.clearance, a.pin_depth + 0.4
        for c in spots:
            lower -= cylinder(hole_d, hole_h, a.at - hole_h, c)
            upper -= cylinder(hole_d, hole_h, a.at, c)
        if spots:
            pin = cylinder(a.pin_d, 2 * a.pin_depth - 0.4, 0, (0, 0))
            pins = m3d.Manifold.batch_boolean([pin.translate((i * (a.pin_d + 3), 0, 0)) for i in range(len(spots))],
                                              m3d.OpType.Add)
        print(f"pins at {[np.round(s, 1).tolist() for s in spots]} (hole {hole_d} mm x {hole_h} mm each side)")
    Rinv = np.linalg.inv(R)
    lo_m, up_m = to_tri(lower), to_tri(upper)
    lo_m.apply_transform(Rinv)
    up_m.apply_transform(Rinv)
    if not a.no_flip and axis == 2:  # print the upper half with its flat cut face on the bed
        up_m.apply_transform(trimesh.transformations.rotation_matrix(np.pi, [1, 0, 0]))
    save(to_bed(lo_m), f"{a.out_prefix}_lower.stl", "lower: ")
    save(to_bed(up_m), f"{a.out_prefix}_upper.stl", "upper: ")
    if pins:
        save(to_bed(to_tri(pins)), f"{a.out_prefix}_pins.stl", "pins: ")


def cmd_hollow(a):
    import igl
    from skimage import measure
    m = load(a.input)
    p = a.pitch
    pad = 3
    shape = np.ceil(m.extents / p).astype(int) + 2 * pad + 1
    origin = m.bounds[0] - pad * p
    axes = [origin[i] + np.arange(shape[i]) * p for i in range(3)]
    G = np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)
    S, *_ = igl.signed_distance(G, np.ascontiguousarray(m.vertices, np.float64),
                                np.ascontiguousarray(m.faces, np.int64),
                                sign_type=igl.SIGNED_DISTANCE_TYPE_FAST_WINDING_NUMBER)
    S = S.reshape(shape)
    if (S < -a.wall).sum() == 0:
        raise SystemExit("model is thinner than 2x wall everywhere; nothing to hollow")
    v, f, _, _ = measure.marching_cubes(S, level=-a.wall, spacing=(p, p, p))
    inner = trimesh.Trimesh(v + origin, f, process=True)
    inner.fix_normals()
    inner = trimesh.util.concatenate([b for b in inner.split(only_watertight=True) if b.volume > 10 * p ** 3])
    man = to_man(m) - to_man(inner)
    if a.drain:
        z0 = m.bounds[0, 2] - 1
        man -= cylinder(a.drain, a.wall + 2 + 1, z0, m.centroid[:2])
    out = to_tri(man)
    print(f"material {m.volume / 1000:.1f} -> {out.volume / 1000:.1f} cm3 ({(1 - out.volume / m.volume) * 100:.0f}% saved)")
    save(out, a.output)


def cmd_boolean(a):
    man = to_man(load(a.input))
    for p in a.add or []:
        man += to_man(load(p))
    for p in a.subtract or []:
        man -= to_man(load(p))
    save(to_tri(man), a.output)


CAP = 0.72  # capital-letter height / font size, for the default fonts


def check_font(font):
    if not font:
        return
    from matplotlib import font_manager
    try:
        font_manager.findfont(font_manager.FontProperties(family=font), fallback_to_default=False)
    except ValueError:
        raise SystemExit(f"font '{font}' is not installed (it would silently fall back to the default). "
                         f"List fonts: fc-list or Font Book.")


def text_solid(text, size, depth, font):
    """Text as a solid: reads along +X, up is +Y, extruded 0..depth along +Z, centred in X/Y."""
    from build123d import Text, export_stl, extrude
    kw = {"font": font} if font else {}
    solid = extrude(Text(text, font_size=size, **kw), amount=depth)
    with tempfile.TemporaryDirectory() as td:
        export_stl(solid, f"{td}/t.stl", tolerance=0.02)
        t = trimesh.load(f"{td}/t.stl", force="mesh", process=True)
    t.apply_translation([-t.bounds[:, 0].mean(), -t.bounds[:, 1].mean(), 0])
    return t


SIDES = {"front": [0, -1, 0], "back": [0, 1, 0], "left": [-1, 0, 0], "right": [1, 0, 0], "top": [0, 0, 1]}


def cmd_text(a):
    check_font(a.font)
    m = load(a.input)
    n = np.array(SIDES[a.side], float)
    size = a.letter_height / CAP if a.letter_height else a.size
    depth = abs(a.depth)
    c = m.bounds.mean(0)
    if a.height_at is not None and a.side != "top":
        c[2] = a.height_at
    u = np.cross(UP, n) if a.side != "top" else np.array([1.0, 0, 0])
    v = np.cross(n, u)
    du, dv = (a.offset or [0.0, 0.0])
    c = c + u * du + v * dv
    hits, *_ = m.ray.intersects_location([c + n * m.extents.max() * 2], [-n], multiple_hits=False)
    if not len(hits):
        raise SystemExit("ray missed the model: adjust --height-at / --offset")
    surf = hits[0]
    probe = text_solid(a.text, size, 1.0, a.font)
    tw, th = probe.extents[0], probe.extents[1]
    print(f"text '{a.text}': {tw:.1f} mm wide, letters {th:.1f} mm tall (font size {size:.1f})")
    if th < 5.5 and a.side != "top":
        print("  note: letters under ~6 mm on vertical faces get hard to read in FDM")

    if a.wrap:  # bend the text around a vertical axis so the relief is even on round surfaces
        sec = m.section(plane_origin=[0, 0, surf[2]], plane_normal=[0, 0, 1])
        axis = sec.bounds.mean(0)[:2] if sec is not None else m.bounds.mean(0)[:2]
        R = float(np.linalg.norm(surf[:2] - axis))
        theta0 = np.arctan2(surf[1] - axis[1], surf[0] - axis[0])
        tangent = np.array([-np.sin(theta0), np.cos(theta0), 0])
        sgn = 1.0 if np.dot(u, tangent) >= 0 else -1.0
        if tw / R > np.pi * 0.9:
            raise SystemExit(f"text wraps {np.degrees(tw / R):.0f} deg around a {R:.1f} mm radius: too long")
        span = depth + 0.5 if not a.engrave else depth + 1.0
        t = text_solid(a.text, size, span, a.font)
        v_, f_ = trimesh.remesh.subdivide_to_size(t.vertices, t.faces, max_edge=0.3)
        x, y, z = v_[:, 0], v_[:, 1], v_[:, 2]
        r = (R - 0.5 + z) if not a.engrave else (R - depth + z)
        th_ = theta0 + sgn * x / R
        W = np.c_[axis[0] + r * np.cos(th_), axis[1] + r * np.sin(th_), surf[2] + y]
        t = trimesh.Trimesh(W, f_, process=True)
        if t.volume < 0:
            t.invert()
        print(f"  wrapped around a vertical axis at ({axis[0]:.1f}, {axis[1]:.1f}), radius {R:.1f} mm")
    else:
        # flat text: measure how far the surface falls away under the text's ends and sink it
        # (emboss) or cut (engrave) that much deeper so it stays fused / fully cut everywhere
        pts = [surf + u * a_ + v * b_ for a_ in (-tw / 2, 0, tw / 2) for b_ in (-th / 2, 0, th / 2)]
        hits2, idx2, _ = m.ray.intersects_location([p_ + n * 50 for p_ in pts], [-n] * len(pts), multiple_hits=False)
        recess = max([float(np.dot(surf - h, n)) for h in hits2] + [0.0])
        limit = max(2.0, 0.25 * min(tw, th))
        if len(idx2) < len(pts) or recess > limit:
            raise SystemExit(f"text ({tw:.1f} x {th:.1f} mm) doesn't sit on one flat-ish surface here: its edges "
                             f"{'miss the model' if len(idx2) < len(pts) else f'fall {recess:.1f} mm behind it'}. "
                             f"On round surfaces use --wrap; otherwise smaller text or move it (--height-at/--offset).")
        if recess > 0.3:
            print(f"  surface curves away {recess:.2f} mm under the text ends (consider --wrap for even depth)")
        t = text_solid(a.text, size, depth + 0.5 + recess + (1.0 if a.engrave else 0), a.font)
        M = np.eye(4)
        M[:3, 0], M[:3, 1], M[:3, 2] = u, v, n
        M[:3, 3] = surf - n * ((depth + recess) if a.engrave else (0.5 + recess))
        t.apply_transform(M)
    man = to_man(m) - to_man(t) if a.engrave else to_man(m) + to_man(t)
    save(to_tri(man), a.output, f"{'engraved' if a.engrave else 'embossed'} '{a.text}' on {a.side} -> ")


def footprint(m, side="bottom"):
    """XY points of the model's bottom (or top) contact region and the centre of their bounding box."""
    tol = max(0.5, m.extents[2] * 0.02)
    sel = m.vertices[:, 2] < m.bounds[0, 2] + tol if side == "bottom" else m.vertices[:, 2] > m.bounds[1, 2] - tol
    pts = m.vertices[sel][:, :2]
    return pts, (pts.min(0) + pts.max(0)) / 2


def cmd_pocket(a):
    import ps_config
    cfg = ps_config.load()
    m = load(a.input)
    xy = np.array(a.at, float) if a.at else footprint(m, a.side)[1]
    seg = 6 if a.shape == "hex" else 96
    d = a.d / np.cos(np.pi / 6) if a.shape == "hex" else a.d  # hex: --d is across flats
    roof = a.roof or ("cone" if a.side == "bottom" else "flat")
    if a.side == "bottom":
        z0 = m.bounds[0, 2]
        tool = cylinder(d, a.depth + 1, z0 - 1, xy, seg)
        top_of_pocket = z0 + a.depth
        hits, *_ = m.ray.intersects_location([[xy[0], xy[1], top_of_pocket]], [[0, 0, 1]], multiple_hits=False)
        headroom = (hits[0][2] - top_of_pocket) if len(hits) else 0.0
        if roof == "cone":
            cone_h = d / 2  # 45 deg: prints without support inside the pocket
            if headroom < cone_h + cfg["min_wall_mm"]:
                print(f"  not enough material above for a cone roof ({headroom:.1f} mm); using a flat roof")
                roof = "flat"
            else:
                tool += m3d.Manifold.cylinder(cone_h, d / 2, 0.01, seg).translate((xy[0], xy[1], top_of_pocket))
        if roof == "flat" and d > cfg["max_bridge_mm"]:
            print(f"  warning: flat {d:.1f} mm roof is a long bridge: the slicer may fill the pocket with support")
        if headroom < cfg["min_wall_mm"]:
            print(f"  WARNING: only {headroom:.2f} mm of material above the pocket")
    else:
        tool = cylinder(d, a.depth + 1, m.bounds[1, 2] - a.depth, xy, seg)
    save(to_tri(to_man(m) - tool), a.output,
         f"{a.shape} pocket d{a.d} x {a.depth} on {a.side} at ({xy[0]:.1f}, {xy[1]:.1f}), {roof} roof -> ")


def cmd_plinth(a):
    m = to_bed(load(a.input))
    if a.cover == "silhouette":  # whole outline seen from above (big; every overhang lands on the base)
        pts = m.convex_hull.vertices[:, :2]
    elif a.cover == "body":  # lower 15% of the figure: feet, legs, tail base (typical figurine base)
        pts = m.vertices[m.vertices[:, 2] < m.bounds[0, 2] + 0.15 * m.extents[2]][:, :2]
    else:  # only what touches the ground
        pts = footprint(m)[0]
    c = (pts.min(0) + pts.max(0)) / 2
    h, ch = a.height, min(a.chamfer, a.height / 3)
    b = min(0.4, a.height / 4)  # small bottom chamfer against elephant's foot
    if a.shape == "round":
        r = float(np.linalg.norm(pts - c, axis=1).max() + a.margin)
        seg = max(96, int(2 * np.pi * r / 0.4))
        # one revolved profile (stacked cylinders only touch, and stay separate bodies)
        prof = m3d.CrossSection([[(0, 0), (r - b, 0), (r, b), (r, h - ch), (r - ch, h), (0, h)]])
        base = m3d.Manifold.revolve(prof, seg).translate((c[0], c[1], 0))
        desc = f"round plinth: centre ({c[0]:.2f}, {c[1]:.2f}), radius {r:.2f}, height {h}"
    else:
        lo, hi = pts.min(0) - a.margin, pts.max(0) + a.margin
        w, d_ = hi - lo
        body = m3d.Manifold.cube((w, d_, h - ch)).translate((lo[0], lo[1], 0))
        cap = m3d.Manifold.cube((w - 2 * ch, d_ - 2 * ch, h)).translate((lo[0] + ch, lo[1] + ch, 0))
        base = m3d.Manifold.batch_hull([body, cap])
        desc = f"rect plinth: centre ({c[0]:.2f}, {c[1]:.2f}), {w:.1f} x {d_:.1f}, height {h}"
    m.apply_translation([0, 0, h - 0.3])  # overlap 0.3 mm so the union fuses
    print(desc)
    print(f"  model raised {h - 0.3:.1f} mm; text on its side: --height-at {h / 2:.1f}"
          f"{' --wrap' if a.shape == 'round' else ''} (letters up to ~{max(h - 3, 0):.0f} mm tall); "
          f"magnet pocket: pocket --side bottom (auto-centred)")
    save(to_tri(to_man(m) + base), a.output)


def xyz(n):
    return {"type": float, "nargs": n}


ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
sub = ap.add_subparsers(dest="cmd", required=True)
p = sub.add_parser("scale"); p.add_argument("input"); p.add_argument("output")
g = p.add_mutually_exclusive_group(required=True)
g.add_argument("--factor", type=float); g.add_argument("--height", type=float); g.add_argument("--width", type=float)
g.add_argument("--fit", type=float, nargs=3)
p = sub.add_parser("transform"); p.add_argument("input"); p.add_argument("output")
p.add_argument("--rotate", **xyz(3), metavar=("RX", "RY", "RZ")); p.add_argument("--translate", **xyz(3), metavar=("X", "Y", "Z"))
p.add_argument("--mirror", choices=list("xyz")); p.add_argument("--to-bed", action="store_true")
p = sub.add_parser("cut"); p.add_argument("input"); p.add_argument("out_prefix"); p.add_argument("--at", type=float, required=True)
p.add_argument("--axis", choices=list("xyz"), default="z"); p.add_argument("--pins", type=int, default=0)
p.add_argument("--pin-d", type=float, default=5.0); p.add_argument("--pin-depth", type=float, default=6.0)
p.add_argument("--clearance", type=float, default=0.25); p.add_argument("--no-flip", action="store_true")
p = sub.add_parser("hollow"); p.add_argument("input"); p.add_argument("output"); p.add_argument("--wall", type=float, default=2.0)
p.add_argument("--drain", type=float, default=0); p.add_argument("--pitch", type=float, default=0.5)
p = sub.add_parser("boolean"); p.add_argument("input"); p.add_argument("output"); p.add_argument("--add", nargs="+"); p.add_argument("--subtract", nargs="+")
p = sub.add_parser("text"); p.add_argument("input"); p.add_argument("output"); p.add_argument("--text", required=True)
p.add_argument("--side", choices=list(SIDES), default="front")
p.add_argument("--size", type=float, default=8.5, help="font size (letters are ~0.72x this tall)")
p.add_argument("--letter-height", type=float, help="capital letter height in mm (overrides --size)")
p.add_argument("--depth", type=float, default=1.0); p.add_argument("--engrave", action="store_true")
p.add_argument("--wrap", action="store_true", help="bend text around a vertical axis (round bases, cylinders)")
p.add_argument("--height-at", type=float); p.add_argument("--offset", **xyz(2), metavar=("U", "V")); p.add_argument("--font")
p = sub.add_parser("pocket"); p.add_argument("input"); p.add_argument("output"); p.add_argument("--d", type=float, required=True)
p.add_argument("--depth", type=float, required=True); p.add_argument("--shape", choices=["cyl", "hex"], default="cyl")
p.add_argument("--at", **xyz(2), metavar=("X", "Y")); p.add_argument("--side", choices=["bottom", "top"], default="bottom")
p.add_argument("--roof", choices=["cone", "flat"], help="bottom pockets: cone (default, no support inside) or flat")
p = sub.add_parser("plinth"); p.add_argument("input"); p.add_argument("output"); p.add_argument("--shape", choices=["round", "rect"], default="round")
p.add_argument("--margin", type=float, default=3); p.add_argument("--height", type=float, default=4); p.add_argument("--chamfer", type=float, default=0.8)
p.add_argument("--cover", choices=["body", "silhouette", "contact"], default="body",
               help="what the base must cover: lower body (default), whole outline from above, or ground contact")

if __name__ == "__main__":
    a = ap.parse_args()
    globals()[f"cmd_{a.cmd}"](a)
