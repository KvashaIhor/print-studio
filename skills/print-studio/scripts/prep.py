"""Make a (watertight) mesh print-ready: orient Z-up, scale, centre on the plate, trim a flat
base, export STL + 3MF, run the mesh check.

Usage:
  python prep.py IN OUT_DIR [--up z|y] [--height MM | --scale F] [--base-cut MM] [--name NAME]
  --up y        input is Y-up (textured TRELLIS GLB, most GLB/OBJ from the web); default z
  --height      scale uniformly so the model is this tall (Z); --scale multiplies instead
  --base-cut    mm sliced off the bottom for a flat contact patch (organic models: 0.6-1.0;
                parts that already have a flat bottom: 0)
"""
import argparse
import subprocess
import sys
from pathlib import Path

import manifold3d as m3d
import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("out_dir")
    ap.add_argument("--up", choices=["z", "y"], default="z")
    ap.add_argument("--height", type=float)
    ap.add_argument("--scale", type=float)
    ap.add_argument("--base-cut", type=float, default=0.0)
    ap.add_argument("--name")
    a = ap.parse_args()

    m = trimesh.load(a.input, force="mesh", process=True)
    if a.up == "y":
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0]))
    if not m.is_watertight:
        raise SystemExit("input is not watertight: run solidify.py (organic/AI meshes) or fix the CAD first")
    if a.height:  # the base trim removes base_cut mm afterwards: aim for height + cut
        m.apply_scale((a.height + a.base_cut) / m.extents[2])
    elif a.scale:
        m.apply_scale(a.scale)
    shift = np.array([-m.bounds[:, 0].mean(), -m.bounds[:, 1].mean(), -m.bounds[0, 2]])
    m.apply_translation(shift)
    print(f"centred on the plate: moved by ({shift[0]:.2f}, {shift[1]:.2f}, {shift[2]:.2f}) mm "
          f"(add this to coordinates measured on the input)")

    if a.base_cut > 0:
        man = m3d.Manifold(m3d.Mesh(vert_properties=np.asarray(m.vertices, np.float32),
                                    tri_verts=np.asarray(m.faces, np.uint32)))
        if man.status() != m3d.Error.NoError:
            raise SystemExit(f"manifold rejected the mesh ({man.status()}); solidify it first")
        out = man.trim_by_plane(normal=(0.0, 0.0, 1.0), origin_offset=float(a.base_cut)).to_mesh()
        m = trimesh.Trimesh(np.asarray(out.vert_properties)[:, :3], np.asarray(out.tri_verts), process=True)
        m.apply_translation([0, 0, -m.bounds[0, 2]])
        print(f"trimmed {a.base_cut} mm off the bottom: z coordinates shifted by -{a.base_cut} mm")

    od = Path(a.out_dir)
    od.mkdir(parents=True, exist_ok=True)
    name = a.name or Path(a.input).stem
    stl, mf = od / f"{name}.stl", od / f"{name}.3mf"
    m.export(stl)
    trimesh.Scene({name: m}).export(mf)  # object shows up as NAME in Bambu Studio's object list
    print(f"wrote {stl} and {mf}: {np.round(m.extents, 1)} mm, {m.volume / 1000:.2f} cm3")
    sys.exit(subprocess.run([sys.executable, str(HERE / "check_mesh.py"), str(stl)]).returncode)


if __name__ == "__main__":
    main()
