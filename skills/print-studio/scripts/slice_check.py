"""Slice a model with the Bambu Studio CLI and report print time, filament and support use.

Doubles as a printability check: if the slicer can't slice it, it's not ready.
Profiles are flattened from Bambu Studio's system profiles (the CLI rejects the
inheriting fragments), using preset names from the print-studio config (ps_config.py).

Usage:
  python slice_check.py MODEL.(stl|3mf|obj) OUT_DIR [--supports auto|off|tree] [--infill 15]
                        [--layer 0.2] [--walls 2] [--brim 5] [--color "#FFFFFF"] [--set KEY=VALUE ...]
--set overrides any process setting, e.g. --set bridge_no_support=1 ("Don't support bridges"); the
override is saved in the sliced project, so it applies when the 3MF is opened in Bambu Studio.
Prints a JSON summary and writes OUT_DIR/slice_summary.json. Supports are reported from the
G-code itself (where they are and how much), not from the "supports enabled" setting.
Exit codes: 0 ok, 3 slicer failed, 4 no result.
"""
import argparse
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import ps_config

CFG = ps_config.load()
BIN = Path(CFG["bambu_studio_bin"])
PROFILES = Path(CFG["bambu_profiles_dir"])  # Bambu Studio's own BBL system presets (read, never copied)


def find_profile(kind, name):
    for f in (PROFILES / kind).glob("*.json"):
        try:
            if json.loads(f.read_text()).get("name") == name:
                return f
        except Exception:
            continue
    raise SystemExit(f"profile not found: {kind}/{name}")


def flatten(kind, name):
    """Merge a profile with its whole `inherits` chain (parent first, child wins)."""
    d = json.loads(find_profile(kind, name).read_text())
    parent = d.get("inherits")
    merged = flatten(kind, parent) if parent else {}
    merged.update(d)
    merged.pop("inherits", None)
    return merged


def support_report(gcode):
    """Where the slicer actually put support material (from ; FEATURE: markers in the G-code)."""
    z = 0.0
    in_support = False
    zs, xs, ys, e_mm = [], [], [], 0.0
    for line in gcode.splitlines():
        if line.startswith("; FEATURE:"):
            in_support = "support" in line.lower()
            continue
        if line.startswith("; Z_HEIGHT:"):
            z = float(line.split(":")[1])
            continue
        if in_support and line.startswith("G1") and " E" in line:
            parts = dict((p[0], p[1:]) for p in line.split(";")[0].split()[1:] if p and p[0] in "XYZE")
            try:
                e = float(parts.get("E", 0))
            except ValueError:
                continue
            if e > 0 and ("X" in parts or "Y" in parts):
                e_mm += e
                zs.append(z)
                if "X" in parts:
                    xs.append(float(parts["X"]))
                if "Y" in parts:
                    ys.append(float(parts["Y"]))
    if not zs:
        return {"supports_generated": False}
    grams = e_mm * 3.14159 * 0.875 ** 2 * 1.24 / 1000  # 1.75 mm PLA (estimate)
    first = min(zs)
    return {"supports_generated": True, "support_g": round(grams, 2),
            "support_z_range_mm": [round(min(zs), 2), round(max(zs), 2)],
            "support_xy_bbox_bed_mm": [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)] if xs and ys else None,
            "support_layers": len(set(zs)),
            "support_on_bed": first <= 0.3,
            "support_note": ("some support stands on the bed: under overhangs beyond the base, or inside a "
                             "bottom cavity/pocket; render or re-slice to see which") if first <= 0.3 else
                            "all support stands on the model itself"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("out_dir")
    ap.add_argument("--supports", choices=["auto", "off", "tree"], default="auto")
    ap.add_argument("--infill", type=int, default=None, help="sparse infill percent")
    ap.add_argument("--layer", type=float, default=None, help="layer height mm")
    ap.add_argument("--walls", type=int, default=None)
    ap.add_argument("--brim", type=float, default=None, help="brim width mm (0 = none)")
    ap.add_argument("--color", default=None, help="filament colour hex for the project file, e.g. #FFFFFF")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a process setting (repeatable)")
    args = ap.parse_args()

    out = Path(args.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    machine = flatten("machine", CFG["machine_profile"])
    process = flatten("process", CFG["process_profile"])
    filament = flatten("filament", CFG["filament_profile"])
    for d, kind in ((machine, "machine"), (process, "process"), (filament, "filament")):
        # "system": the CLI then checks compatibility by these names (for "User" presets it
        # would look up an `inherits` parent instead, which flattening removed).
        d["from"], d["type"] = "system", kind
    # The GUI fills these ids with the preset names; the CLI's compatibility check needs them.
    machine["printer_settings_id"] = machine["name"]
    process["print_settings_id"] = process["name"]
    filament["filament_settings_id"] = [filament["name"]]
    if args.supports != "off":
        process["enable_support"] = "1"
        process["support_type"] = "tree(auto)" if args.supports in ("auto", "tree") else process.get("support_type")
    else:
        process["enable_support"] = "0"
    if args.infill is not None:
        process["sparse_infill_density"] = f"{args.infill}%"
        if args.infill >= 100:  # Bambu rejects the profile's 'grid' pattern at 100%
            process["sparse_infill_pattern"] = "zig-zag"
    if args.brim is not None:
        process["brim_type"] = "no_brim" if args.brim <= 0 else "outer_only"
        process["brim_width"] = str(args.brim)
    if args.color:
        filament["filament_colour"] = [args.color]
    if args.layer is not None:
        process["layer_height"] = str(args.layer)
    if args.walls is not None:
        process["wall_loops"] = str(args.walls)
    for kv in args.set:
        key, sep, val = kv.partition("=")
        if not sep or key not in process:
            sys.exit(f"--set {kv!r}: expected KEY=VALUE with a known process key")
        process[key] = val

    paths = {}
    for kind, d in (("machine", machine), ("process", process), ("filament", filament)):
        paths[kind] = out / f"_{kind}.json"
        paths[kind].write_text(json.dumps(d, indent=1))

    result_3mf = out / (Path(args.model).stem + "_sliced.3mf")
    cmd = [str(BIN), "--orient", "0", "--arrange", "1", "--ensure-on-bed",
           "--load-settings", f"{paths['machine']};{paths['process']}",
           "--load-filaments", str(paths["filament"]),
           "--slice", "0", "--export-3mf", result_3mf.name, "--outputdir", str(out),
           str(Path(args.model).resolve())]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    (out / "_slicer.log").write_text(proc.stdout + "\n" + proc.stderr)
    if proc.returncode != 0 or not result_3mf.exists():
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-15:]
        print(json.dumps({"ok": False, "returncode": proc.returncode, "log_tail": tail}, indent=1))
        sys.exit(3)

    summary = {"ok": True, "sliced_3mf": str(result_3mf), "slice_seconds": round(time.time() - t0, 1),
               "settings": {"supports": args.supports, "infill": process.get("sparse_infill_density"),
                            "layer_height": process.get("layer_height"), "walls": process.get("wall_loops"),
                            "overrides": args.set}}
    with zipfile.ZipFile(result_3mf) as z:
        names = z.namelist()
        info = next((n for n in names if n.endswith("slice_info.config")), None)
        if info:
            xml = z.read(info).decode()
            meta = dict(re.findall(r'key="([^"]+)"\s+value="([^"]*)"', xml))
            secs = float(meta.get("prediction", 0) or 0)
            summary.update({"print_time": f"{int(secs // 3600)}h {int(secs % 3600 // 60)}m",
                            "print_seconds": secs, "filament_g": float(meta.get("weight", 0) or 0),
                            "warnings": re.findall(r'<warning[^>]*msg="([^"]+)"', xml)})
            fil = re.search(r'<filament[^>]*used_m="([^"]+)"[^>]*used_g="([^"]+)"', xml)
            if fil:
                summary["filament_m"] = float(fil.group(1))
        gcodes = [n for n in names if n.endswith(".gcode")]
        summary["has_gcode"] = bool(gcodes)
        if gcodes:
            summary.update(support_report(z.read(gcodes[0]).decode(errors="ignore")))
    (out / "slice_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    sys.exit(0 if summary.get("has_gcode") else 4)


if __name__ == "__main__":
    main()
