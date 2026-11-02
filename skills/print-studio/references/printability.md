# Printability rules for this printer (P1S, 0.4 mm nozzle, PLA default)

Numbers live in `config/printer.json`; this explains them.

- **Build volume** 256 × 256 × 256 mm. Bigger → cut into parts with pins (`meshops.py cut`).
- **Minimum wall** 0.8 mm (2 perimeters). Below ~0.6 mm features vanish or print as mush. Fine detail
  < 0.3 mm (e.g. AI-mesh micro-steps of 0.08 mm) is below what the nozzle reproduces: ignore it,
  don't "fix" it.
- **Overhangs** > 45° from vertical need support. Tree supports (auto) suit organic shapes and
  peel off cleanly; for functional parts prefer reorienting or chamfering so none are needed.
- **Bridges** up to ~10 mm print clean; longer ones sag.
- **Bed contact**: a flat base. Organic models: trim 0.6-1.0 mm (`--base-cut`). Small contact or
  tall/narrow parts: brim, or a plinth. check_mesh reports contact area and tip-over stability.
- **Holes** print ~0.2 mm undersize; horizontal holes > 6 mm sag at the top (teardrop shape).
- **Elephant's foot**: first layers spread ~0.2 mm; chamfer bottom edges of mating parts.
- **Strength**: weakest between layers; orient so loads run along layers.
- **Tolerances** (per side): press 0.1, snug 0.2, free 0.3, moving 0.4 mm.
- **Layer height**: 0.2 mm default; 0.12 mm for figurines with fine detail or lithophanes;
  0.28 mm for big plain parts.
- **Infill**: 15% default; 25-40% for functional loaded parts; walls matter more than infill for
  strength (3-4 walls for brackets/hooks).
- **Materials**: PLA (default, easy, not for heat/outdoor), PETG (tougher, outdoor, slight flex),
  TPU (flexible, needs care). Ask before choosing anything other than PLA.
