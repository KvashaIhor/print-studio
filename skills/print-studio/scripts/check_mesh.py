"""Print-readiness report for a mesh (STL/3MF/OBJ/GLB), against the print-studio config (ps_config.py).

Checks: watertight + consistent winding, body count, volume, size vs build plate, flat base
contact, tip-over stability, overhang area, walls thinner than the printer minimum.

Usage:  python check_mesh.py MODEL [--json]
Exit codes: 0 ready, 2 blocking problem (not watertight / several bodies / too big / no base),
            1 ready with warnings (thin walls, big overhangs, may tip over).
"""
import argparse
import json
import sys

import igl
import numpy as np
import trimesh
from scipy.spatial import ConvexHull, Delaunay

import ps_config

CFG = ps_config.load()


def load(path):
    m = trimesh.load(path, force="mesh", process=True)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--json", action="store_true", help="print only JSON")
    args = ap.parse_args()

    m = load(args.model)
    plate = np.array(CFG["build_volume_mm"], float)
    r = {"file": str(args.model), "faces": int(len(m.faces)),
         "watertight": bool(m.is_watertight), "winding_consistent": bool(m.is_winding_consistent),
         "extents_mm": [round(float(x), 2) for x in m.extents]}
    bodies = m.split(only_watertight=False)
    r["bodies"] = len(bodies)
    if len(bodies) > 1:
        r["body_volumes_cm3"] = sorted([round(abs(b.volume) / 1000, 3) for b in bodies], reverse=True)[:8]
    if m.is_watertight:
        r["volume_cm3"] = round(float(m.volume) / 1000, 2)
    r["fits_plate"] = bool(np.all(np.sort(m.extents) <= np.sort(plate)))

    # Base: faces lying on the lowest z and pointing down.
    zmin = m.bounds[0, 2]
    down = (m.face_normals[:, 2] < -0.99) & (m.triangles_center[:, 2] < zmin + 0.05)
    r["base_contact_mm2"] = round(float(m.area_faces[down].sum()), 1)

    # Stability: centre of mass must project inside the base contact's convex hull.
    if down.any() and m.is_watertight:
        pts2 = m.triangles[down][:, :, :2].reshape(-1, 2)
        try:
            hull = ConvexHull(pts2)
            inside = Delaunay(pts2[hull.vertices]).find_simplex(m.center_mass[:2]) >= 0
            r["stable_on_base"] = bool(inside)
        except Exception:
            r["stable_on_base"] = None

    # Overhangs: downward-facing area steeper than the printer limit, excluding the base.
    # normal z below -lim => overhang; +0.5 deg tolerance so exact-45 deg chamfers don't flip
    # in and out of the count when the part is merely rotated (float rounding)
    lim = np.cos(np.radians(90 - CFG["max_overhang_deg"] - 0.5))
    over = (m.face_normals[:, 2] < -lim) & ~down
    r["overhang_area_mm2"] = round(float(m.area_faces[over].sum()), 1)
    r["overhang_pct_of_surface"] = round(float(m.area_faces[over].sum() / m.area * 100), 2)

    # Thin walls: step min_wall inward from surface samples; outside => wall thinner than that.
    if m.is_watertight:
        V = np.ascontiguousarray(m.vertices, np.float64)
        F = np.ascontiguousarray(m.faces, np.int64)
        pts, fi = trimesh.sample.sample_surface_even(m, min(200_000, max(20_000, len(m.faces))))
        n = m.face_normals[fi]
        for d in (CFG["min_wall_mm"] / 2, CFG["min_wall_mm"]):
            w = igl.fast_winding_number(V, F, np.ascontiguousarray(pts - n * d))
            thin = w < 0.5
            r[f"thinner_than_{d:g}mm_pct"] = round(float(thin.mean() * 100), 3)
            if d == CFG["min_wall_mm"] and thin.any():
                z = pts[thin, 2]
                r["thin_wall_z_range_mm"] = [round(float(np.percentile(z, 5)), 1), round(float(np.percentile(z, 95)), 1)]
                # where: bin thin samples into 4 mm cells, report the biggest clusters (use with
                # render.py closeup --at X Y Z to look at them)
                cells, inv, cnt = np.unique(np.floor(pts[thin] / 4.0).astype(int), axis=0,
                                            return_inverse=True, return_counts=True)
                top = np.argsort(-cnt)[:6]
                r["thin_wall_spots"] = [{"at_mm": [round(float(v), 1) for v in pts[thin][inv.ravel() == k].mean(0)],
                                         "samples": int(cnt[k])} for k in top]

    blocking, warnings = [], []
    if not (r["watertight"] and r["winding_consistent"]):
        blocking.append("mesh is not watertight / has inconsistent winding")
    if r["bodies"] > 1:
        blocking.append(f"{r['bodies']} separate bodies (fine only if intended as separate parts)")
    if not r["fits_plate"]:
        blocking.append(f"too big for the {plate.tolist()} mm plate: cut it or scale down")
    if r["base_contact_mm2"] < 20:
        blocking.append("almost no flat base contact: trim a flat base or plan a support/brim")
    if r.get("stable_on_base") is False:
        warnings.append("centre of mass is outside the base: may tip over (add a plinth or brim)")
    thin_key = f"thinner_than_{CFG['min_wall_mm']:g}mm_pct"
    if r.get(thin_key, 0) > 0.5:
        warnings.append(f"walls thinner than {CFG['min_wall_mm']} mm on {r[thin_key]}% of surface")
    if r["overhang_pct_of_surface"] > 5:
        warnings.append(f"{r['overhang_pct_of_surface']}% of the surface overhangs >{CFG['max_overhang_deg']} deg: needs supports or reorientation")
    r["blocking"], r["warnings"] = blocking, warnings
    r["verdict"] = "BLOCKED" if blocking else ("OK with warnings" if warnings else "READY")

    if args.json:
        print(json.dumps(r, indent=1))
    else:
        print(json.dumps(r, indent=1))
        print(f"\nVERDICT: {r['verdict']}")
        for b in blocking:
            print("  ✗", b)
        for w in warnings:
            print("  !", w)
    sys.exit(2 if blocking else (1 if warnings else 0))


if __name__ == "__main__":
    main()
