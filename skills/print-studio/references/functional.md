# Functional route: exact parts with build123d

Copy `assets/cad_template.py` to `work/<job>/part.py`, set PARAMETERS, write `build()`, run
`$PY work/<job>/part.py work/<job>/out` → STL + STEP + 3MF. Keep the parameters at the top and named
after real-world things (`PHONE_WIDTH`, `SCREW`), so the user can ask for "2 mm wider" and you change
one number. The template already loads clearances, hole allowance and min wall from printer.json and
has helpers: `clearance_hole`, `insert_hole`, `nut_trap`, `countersink`, `chamfer_bottom`.

## Orientation conventions
Model the part in its **print orientation** (flat side on Z=0) with the side a person looks at
facing **-Y** (that's "front" in renders and Bambu Studio). Holes along X or Y: rotate the hole's Location — `Location((x, y, z), (90, 0, 0))` puts the hole
axis along Y, `(0, 90, 0)` along X. Put the Location on the face where the screw head goes and
confirm in a `render.py closeup` (the `below`/`side` tiles) that the countersink is on that side.

## Get the numbers right first
- Fit-critical dimensions come from the user's calipers, not guesses. Ask once, list what you need.
- Add clearance on the *printed* side: holes +0.2 mm (hole_allowance), sliding fits +0.2-0.3 per side,
  press fits +0.1. Moving parts (hinges, lids) 0.3-0.4. Values in printer.json `clearance_mm`.
- Drop-in holders/sleeves built from **approximate** user measurements ("about 136 x 35 x 9"):
  0.8-1.0 mm per side, and say which dimension to double-check.
- If a fit is uncertain, offer a 5-minute **test coupon** (just the mating feature, few grams) first.
  Record proven values in printer.json `proven` so later parts reuse them.

## Design for FDM (why parts fail)
- **Layer direction is the weak axis.** Orient so loads run along layers (a hook or bracket printed
  lying on its side; clips flexing in the XY plane). Model the part in its print orientation.
- Walls ≥ 2 perimeters (0.8 mm); structural walls 2-3 mm; ribs instead of solid bulk.
- Overhangs ≤ 45°: use chamfers (not fillets) on downward-facing edges; teardrop or flat-top holes
  for horizontal holes > ~6 mm; bridges ≤ 10 mm.
- Bottom edges: 0.3-0.5 mm chamfer (`chamfer_bottom`) so elephant's foot doesn't break fits.
- Fillet inside corners (stress) — prefer 2D fillets on sketch vertices (robust); 3D `fillet()` on
  selected edges fails easily: if it throws, try `max_fillet()` or a smaller radius.
- Screws into plastic: heat-set inserts (`insert_hole`) for anything reassembled; self-tapping into a
  hole of ~0.85× screw diameter otherwise. Nuts: hex trap pocket (`nut_trap`).
- Threads: printed threads only ≥ M8 (bd_warehouse not installed; prefer inserts/nuts).
- Text on parts: `Text()` + `extrude` (emboss ≥ 0.6 mm, engrave 0.6-1 mm, ≥ 6 mm font size).
- Snap fits: cantilever ≥ 1.5 mm thick, length ≥ 5× deflection, printed so it bends in XY.

## build123d gotchas seen here
- Class names: `CounterSinkHole`, `CounterBoreHole`, `Hole` (not "Countersink").
- `Plane.XY` profile + `extrude(amount=W)` is the most reliable way to build "bent plate" parts.
- Check `part.is_valid` and the exported STL's `is_watertight` (the template prints both).

## Slicing functional parts
`slice_check.py PART dir --supports off --walls 3 --infill 25` (4 walls for hooks/brackets under
load). If supports get generated, the part probably isn't oriented/chamfered right: fix the model.

## Verify like any other route
check_mesh → render (sheet + closeups of mating features; does the shape make sense for its job?
e.g. a hook's lip must point up) → slice_check. Then tell the user which dimensions to double-check.
