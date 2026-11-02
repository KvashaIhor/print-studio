# 2D → 3D route: pictures, logos and text into printable objects

All via `$PY $S/relief.py <mode> ...` (outputs are watertight; verify as usual).

| Want | Mode | Good defaults |
|---|---|---|
| Photo that appears when back-lit | `lithophane IMG OUT --width 100 [--crop X0 Y0 X1 Y1]` | min 0.8, max 3.2 mm, border 3 mm; upright on a foot that scales with height; writes `OUT_preview.png` (back-lit look) |
| Raised picture / logo plaque | `relief IMG OUT --width 80 --base 2 --height 3` | `--threshold 0.5` for crisp two-level logos, `--invert` if dark should be high |
| Logo / icon from SVG | `svg FILE.svg OUT --height 3 --width 60 [--base 1.5]` | closed filled paths; strokes must be converted to paths |
| Name tag, keychain, sign | `text "TEXT" OUT --size 10 --height 2 --base 2 [--hole 4]` | ≥ 6 mm letters, hole ≥ 4 mm with 2 mm rim |
| Cookie cutter | `cookie FILE.svg OUT --width 70 --height 12` | wall 0.8 mm cutting edge, 3 mm flange |

## Print settings to tell the user
- **Lithophane**: print standing up (as exported), **supports OFF**, 0.12 mm layers, 100% infill
  (or 4 walls), white PLA: `slice_check.py OUT dir --supports off --layer 0.12 --infill 100 --color "#FFFFFF"`.
  The relief side faces -Y ("front"): that side faces the room; from the flat side the picture is
  mirrored. The script already limits thickness growth to 45° when upright (no supports needed,
  and it chamfers the ledge under the top frame). Look at `OUT_preview.png`, not the geometry render,
  to judge the picture. PLA can soften in a sunny window: PETG for windowsills in summer.
  check_mesh may flag "thin" walls at the 0.8 mm minimum thickness: expected for lithophanes.
  Crop to the subject (`--crop`, fractions of the image); `--gamma` >1 darkens midtones.
- **Reliefs / logos**: flat on the bed; a colour change at the relief height (pause, or the AMS if the
  user wants it) makes logos pop: mention it, don't assume it (single-colour default).
- **Keychains**: 3+ walls for the ring area; PETG if it lives on keys.
- **Cookie cutters**: PLA is fine for occasional use; food-safety caveat (layer lines trap dough;
  not dishwasher safe).

## Inputs
- Images: high contrast works best; crop to the subject. For lithophanes faces/pets look great; busy
  backgrounds turn into noise: offer to remove the background (TRELLIS's RMBG or a plain crop).
- SVGs: if the user only has a PNG logo, use `relief --threshold` instead of tracing.
- Text fonts: build123d's default font; use `--font "Arial Black"` etc. for bolder text (system fonts).
