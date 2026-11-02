# Inspecting models (the user will)

The user opens results in Bambu Studio and zooms in. Defects they found that a small overview hid:
voxel terraces, saw-toothed eye sockets, a notch between toes. So inspect at the zoom they will.

## Procedure
1. `render.py sheet MODEL sheet.png --ref REF` — 10 views (front/back/left/right/top/bottom, two 3/4
   views, upper & lower close-ups) with shadows and cavity shading. Look at every tile.
2. `render.py closeup` on every region with detail or function: eyes/face/mouth, ears, fingers/toes,
   hair/fur/tufts, text, holes and mating features, thin parts, joins between parts, the base, cut
   faces. `--at X,Y,Z --radius R` (mm) or `--box` (bbox fractions).
3. For AI meshes: `render.py sheet FINAL out.png --compare RAW.obj` — anything in yours but not in
   the raw is your processing's fault (fix the method); anything in both is the generator's (fix the
   spot or regenerate).
4. Compare symmetric twins (left/right paw, both eyes, both ears): a difference is usually a defect.

## What to look for
- Surface: terraces/contour rings, grain, saw-tooth or zig-zag edges along grooves, dimples, spikes,
  folds, flat patches where holes were filled, see-through spots.
- Shape: missing parts (tail/ears dropped by "keep largest part"), extra floating pieces, collars or
  webbing filling gaps that should be open (neck, between fingers, inside ears), merged details.
- Function: does the object do its job the right way round (a hook's lip points up; text reads
  left-to-right from the front; a holder's opening faces up)? Do mating features line up?
- Printing: big overhangs under chins/arms, thin spikes, small base, top-heavy shapes.

## Fixing a spot
1. Close-up tile → note the pixel of the defect (tiles are 600 px) → `render.py pick OUT.png front u,v`
   gives the 3D point. Pick 2-3 pixels around it to be sure. Estimating coordinates from the picture
   by eye was wrong twice; always pick.
2. `fix_spot.py IN OUT --at X,Y,Z --radius 0.5..0.7` (start small; 1.2 mm erased a real groove).
3. Re-render the same close-up before/after; check the symmetric twin still matches.

## Reading renders correctly
- Crops of watertight models are exact solid intersections; crops of leaky meshes keep whole
  triangles and can show shard-like slivers at the crop edge — not real.
- The raw TRELLIS OBJ renders speckled/see-through (inconsistent winding): expected, not a defect.
- If a detail looks missing, confirm with numbers before declaring a defect (e.g. compare volumes /
  areas with the CAD) — once flat letters were invisible only because of shading.
- Renders have soft cast shadows: a dark patch under an overhang (inside a window, under a chin,
  on legs under a cape) is usually a shadow, not geometry or paint. Check from another view.
- The `below` close-up tile is the way to inspect pockets, holes and bases from underneath.
- check_mesh `thin_wall_spots` gives coordinates of thin regions: close-up each with `--at X Y Z`.
- Faceted 96-segment cylinders show faint vertical bands in renders: cosmetic, ~0.02 mm.
