# Organic route: idea or photo → printable figure

Local and free: Z-Image-Turbo (text → picture), Qwen-Image-Edit-2511 (photo → clay version),
TRELLIS.2 (picture → 3D), all on Apple Silicon (timings below are from an M5 Max).

## 0. Is there already a model? (known characters, products, famous designs)
For anything with a name (a film/game character, a specific suit, a vehicle, a mascot), search
before generating: a fan-made printable model is usually far better than any single-image AI result.
WebSearch e.g. `"<subject>" STL figure OR statue` restricted to printables.com, makerworld.com,
thingiverse.com, thangs.com. Show the user the 2-4 best free options (link, what it is, licence:
most are personal-use only). If one fits → **modify route** (rescale, plinth, name plate, split).
Generate only if nothing fits or the user wants their own version.

## 1. The reference picture decides most of the quality
TRELLIS builds geometry from what it *sees*. Detail that is only colour, sheen or darkness becomes
nothing (painted eyes → faint outlines) or garbage (colour boundaries → ridges and flaps). For
single-colour prints the reference must look like an **unpainted grey clay sculpture**.

**A) The user has a photo of a specific design** (a costume, a figure, their pet) →
`$PY $S/organic.py claify PHOTO work/<job>/clay --seeds 7 21 --gray` (~5-10 min, background + tail).
It keeps *that* design and pose and re-renders it as a sculpture, which text prompts can't: a
text-only "Batman" came out as a generic comics suit instead of the photo's. Use `--prompt-extra`
for fixes ("the cape hem rests on the ground", "the boots are fully visible"). A dark or cropped
photo is fine as input to claify; it is not fine as direct TRELLIS input.

**B) Only an idea** → text prompt:
`$PY $S/organic.py image "PROMPT" work/<job>/refs --seeds 7 21 42 --gray` (~2-3 min). Template:
```
a <subject> figurine <pose>, full body, unpainted solid light grey matte clay sculpture, one uniform
color, no painted markings, all details sculpted in relief: <eyes sculpted as smooth raised domes with
a clear rim / fur tufts as soft shallow grooves / ...>, thick sturdy <neck/limbs/connections>,
<tail/limbs/cape> touching the body or the ground, chunky rounded proportions, single object centered,
pure white background, soft studio lighting, entire figure visible, no base, no shadow
```
Online photos of the subject can be used as extra input to claify (e.g. a clear back view) or to
describe details the main photo hides (boots, back of a cape).

**Picking the reference** (look at every candidate): printability beats looks. Prefer thick
connections, limbs/capes touching body or ground, no thin free-standing spikes (whiskers, blades,
antennae), the whole figure in frame, a pose that sits flat. The image models ignore some
instructions (Z-Image ignored "cape hem on the ground" in 8/8 images and added skin tones despite
"one colour": `--gray` fixes the colour; for pose problems try more seeds or claify with
`--prompt-extra`). Name of outputs: `ref_seed_<N>.png` / `clay_seed_<N>.png`.

**The back is a guess.** TRELLIS sees one picture and invents everything it hides, and it tends to
copy front details onto the back: a baby dragon's sculpted belly plates came out mirrored onto its
back, next to a forked tail. Keep strong front-only details out of the prompt (belly plates, chest
emblems, buttons), prefer a three-quarter view that shows some of the side, and look at the back,
left and right views of the first sheet before solidifying. A tail the reference hides behind the
body often comes out forked (two tails), even from a three-quarter view: pick a seed that shows
the whole tail.

## 2. Picture → mesh
`$PY $S/organic.py to3d work/<job>/refs/ref_seed_7.png work/<job>/mesh --quality 1024`
~18-20 min (1024 cascade) — background job, ETA + tail. Output `<name>_1024.obj`, **Z-up**, 7-9M
faces. The front can come out facing any direction: check the first sheet and rotate so it faces
-Y (`meshops.py transform --rotate 0 0 90`). Look at the back views too (see "The back is a guess" above):
a bad back means a new reference, not a repair. 512 quality (~5 min) is for quick drafts only.

## 3. Mesh → watertight solid
`$PY $S/solidify.py mesh/<name>_1024.obj work/<job>/solid.stl --up z --height H`
It tries `direct` (keeps the original surface), then `wn-vis` (re-orients faces by visibility, for
badly broken meshes like the Batman), then `wn`. Each result must keep the input's size or it is
rejected. **Exit 2 = no method produced a complete figure: don't continue** — regenerate (other seed,
cleaner reference) instead of patching half a model. If the JSON says a `wn*` method was used,
inspect narrow grooves (eye sockets, toe gaps, mouth, armour seams): they can be saw-toothed.

Then `prep.py ... --height H --base-cut 0.8` (0.6-1.0 mm; more if the figure rocks). The final
height equals H (the cut is compensated).

## 4. Inspect and fix
- `render.py sheet FINAL sheet.png --ref REFERENCE.png` and `--compare RAW.obj`.
- Close-ups of face/eyes, ears, hands/paws/toes, hair/fur/tufts, cape edges, weapon/props, joins, base.
- Defect also in the raw mesh = generator's → `render.py pick` its pixel → `fix_spot.py --at X Y Z`.
  Radius ≈ half the defect's size: 0.5-0.7 mm for notches, 0.8-1.0 mm for rough patches ~3 mm
  across. Re-render the same close-up; compare with the symmetric twin so real detail survived.
- Defect only in yours → your processing: fix the method, not the spot.

## 5. Printing notes to pass on
- Size: big enough that thin parts stay ≥ 0.8 mm (capes, blades, ears): the 115 mm Batman's cape
  was ~0.8-1 mm; at 80 mm it would have been unprintable. check_mesh's `thin_wall_spots` tell you.
- Overhangs: tree supports (auto). Heads/chins and floating cape hems take most of it.
- Two small feet: a plinth (`meshops.py plinth`) or a brim (`slice_check --brim 5`).
- Figure > ~60 mm with thin neck/ankles: consider `meshops.py cut` + pins.
- Hollowing only pays off above ~100 mm (FDM infill already keeps the inside sparse).
- Fan models / characters: personal use only; RMBG-2.0 (used by TRELLIS) is non-commercial.
