---
name: print-studio
description: Design, generate, modify and verify 3D-printable models for a Bambu Lab printer (P1S, X1, A1... set in the config), end to end, with local free tools. Covers organic shapes (figurines, animals, busts, characters, decor via local AI text/image-to-3D), functional parts (brackets, hooks, mounts, enclosures, adapters, spacers, hinges, clips via code CAD with exact dimensions), changing existing STL/3MF/OBJ files (scale, cut into parts with pins, hollow, add text, magnet/nut pockets, plinths, booleans), and 2D-to-3D (lithophanes, image reliefs, logos/SVG, signs, keychains, cookie cutters), plus any hybrid of these. Every model is checked (watertight, walls, overhangs, stability), inspected with close-up renders and test-sliced with Bambu Studio before delivery. Use this skill whenever the user wants to make, print, model, design, fix, resize, split or customise a physical object or an STL/3MF, mentions 3D printing, Bambu, MakerWorld/Printables files, a slicer, filament or supports, or describes a thing they want to hold in their hands, even if they never say "3D model".
---

# Print Studio

Turn "I want X" into a file that prints well on the configured printer, and prove it before handing
it over. Users inspect results closely (in Bambu Studio's viewport) and catch defects that a quick
glance misses, so verification is part of the job, not an extra.

## Environment

Everything machine-specific lives in one config file. Start every job by printing it:
`python3 <skill>/scripts/ps_config.py` (`<skill>` = this skill's base directory, shown when the skill
loads). It says which file it read: `$PRINT_STUDIO_CONFIG`, else `~/.config/print-studio/printer.json`,
else `<skill>/config/printer.json`. If there is none, help the user create it from
`config/printer.example.json` (see SETUP.md in the repository) before doing anything else.

| What | Where |
|---|---|
| Python with the libraries (trimesh, manifold3d, build123d, libigl, pymeshfix, scikit-image; mflux for organic) | `PY` = config `python` |
| Skill scripts | `S=<skill>/scripts` |
| Printer, nozzle, build volume, clearances, slicer presets, preferences | the config (read it at the start) |
| Workspace: jobs in `work/<job>/`, deliverables in `models/<name>/`, logs in `logs/` | config `workspace` |
| Blender (headless renders), Bambu Studio (CLI slicing) | config `blender`, `bambu_studio_app` |
| TRELLIS.2 image-to-3D (organic route only; Apple Silicon) | config `trellis_dir` (empty = organic route unavailable: say so, offer other routes) |

Ground rules:
- **Free, local tools only.** Don't propose paid APIs (Meshy, Tripo, Rodin, fal) unless asked.
- **Single colour by default** (config `default_colors`), even with an AMS. Design details as shape, not paint.
- **Long jobs (>30 s): log to `logs/<job>.log`, tell the user the ETA and the `tail -f` command before
  starting, run in the background**, report the real exit code. TRELLIS (~20 min), image generation
  (~1 min), big solidify/hollow runs all count.
- **Don't run `open -a BambuStudio file`**: the user often has their own project open and the model
  gets added into it. Give the path; they drag it in or use right-click → Reload from disk.
- **Don't delete files with `rm`**: delete commands commonly trigger permission prompts, and a
  background run then stalls for hours while nobody is watching. Overwrite outputs, or `mv` old
  files into `work/<job>/_trash/`.
- **Coordinate convention**: Z up, the side a person looks at faces **-Y** ("front" in every
  render and in Bambu Studio's default view). Rotate generated/downloaded models to match.

## Workflow

### 1. Understand and route
Pick the route(s) from what the user wants; hybrids chain routes (e.g. organic figure + plinth + text
+ magnet pocket = organic → modify).

| Signals | Route | Read |
|---|---|---|
| Living things, characters, faces, sculptural/decorative, "from this photo/picture" | Organic (AI) — but for any **known** character/object first search for an existing printable model (organic.md step 0) | `references/organic.md` |
| Measurements, fits, screws, "holder/mount/bracket/box/adapter/replacement part" | Functional (code CAD) | `references/functional.md` |
| User has an STL/3MF/OBJ (downloaded or own), "resize/split/hollow/add…" | Modify | `references/modify.md` |
| Photo → lithophane, logo/SVG, text, sign, keychain, cookie cutter, relief | 2D → 3D | `references/flat2d.md` |

Always skim `references/printability.md` (FDM rules for this printer) and `references/lessons.md`
(things that already went wrong once: don't repeat them).

### 2. Pin down constraints
Use the config (printer, nozzle, build volume, clearances, min wall). Ask the
user only for what you can't sensibly default and that changes the result: the size of the object,
dimensions of things it must fit (measure twice: ask for calipers numbers when fit matters), how it
mounts. State the defaults you chose instead of asking about them.

### 3. Build
Follow the route reference. Keep every intermediate in `work/<job>/` so steps can be re-run.

### 4. Make it print-ready
- Meshes from AI/scans/downloads: `$PY $S/solidify.py IN OUT.stl --up z|y --height MM`
- Then: `$PY $S/prep.py OUT.stl work/<job>/print --base-cut 0.8` (organic) / `--base-cut 0` (flat-bottomed parts)
- CAD parts: export from build123d already watertight; run prep only to centre/scale.

### 5. Verify (all three gates, every time)
1. **Mesh check**: `$PY $S/check_mesh.py MODEL` → READY / OK with warnings / BLOCKED. Fix blockers.
   Warnings need a decision you tell the user about (supports, reorientation, plinth). It lists
   `thin_wall_spots` (coordinates): look at them with `render.py closeup --at X Y Z`.
2. **Look at it**, properly. `$PY $S/render.py sheet MODEL work/<job>/sheet.png [--ref IMAGE]` gives 10
   views incl. top/bottom; then `render.py closeup` on every detailed region: faces, eyes, fingers/toes,
   text, mating features, thin parts, joins, the base (the `below` tile shows undersides/pockets).
   For processed AI meshes add `--compare RAW.obj` to tell your artifacts from the generator's.
   See `references/inspection.md` for what to look for and how to fix spots (`pick` → `fix_spot.py`).
3. **Slice it**: `$PY $S/slice_check.py MODEL work/<job>/slice [route settings below]` → print time,
   grams, and whether/where supports are *actually generated* (from the G-code) incl. support on the
   bed (`support_on_bed`). Writes `slice_summary.json` and a ready-to-print `*_sliced.3mf`.
   A model that doesn't slice isn't done.

   | Route | Slice with |
   |---|---|
   | Organic figures | `--supports auto` (tree); `--layer 0.12` for detailed figures under ~100 mm |
   | Functional parts | `--supports off` if designed support-free, `--walls 3` (4 for hooks/brackets under load), `--infill 25` |
   | Lithophanes | `--supports off --layer 0.12 --infill 100 --color "#FFFFFF"` |
   | Reliefs, signs, keychains | `--supports off`, `--walls 3` |

### 6. Deliver
Copy final files to `models/<name>/`: `<name>.stl`, `<name>.3mf` (plain model), `<name>_sliced.3mf`
(the slice_check project: open it in Bambu Studio and print, settings included), STEP for CAD parts,
and the reference/inspection sheet. Tell the user, briefly:
- path, size (mm), print time, filament (g), supports yes/no + type, suggested settings that differ
  from Bambu defaults (layer height, infill, walls, orientation, brim), how many parts/pins;
- anything you're not sure about, plainly (e.g. "the nose tip is 0.7 mm: it may print soft").
If they report a defect: find it with closeup + pick, fix at the root (route/method) when it's
systematic, locally (`fix_spot.py`) when it's a one-off, re-verify, deliver to the same path.

## How long things take (for ETAs)
render sheet/closeup 2-5 s · check_mesh 5-20 s · slice_check 5-60 s · prep 5-15 s · meshops 2-30 s
(hollow up to ~1 min) · solidify 0.5-8 min · organic image ~2-3 min for 3-4 seeds · claify ~5-10 min
· TRELLIS 1024 ~18-20 min · lithophane/relief 2-10 s. Anything over ~30 s: log + background + tail.

## Script cheat-sheet
```
ps_config.py                                      print the config and which file it came from
check_mesh.py MODEL                               print-readiness report (exit 0 ready / 1 warnings / 2 blocked)
render.py sheet MODEL OUT.png [--ref IMG] [--compare MODEL2]
render.py closeup MODEL OUT.png (--box x0 x1 y0 y1 z0 z1 | --at X Y Z --radius R)
render.py pick OUT.png front|side|above|below u,v  tile pixel -> 3D point (mm)
fix_spot.py IN OUT --at X Y Z [--radius 0.7 --fade 1.3]
slice_check.py MODEL OUT_DIR [--supports auto|off] [--infill 15] [--layer 0.2] [--walls 2] [--brim 5] [--color HEX]
solidify.py IN OUT.stl --up z|y --height MM       AI/scan mesh -> one watertight solid (fails loudly)
prep.py IN OUT_DIR [--up y] [--height MM|--scale F] [--base-cut MM]
organic.py image "PROMPT" OUT_DIR [--seeds ...]   local text-to-image (Z-Image-Turbo)
organic.py claify PHOTO OUT_DIR [--seeds ...]     user photo -> clay-sculpture version, same design (Qwen-Image-Edit)
organic.py to3d IMAGE OUT_DIR [--quality 1024]    local image-to-3D (TRELLIS.2), ~20 min
meshops.py scale|transform|cut|hollow|boolean|text|pocket|plinth ...
relief.py lithophane|relief|svg|text|cookie ...
assets/cad_template.py                            build123d starting point for functional parts
                                                  (copy to the job, run: PYTHONPATH=$S $PY part.py OUT_DIR)
```
Each script has `--help` with details. Coordinates are space-separated numbers (negatives fine).
