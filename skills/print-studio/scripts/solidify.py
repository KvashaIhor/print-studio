"""Turn a raw AI / scanned / downloaded mesh into ONE watertight solid, scaled and Z-up.

Strategies, tried in order (`--method auto`); each result must pass a size check against the
input (all three extents within 3%) or it is rejected; if none passes the script FAILS (exit 2)
instead of handing back a fragment:
 1. direct  - weld, decimate, pymeshfix hole-fill. Keeps the original surface exactly (narrow
              grooves like eye sockets and toe gaps survive). Also needs >=95% of faces kept.
 2. wn-vis  - orient every face towards its more open side (two-sided ambient occlusion), drop
              faces buried inside (double layers), majority-filter stragglers, then generalized
              winding number on a voxel grid + shrinkwrap onto the original surface. For badly
              broken meshes (inside-out patches, inner layers): the 115 mm Batman needed this.
 3. wn      - same fill, but orientation only by trimesh fix_winding/fix_normals (fast; enough
              for cleaner meshes).
The winding methods turn grooves narrower than --pitch into a saw-tooth; inspect them.
Never use plain voxel remesh / binary-voxel marching cubes / full pymeshfix alone on messy
meshes (see references/lessons.md).

Usage:
  python solidify.py IN OUT.stl [--up z|y] [--height MM] [--method auto|direct|wn-vis|wn]
                     [--max-faces 1500000] [--pitch 0.25]
Prints a JSON report (method used, every attempt and why it was rejected).
"""
import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

T0 = time.time()


def log(msg):
    print(f"[solidify +{time.time() - T0:5.1f}s] {msg}", flush=True)


def size_ok(out, ref, tol=0.03):
    return bool(np.all(np.abs(out.extents - ref.extents) <= tol * ref.extents.max()))


def direct(mesh):
    import pymeshfix
    fx = pymeshfix.MeshFix(np.asarray(mesh.vertices), np.asarray(mesh.faces))
    fx.repair(joincomp=False, remove_smallest_components=True)
    r = trimesh.Trimesh(fx.points, fx.faces, process=True)
    r.fix_normals()
    kept = len(r.faces) / len(mesh.faces)
    why = []
    if kept < 0.95:
        why.append(f"kept only {kept * 100:.0f}% of faces")
    if not (r.is_watertight and r.body_count == 1):
        why.append(f"watertight={r.is_watertight}, bodies={r.body_count}")
    return r, why


def visibility_orient(mesh, samples=128, drop=0.995):
    """Flip each face to point at its more open side; drop faces that see out from neither side."""
    import igl.embree
    V = np.ascontiguousarray(mesh.vertices, np.float64)
    F = np.ascontiguousarray(mesh.faces, np.int64).copy()
    c, n = mesh.triangles_center, mesh.face_normals
    eps = 0.01
    occ_p = igl.embree.ambient_occlusion(V, F, np.ascontiguousarray(c + eps * n), np.ascontiguousarray(n), samples)
    occ_m = igl.embree.ambient_occlusion(V, F, np.ascontiguousarray(c - eps * n), np.ascontiguousarray(-n), samples)
    flip = occ_m < occ_p
    hidden = np.minimum(occ_p, occ_m) >= drop
    F[flip] = F[flip][:, ::-1]
    F = F[~hidden]
    log(f"visibility orientation: flipped {flip.mean() * 100:.1f}%, dropped {hidden.mean() * 100:.1f}% buried faces")
    return majority_fix(V, F)


def majority_fix(V, F, rounds=10):
    """Flip faces whose edge-neighbours mostly disagree with their winding."""
    nF, nV = len(F), len(V)
    for r in range(rounds):
        de = np.stack([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]], 1).reshape(-1, 2)
        fid = np.repeat(np.arange(nF), 3)
        sgn = np.where(de[:, 0] < de[:, 1], 1, -1)
        key = np.sort(de, 1)
        key = key[:, 0].astype(np.int64) * (nV + 1) + key[:, 1]
        order = np.argsort(key, kind="stable")
        ks = key[order]
        start = np.r_[True, ks[1:] != ks[:-1]]
        idx = np.cumsum(start) - 1
        two = np.bincount(idx)[idx] == 2
        o2 = order[two]
        i0, i1 = o2[0::2], o2[1::2]
        bad = sgn[i0] == sgn[i1]
        fa, fb = fid[i0], fid[i1]
        nbad = np.bincount(np.r_[fa[bad], fb[bad]], minlength=nF)
        ngood = np.bincount(np.r_[fa[~bad], fb[~bad]], minlength=nF)
        flip = (nbad >= 2) & (nbad > ngood)
        if r % 2:
            flip &= nbad == 3
        if not flip.any():
            break
        F[flip] = F[flip][:, ::-1]
    log(f"majority filter: {int(bad.sum())} inconsistent edges left")
    return trimesh.Trimesh(V, F, process=False)


def winding(mesh, pitch, orient, band=2):
    import igl
    from scipy import ndimage
    from skimage import measure
    if orient == "vis":
        mesh = visibility_orient(mesh)
    else:
        trimesh.repair.fix_winding(mesh)
        trimesh.repair.fix_normals(mesh, multibody=True)
    V = np.ascontiguousarray(mesh.vertices, np.float64)
    F = np.ascontiguousarray(mesh.faces, np.int64)
    pad = band + 2
    shape = np.ceil(mesh.extents / pitch).astype(int) + 2 * pad + 1
    origin = mesh.bounds[0] - pad * pitch
    axes = [origin[i] + np.arange(shape[i]) * pitch for i in range(3)]
    G = np.stack(np.meshgrid(*axes, indexing="ij"), -1).reshape(-1, 3)
    W = np.clip(igl.fast_winding_number(V, F, G).reshape(shape).astype(np.float32), 0, 1)
    inside = W > 0.5
    lab, n = ndimage.label(inside)
    if n > 1:
        keep = lab == (np.argmax(ndimage.sum(inside, lab, range(1, n + 1))) + 1)
        W[~keep & inside] = 0
    verts, faces, _, _ = measure.marching_cubes(W, level=0.5, spacing=(pitch,) * 3)
    out = trimesh.Trimesh(verts + origin, faces, process=True)
    _, _, closest, _ = igl.signed_distance(np.ascontiguousarray(out.vertices, np.float64), V, F,
                                           sign_type=igl.SIGNED_DISTANCE_TYPE_UNSIGNED)
    snap = np.linalg.norm(closest - out.vertices, axis=1) < band * pitch
    out.vertices[snap] = closest[snap]
    trimesh.smoothing.filter_taubin(out, iterations=3)
    out = max(out.split(only_watertight=False), key=lambda p: len(p.faces))
    out.fix_normals()
    why = [] if (out.is_watertight and out.body_count == 1) else [f"watertight={out.is_watertight}"]
    return out, why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("output")
    ap.add_argument("--up", choices=["z", "y"], default="z",
                    help="TRELLIS --no-texture OBJ is z; textured TRELLIS GLB and most web GLBs are y")
    ap.add_argument("--height", type=float, help="scale to this height (mm)")
    ap.add_argument("--method", choices=["auto", "direct", "wn-vis", "wn"], default="auto")
    ap.add_argument("--max-faces", type=int, default=1_500_000)
    ap.add_argument("--pitch", type=float, default=0.25)
    a = ap.parse_args()

    m = trimesh.load(a.input, force="mesh", process=False)
    m = trimesh.Trimesh(m.vertices, m.faces, process=True)  # weld UV-seam duplicates
    n0 = len(m.faces)
    if n0 > a.max_faces:
        import fast_simplification
        v, f = fast_simplification.simplify(np.asarray(m.vertices, np.float32), np.asarray(m.faces),
                                            target_reduction=1 - a.max_faces / n0)
        m = trimesh.Trimesh(v, f, process=True)
        log(f"decimated {n0} -> {len(m.faces)} faces")
    if a.up == "y":
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    if a.height:
        m.apply_scale(a.height / m.extents[2])
    m.apply_translation(-m.bounds[0])
    log(f"input: {len(m.faces)} faces, extents {np.round(m.extents, 1)} mm, parts {m.body_count}")

    plan = {"auto": ["direct", "wn-vis", "wn"], "direct": ["direct"], "wn-vis": ["wn-vis"], "wn": ["wn"]}[a.method]
    attempts, out, used = [], None, None
    for meth in plan:
        t = time.time()
        if meth == "direct":
            res, why = direct(m.copy())
        else:
            res, why = winding(m.copy(), a.pitch, "vis" if meth == "wn-vis" else "fix")
        if not size_ok(res, m):
            why.append(f"size changed {np.round(m.extents, 1).tolist()} -> {np.round(res.extents, 1).tolist()} mm "
                       f"(lost parts)")
        attempts.append({"method": meth, "ok": not why, "why": why, "seconds": round(time.time() - t, 1)})
        log(f"{meth}: {'ACCEPT' if not why else 'reject: ' + '; '.join(why)}")
        if not why:
            out, used = res, meth
            break
    rep = {"input_extents_mm": [round(float(x), 2) for x in m.extents], "attempts": attempts}
    if out is None:
        rep["method"] = None
        print(json.dumps(rep, indent=1))
        print("SOLIDIFY FAILED: no method produced a complete solid. Do not continue with this mesh: "
              "regenerate it (other seed / cleaner reference image) or inspect the raw mesh.", file=sys.stderr)
        sys.exit(2)
    Path(a.output).parent.mkdir(parents=True, exist_ok=True)
    out.export(a.output)
    rep.update({"method": used, "output": a.output, "watertight": bool(out.is_watertight),
                "bodies": int(out.body_count), "faces": int(len(out.faces)),
                "volume_cm3": round(float(out.volume) / 1000, 2),
                "extents_mm": [round(float(x), 2) for x in out.extents]})
    print(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
