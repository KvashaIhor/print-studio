"""Load the print-studio configuration (printer, slicer profiles, tool paths).

Search order, first file found wins:
  1. $PRINT_STUDIO_CONFIG
  2. ~/.config/print-studio/printer.json   (survives plugin updates: recommended)
  3. <skill>/config/printer.json
Keys missing from it fall back to <skill>/config/printer.example.json, so a config written for an
older version keeps working. Paths may use ~. An empty "python" means the interpreter running the
script.
"""
import json
import os
import platform
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
EXAMPLE = SKILL / "config" / "printer.example.json"
CANDIDATES = [os.environ.get("PRINT_STUDIO_CONFIG"),
              Path.home() / ".config" / "print-studio" / "printer.json",
              SKILL / "config" / "printer.json"]
PATH_KEYS = ("workspace", "python", "blender", "bambu_studio_app", "bambu_studio_bin", "bambu_profiles_dir",
             "trellis_dir")


def config_path():
    for c in CANDIDATES:
        if c and Path(c).expanduser().is_file():
            return Path(c).expanduser()
    return None


def _bambu_paths(cfg):
    """Bambu Studio executable and its BBL system-profile folder (macOS layout unless overridden)."""
    app = Path(cfg.get("bambu_studio_app") or "")
    if not cfg.get("bambu_studio_bin"):
        cfg["bambu_studio_bin"] = str(app / "Contents/MacOS/BambuStudio") if platform.system() == "Darwin" else str(app)
    if not cfg.get("bambu_profiles_dir"):
        base = app / "Contents/Resources" if platform.system() == "Darwin" else app.parent / "resources"
        cfg["bambu_profiles_dir"] = str(base / "profiles" / "BBL")


def load():
    cfg = json.loads(EXAMPLE.read_text())
    p = config_path()
    if p is None:
        raise SystemExit("print-studio: no config found. Copy\n  " + str(EXAMPLE) +
                         "\nto ~/.config/print-studio/printer.json and edit it (see SETUP.md).")
    cfg.update(json.loads(p.read_text()))
    cfg["_config_file"] = str(p)
    for k in PATH_KEYS:
        if cfg.get(k):
            cfg[k] = str(Path(cfg[k]).expanduser())
    if not cfg.get("python"):
        cfg["python"] = sys.executable
    _bambu_paths(cfg)
    return cfg


if __name__ == "__main__":
    print(json.dumps(load(), indent=1))
