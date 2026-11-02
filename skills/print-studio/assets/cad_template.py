"""Parametric functional part (build123d). Copy this file into the job folder, edit PARAMETERS
and build(), run:  PYTHONPATH=<skill>/scripts <python> part.py OUT_DIR
Exports OUT_DIR/<name>.stl, .step (editable CAD), .3mf and prints size/volume.

Design rules live in references/functional.md; printer limits come from the print-studio config.
Conventions: model in PRINT orientation (flat side on Z=0); the side a person looks at faces -Y
("front" in renders and Bambu Studio). Slice: slice_check.py OUT.stl dir --supports off --walls 3.
"""
import sys
from pathlib import Path

from build123d import *  # noqa: F403 (build123d is designed for star import)

try:
    import ps_config  # on PYTHONPATH when run as documented above
    PRN = ps_config.load()
except ImportError:  # standalone use: the defaults from config/printer.example.json
    PRN = {"clearance_mm": {"press_fit": 0.1, "snug_slide": 0.2, "free_fit": 0.3, "moving_part": 0.4},
           "hole_allowance_mm": 0.2, "min_wall_mm": 0.8}
CLR = PRN["clearance_mm"]          # press_fit / snug_slide / free_fit / moving_part
HOLE = PRN["hole_allowance_mm"]    # printed holes come out ~0.2 mm small
MIN_WALL = PRN["min_wall_mm"]

# ---------------------------------------------------------------- PARAMETERS (edit me)
NAME = "wall_hook"
WIDTH, HEIGHT, THICK = 30.0, 60.0, 4.0     # back plate
HOOK_REACH, HOOK_LIP = 25.0, 10.0
SCREW = "M4"                                # mounting screws
FILLET = 2.0

# ---------------------------------------------------------------- helpers
# ISO metric: (clearance hole, head dia (countersunk), heat-set insert hole, insert depth, nut across-flats)
METRIC = {"M2": (2.4, 4.0, 3.2, 4.0, 4.0), "M2.5": (2.9, 5.0, 3.6, 4.5, 5.0), "M3": (3.4, 6.0, 4.0, 5.7, 5.5),
          "M4": (4.5, 8.0, 5.6, 8.1, 7.0), "M5": (5.5, 10.0, 6.4, 9.5, 8.0)}


def clearance_hole(size):
    """Through-hole diameter for a screw, including the printer's hole allowance."""
    return METRIC[size][0] + HOLE


def insert_hole(size):
    """Hole for a brass heat-set insert (diameter, depth)."""
    return METRIC[size][2], METRIC[size][3] + 1.0


def nut_trap(size, depth):
    """Hexagonal pocket sketch for a nut (use with extrude(..., mode=Mode.SUBTRACT))."""
    af = METRIC[size][4] + CLR["snug_slide"]
    return RegularPolygon(af / 2 / 0.8660254, 6)


def countersink(size):
    return CounterSinkHole(radius=clearance_hole(size) / 2, counter_sink_radius=METRIC[size][1] / 2 + 0.2)


def chamfer_bottom(part, size=0.4):
    """Small chamfer on bed-touching edges: cancels 'elephant foot' so mating parts still fit."""
    bottom = part.edges().group_by(Axis.Z)[0]
    return chamfer(bottom, size)


# ---------------------------------------------------------------- the part
def build():
    """Wall hook, modelled in its PRINT orientation: lying on its side, so layers run along the
    arm (a hook printed upright snaps between layers). Profile in XY, extruded WIDTH along Z."""
    with BuildPart() as p:
        with BuildSketch(Plane.XY) as s:
            with BuildLine():
                # back plate (x 0..THICK) with the arm along the bottom and the lip pointing UP
                Polyline((0, 0), (THICK + HOOK_REACH, 0), (THICK + HOOK_REACH, HOOK_LIP),
                         (HOOK_REACH, HOOK_LIP), (HOOK_REACH, THICK), (THICK, THICK),
                         (THICK, HEIGHT), (0, HEIGHT), close=True)
            make_face()
            fillet(s.vertices(), radius=min(FILLET, THICK / 2 - 0.1))  # 2D fillets: robust, no stress corners
        extrude(amount=WIDTH)
        # screw holes go through the back plate along X (horizontal while printing: keep them small,
        # or use a teardrop shape for holes > 6 mm so the top doesn't sag)
        for y in (HEIGHT / 2, HEIGHT - 10):  # above the arm: screwdriver access
            with Locations(Location((THICK / 2, y, WIDTH / 2), (0, 90, 0))):
                Cylinder(clearance_hole(SCREW) / 2, THICK * 3, mode=Mode.SUBTRACT)
    return p.part


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    out.mkdir(parents=True, exist_ok=True)
    part = build()
    export_stl(part, str(out / f"{NAME}.stl"), tolerance=0.01, angular_tolerance=0.1)
    export_step(part, str(out / f"{NAME}.step"))
    import trimesh
    m = trimesh.load(out / f"{NAME}.stl", force="mesh")
    m.export(out / f"{NAME}.3mf")
    bb = part.bounding_box()
    print(f"{NAME}: {bb.size.X:.1f} x {bb.size.Y:.1f} x {bb.size.Z:.1f} mm, volume {part.volume / 1000:.2f} cm3, "
          f"valid={part.is_valid}, watertight={m.is_watertight} -> {out}")
