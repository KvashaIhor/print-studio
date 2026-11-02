"""Smooth away a small local defect (notch, spike, fold) around one 3D point, leaving the rest
of the surface untouched. Find the point with `render.py closeup` + `render.py pick`.

Usage:
  python fix_spot.py IN OUT --at X Y Z [--radius 0.7] [--fade 1.3] [--iters 15]   (or --at=X,Y,Z)
  radius: fully smoothed within this many mm; fade: blends back to the original by this distance.
Start small (0.5-0.7 mm). Too large erases real detail (a 1.2 mm radius erased a toe groove).
Don't smooth the whole model instead: global smoothing makes decimated meshes grainy.
"""
import argparse
from pathlib import Path

import numpy as np
import scipy.sparse as sp
import trimesh

ap = argparse.ArgumentParser()
ap.add_argument("input")
ap.add_argument("output")
ap.add_argument("--at", required=True, nargs="+")
ap.add_argument("--radius", type=float, default=0.7)
ap.add_argument("--fade", type=float, default=1.3)
ap.add_argument("--iters", type=int, default=15)
a = ap.parse_args()

m = trimesh.load(a.input, force="mesh")
V = m.vertices.copy()
n = len(V)
c = np.array([float(v) for t in a.at for v in t.replace(",", " ").split()])
dist = np.linalg.norm(V - c, axis=1)
w = np.clip((a.fade - dist) / max(a.fade - a.radius, 1e-6), 0, 1)
idx = np.where(w > 0)[0]
if len(idx) == 0:
    raise SystemExit("no vertices near --at; check the coordinates (same frame as the file?)")
e = m.edges_unique
A = sp.coo_matrix((np.ones(len(e) * 2), (np.r_[e[:, 0], e[:, 1]], np.r_[e[:, 1], e[:, 0]])), shape=(n, n)).tocsr()
deg = np.asarray(A.sum(1)).ravel()
S = V.copy()
for _ in range(a.iters):
    S[idx] = 0.5 * S[idx] + 0.5 * ((A @ S) / deg[:, None])[idx]
out = trimesh.Trimesh(V + (S - V) * w[:, None], m.faces, process=False)
moved = np.linalg.norm(out.vertices - V, axis=1)
print(f"smoothed {len(idx)} vertices, max move {moved.max():.3f} mm; watertight={out.is_watertight}; "
      f"volume {m.volume / 1000:.3f} -> {out.volume / 1000:.3f} cm3")
Path(a.output).parent.mkdir(parents=True, exist_ok=True)
out.export(a.output)
