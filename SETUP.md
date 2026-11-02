# Setup

About 15 minutes for the core routes (functional, modify, 2D → 3D). The optional organic route adds model downloads of 20–80 GB.

## 1. Python environment

Use Python 3.12. With [uv](https://docs.astral.sh/uv/):

```bash
uv venv --python 3.12 ~/print-studio/.venv
uv pip install --python ~/print-studio/.venv/bin/python -r requirements.txt
```

Or with plain venv and pip:

```bash
python3.12 -m venv ~/print-studio/.venv
~/print-studio/.venv/bin/pip install -r requirements.txt
```

## 2. Blender and Bambu Studio

- **Blender** (free) is used headless for the inspection renders. On macOS run `brew install --cask blender`, or download it from blender.org. Note the path to the executable:
  - macOS: `/Applications/Blender.app/Contents/MacOS/Blender`
  - Homebrew formula: `/opt/homebrew/bin/blender`
- **Bambu Studio** (free) is used through its command line for test slicing. Install it normally; the skill reads its built-in printer presets and never changes your Bambu Studio settings.

## 3. Config

```bash
mkdir -p ~/.config/print-studio
cp skills/print-studio/config/printer.example.json ~/.config/print-studio/printer.json
```

Edit `~/.config/print-studio/printer.json`:

| Key | Set to |
|---|---|
| `printer`, `nozzle_mm`, `build_volume_mm` | your printer |
| `machine_profile`, `process_profile`, `filament_profile` | Bambu Studio system preset names, exactly as shown in Bambu Studio |
| `python` | the venv from step 1, e.g. `~/print-studio/.venv/bin/python` |
| `workspace` | where jobs, deliverables and logs go, e.g. `~/print-studio` |
| `blender` | the Blender executable from step 2 |
| `bambu_studio_app` | `/Applications/BambuStudio.app` on macOS |
| `bambu_studio_bin`, `bambu_profiles_dir` | leave empty on macOS. On Linux/Windows, set both: the `bambu-studio` executable and the `resources/profiles/BBL` folder of the install |
| `trellis_dir` | leave empty unless you set up the organic route (step 5) |

Check it (run from the `skills/print-studio` folder):

```bash
~/print-studio/.venv/bin/python scripts/ps_config.py
```

It prints the merged config and which file it read. You can point to another file with `PRINT_STUDIO_CONFIG=/path/to/printer.json`.

## 4. Smoke test

From `skills/print-studio`, with `PY=~/print-studio/.venv/bin/python`. The first line creates the
sample inputs (a synthetic picture and figure; they are generated rather than shipped):

```bash
$PY evals/files/make_samples.py
$PY scripts/relief.py lithophane evals/files/sample_picture.png /tmp/ps_test/litho.stl --width 80
$PY scripts/check_mesh.py /tmp/ps_test/litho.stl
$PY scripts/render.py sheet /tmp/ps_test/litho.stl /tmp/ps_test/sheet.png
$PY scripts/slice_check.py /tmp/ps_test/litho.stl /tmp/ps_test/slice --supports off --layer 0.12 --infill 100
```

Look at `sheet.png`, and check the slice reports a print time and grams. Then ask Claude Code something like "make me a lithophane of this picture" and the skill takes over.

## 5. Optional: the organic route (Apple Silicon)

Tested on an M5 Max with 128 GB.

### Text-to-image and photo-to-clay (mflux)

```bash
uv pip install --python ~/print-studio/.venv/bin/python -r requirements-organic.txt
```

The models download from Hugging Face on first use:
- Z-Image-Turbo for text prompts.
- Qwen-Image-Edit-2511 for turning a photo into a clay-sculpture reference. It is about 58 GB, and its first run takes a while.

### Image-to-3D (TRELLIS.2, Apple Silicon port)

```bash
git clone https://github.com/shivampkumar/trellis-mac ~/print-studio/tools/trellis-mac
cd ~/print-studio/tools/trellis-mac
hf auth login        # a Hugging Face token; the next two models are gated
# request access (usually instant):
#   https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m
#   https://huggingface.co/briaai/RMBG-2.0
printf 'torch==2.11.0\ntorchaudio==2.11.0\n' > constraints.txt
UV_CONSTRAINT=constraints.txt bash setup.sh
```

The torch pin matters. torch 2.12 and newer need C++20, while the port's Metal extensions are built as C++17. Without the pin those builds fail, even though `setup.sh` still reports success. To check that the build worked, run `.venv/bin/python -c "import cumesh._C"` inside the folder.

Then set `"trellis_dir": "~/print-studio/tools/trellis-mac"` in your config. One 1024-quality generation takes about 20 minutes. The skill runs it in the background, with a log you can follow.

Licences: RMBG-2.0 is CC BY-NC 4.0 (non-commercial) and DINOv3 has Meta's custom licence. See the README.
