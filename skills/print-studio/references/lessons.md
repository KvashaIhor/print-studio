# Lessons (things that went wrong once — don't repeat)

## Mesh processing (AI / scanned meshes)
| Tried | Result | Do instead |
|---|---|---|
| Full pymeshfix repair on a messy 512 TRELLIS mesh | deleted most of the body, kept the head | `solidify.py` (accepts direct repair only if ≥95% faces kept & size unchanged) |
| Blender voxel remesh | hollow 0.5 mm skin (holes let the inside leak) | winding-number fill |
| Hole patch + dilate/erode + flood fill | filled real cavities: torn inner ears, a ribbed collar in the neck gap | winding number never fills open cavities |
| Binary voxels → marching cubes (even blurred, even finer grid) | contour-ring terraces the user saw in Bambu Studio | shrinkwrap vertices back onto the original surface |
| Winding number + shrinkwrap at 0.25 mm pitch | saw-tooth rim around eye sockets (groove narrower than the grid) | direct repair first (keeps the original surface) |
| `fast_simplification` | fine; MeshLab decimation with preservenormal on the raw mesh → repair deleted 24% | keep fast_simplification, then repair |
| Global Taubin smoothing | grainy surface on decimated mesh; after the base cut it distorted the base edge (7 mm) | local `fix_spot.py`; never smooth after base trimming |
| Spike detection by vertex offset / dihedral angle | flags real narrow grooves | pick the defect visually + `render.py pick` |
| `abs(winding)` to rescue inside-out shells | marked empty space as solid above the ears | per-shell `fix_normals(multibody=True)` |
| Keeping only the largest connected part | dropped the tail and eyes (separate shells) | winding number merges overlapping shells |

## Generation
- Painted details (colour-only eyes, white chest patches) → no geometry or flaps/ridges. Prompt for
  sculpted relief in one colour (see organic.md). This mattered more than any post-processing.
- TRELLIS 512 is draft quality; 1024 cascade is much cleaner (~20 min).
- The `--no-texture` OBJ is Z-up; the textured GLB is Y-up.
- trellis-mac's setup pulls the newest torch; torch ≥2.12 needs C++20 and the Metal deps hardcode
  C++17 → builds fail while setup still says "complete". Pinned: `tools/trellis-mac/constraints.txt`.

## Tools and environment
- Bambu Studio CLI rejects profile fragments: flatten `inherits`, set `*_settings_id` to the preset
  names and `from: system` (slice_check.py does this).
- Workbench renders: flat raised details vanish without shadows (fixed); framing must use the
  projected outline (fixed); face-centre crops show shards (fixed: solid intersection).
- `open -a BambuStudio model.stl` added the model into the user's open project. Don't.
- Estimating a defect's 3D position from a screenshot was wrong twice; use `render.py pick`.
- First example hook was modelled upside down (lip pointing down) — check function, not only geometry.

## Found by the first skill test round (2026-11-01)
| Problem | Fix now in the skill |
|---|---|
| solidify's winding fallback returned a torso fragment (head open, legs gone) on the Batman and still said "watertight, success" | every strategy is size-checked against the input; visibility-orientation strategy (`wn-vis`); exit 2 instead of a fragment |
| slice_check said `support_used: true` whenever supports were merely enabled | supports are read from the G-code (`supports_generated`, where, grams, `support_on_bed`) |
| `--infill 100` failed (grid pattern) | zig-zag at 100% |
| Flat text on a round base: uneven relief or refused | `text --wrap`, `--letter-height` |
| Flat-roof 10 mm magnet pocket filled with support | cone roof by default |
| plinth "chamfer" made a cone-shaped side; base sized from contact points only | real edge chamfers; covers the lower body |
| Lithophane: unsupported ledge under the top frame → 106 mm support tree | 45° growth limit when upright |
| Text-only generation lost the specific costume (generic Batman) | search existing models first; `organic.py claify` from the user's photo |
| A background test agent sat ~2 h on a permission prompt (an `rm`) | never use `rm` (overwrite or mv to `_trash/`) |
| `--at -2,-27,108` broke argparse | coordinates as separate numbers |
