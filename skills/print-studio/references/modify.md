# Modify route: change an existing mesh

Input can be the user's STL/3MF/OBJ, a MakerWorld/Printables download, or a model from another route.
1. `check_mesh.py IN` first. Not watertight / many bodies → `solidify.py` (use `--up y` for most
   GLB/OBJ from the web; STL/3MF are usually Z-up already). Keep the original untouched.
2. Chain `meshops.py` commands, one output file per step (`a_*.stl`, `b_*.stl`, ...) so any step can be
   redone. Every command prints size/volume and warns about multiple pieces.

| Want | Command |
|---|---|
| Resize | `scale IN OUT --height 120` / `--factor 1.5` / `--fit 250 250 250` |
| Rotate / mirror / move | `transform IN OUT --rotate 0 90 0 --to-bed` / `--mirror x` |
| Too big for the plate, or needs a flat face for printing | `cut IN PREFIX --at Z --pins 2` |
| Lighter / cheaper large model | `hollow IN OUT --wall 2 --drain 5` |
| Combine / subtract meshes (place them first with `transform`) | `boolean IN OUT --add A.stl --subtract B.stl` |
| Name / label / date | `text IN OUT --text "..." --side front --letter-height 6 --depth 1.0 [--wrap] [--engrave]` |
| Magnets, coins, nuts, weights | `pocket IN OUT --d 10.3 --depth 3.2 [--shape hex] [--side bottom]` (cone roof by default) |
| Stability / display base | `plinth IN OUT --shape round --height 10` (covers the lower body; prints centre/radius) |

## Cutting well
- Choose the height from the cross-section, not by eye: a plane that also clips a tail tip or ear
  makes extra loose pieces (cut warns: "N separate pieces"). Move it until each half is one body.
- Cut where the seam is least visible and the section is widest (strong pin joint); both halves
  should print without supports: the upper half is flipped cut-face-down automatically.
- Pins: separate printed pins (default 5 mm, 6 mm deep each side, +0.25 mm hole clearance). If the
  section is too small, the script places fewer pins and says so; then use smaller `--pin-d`.

## Text well
- Give the real letter height: `--letter-height 6` (≥ 6 mm on vertical faces); `--size` is the font
  size and letters come out ~0.72 × that. Raised depth 1.0 mm (0.8 mm equals the minimum wall and
  shows up as "thin" in check_mesh), engraved 0.6-1.0 mm.
- **Round surfaces (round plinths, cylinders, mugs): always `--wrap`.** It bends the text around
  the vertical axis so every letter has the same relief. Flat text on a curve stands out more at
  its ends (seen: 0.8 mm in the middle, 2.4 mm at the ends) or gets refused.
- Text on the side of a base needs a base taller than the letters: height ≥ letter height + 3 mm
  (the default plinth is 4 mm: use `--height 10` for 6-7 mm letters). plinth prints the
  `--height-at` to use.
- Fonts: `--font "Arial Black"` (bold reads better). Unknown fonts are refused (they'd silently
  fall back to the default otherwise).

## Magnet pockets
Common sizes (add +0.3 mm diameter, +0.2 mm depth): 6×2, 8×3, 10×2, 10×3 mm. Bottom pockets get a 45°
cone roof by default: a flat 10 mm roof is a bridge and Bambu fills the pocket with support. The
pocket is centred on the bottom footprint unless `--at X Y`. Glue magnets in (check polarity), or
pause the print above the pocket (Bambu Studio: layer slider → add pause). One magnet holds a small
figure on a horizontal steel surface, not on a vertical fridge door.

## Coordinates
Space-separated (`--at -12 3.5 40`, negatives fine). `prep.py` re-centres models and prints the shift;
coordinates measured before prep must be shifted by it.
