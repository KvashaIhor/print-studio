"""Organic route generators (all local and free): text or photo -> reference image -> 3D mesh.

  image "PROMPT" OUT_DIR [--seeds 7 21 42] [--size 1024] [--gray]
        Z-Image-Turbo via mflux (text only). ~1 min model load + ~30 s per image
        (4 seeds ~2.5 min). Writes OUT_DIR/ref_seed_<N>.png.
  claify PHOTO OUT_DIR [--seeds 7 21] [--prompt-extra "..."] [--gray]
        Qwen-Image-Edit-2511 via mflux: re-renders the user's photo/reference as an unpainted
        single-colour clay sculpture of the SAME design and pose (keeps the specific costume /
        character, unlike text-only generation). ~2-4 min model load + ~1-3 min per image.
        Writes OUT_DIR/clay_seed_<N>.png. Needs the ~58 GB model in the HF cache.
  to3d  IMAGE OUT_DIR [--quality 1024|512] [--seed 42]
        TRELLIS.2 (Apple-Silicon port) image -> mesh, no texture (single-colour prints).
        1024 (cascade): ~18-20 min on an M5 Max (about 4 min of it is a texture stage that runs even
        with --no-texture), clean detailed geometry, Z-up OBJ ~7-9M faces. The model's front can
        face any direction: check the sheet and rotate (meshops transform) so it faces -Y.
        512: ~5 min, coarser, more holes; use for quick drafts only.

All log every line with timestamps to <workspace>/logs/<kind>_<job>_<time>.log (unique per run)
and record the real exit code. They block until done: start them in the background and tell the user the ETA and
`tail -f` command.
"""
import argparse
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import ps_config  # noqa: E402

CFG = ps_config.load()
WS = Path(CFG["workspace"])
VENV_BIN = Path(CFG["python"]).parent        # mflux's CLIs are installed next to the python
TRELLIS = Path(CFG["trellis_dir"]) if CFG.get("trellis_dir") else None


def run_logged(job, cmd, cwd=None, env=None):
    log = WS / "logs" / f"{job}_{datetime.now():%Y%m%d-%H%M%S}.log"
    log.parent.mkdir(exist_ok=True)
    t0 = time.time()
    print(f"logging to {log}\n  watch: tail -f {log}", flush=True)
    with open(log, "a") as fh:
        fh.write(f"[{datetime.now():%F %T}] START {' '.join(map(str, cmd))}\n")
        fh.flush()
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in p.stdout:
            fh.write(f"[{datetime.now():%T} +{time.time() - t0:.0f}s] {line}")
            fh.flush()
        code = p.wait()
        fh.write(f"[{datetime.now():%F %T}] END exit={code} elapsed={time.time() - t0:.0f}s\n")
    if code != 0:
        print(f"FAILED (exit {code}); last lines:\n" + "".join(open(log).readlines()[-15:]))
        sys.exit(code)
    return log


def to_gray(paths):
    from PIL import Image
    for p in paths:
        Image.open(p).convert("L").convert("RGB").save(p)


def job_name(out):
    return f"{out.parent.name}_{out.name}"  # e.g. batman_refs: unique across jobs


def cmd_image(a):
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    cmd = [VENV_BIN / "mflux-generate-z-image-turbo", "--prompt", a.prompt, "--width", str(a.size),
           "--height", str(a.size), "--seed", *map(str, a.seeds), "--output", str(out / "ref.png")]
    run_logged(f"image_{job_name(out)}", cmd)
    made = sorted(out.glob("ref*.png"))  # mflux appends _seed_N when given several seeds
    if a.gray:  # the image model sometimes adds skin/colour tints despite "one colour"
        to_gray(made)
    print("images:", *map(str, made), sep="\n  ")


CLAY = ("Transform this into a studio photograph of an unpainted, single-colour light grey matte clay "
        "sculpture figurine of exactly the same character, same pose, same proportions and the same costume "
        "design. Every costume detail (armour plates, seams, belts, straps, emblems, folds) is sculpted in "
        "relief, not painted. No colours, no shine, no textures printed on. Full body visible including both "
        "feet, standing on the ground, plain pure white background, soft even studio lighting, no shadow.")


def cmd_claify(a):
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prompt = CLAY + (" " + a.prompt_extra if a.prompt_extra else "")
    cmd = [VENV_BIN / "mflux-generate-qwen-edit", "--model", "qwen-image-edit-2511",
           "--image-paths", str(Path(a.photo).resolve()), "--prompt", prompt,
           "--seed", *map(str, a.seeds), "--output", str(out / "clay.png")]
    if a.size:
        cmd += ["--width", str(a.size), "--height", str(a.size)]
    if a.quantize:
        cmd += ["--quantize", str(a.quantize)]
    run_logged(f"claify_{job_name(out)}", cmd)
    made = sorted(out.glob("clay*.png"))
    if a.gray:
        to_gray(made)
    print("clay references:", *map(str, made), sep="\n  ")


def cmd_to3d(a):
    if TRELLIS is None or not (TRELLIS / "generate.py").is_file():
        raise SystemExit(f"TRELLIS.2 not found (trellis_dir = {CFG.get('trellis_dir')!r} in {CFG['_config_file']}). "
                         "Install the Apple-Silicon port and set trellis_dir: see SETUP.md.")
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = out / f"{Path(a.image).stem}_{a.quality}"
    pipe = "1024_cascade" if a.quality == "1024" else "512"
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    cmd = [TRELLIS / ".venv/bin/python", "-u", "generate.py", str(Path(a.image).resolve()), "--pipeline-type", pipe,
           "--seed", str(a.seed), "--no-texture", "--output", str(stem.resolve())]
    run_logged(f"trellis_{job_name(out)}_{a.quality}", cmd, cwd=TRELLIS, env=env)
    print(f"mesh: {stem}.obj (Z-up; next: solidify.py {stem}.obj OUT.stl --up z --height MM)")


ap = argparse.ArgumentParser()
sub = ap.add_subparsers(dest="cmd", required=True)
i = sub.add_parser("image"); i.add_argument("prompt"); i.add_argument("out_dir")
i.add_argument("--seeds", type=int, nargs="+", default=[7, 21, 42]); i.add_argument("--size", type=int, default=1024)
i.add_argument("--gray", action="store_true", help="convert results to greyscale")
c = sub.add_parser("claify"); c.add_argument("photo"); c.add_argument("out_dir")
c.add_argument("--seeds", type=int, nargs="+", default=[7, 21]); c.add_argument("--prompt-extra")
c.add_argument("--size", type=int); c.add_argument("--quantize", type=int, choices=[4, 6, 8], default=8)
c.add_argument("--gray", action="store_true")
t = sub.add_parser("to3d"); t.add_argument("image"); t.add_argument("out_dir")
t.add_argument("--quality", choices=["1024", "512"], default="1024"); t.add_argument("--seed", type=int, default=42)
a = ap.parse_args()
{"image": cmd_image, "claify": cmd_claify, "to3d": cmd_to3d}[a.cmd](a)
