# Blender Synthetic Light Curves

Initial implementation targets Blender 4.5 LTS and uses the Blender 4.5 Python API. The installed and tested executable is Blender 4.5.15 LTS. Blender API calls are smoke-tested in that runtime; use the versioned [Blender 4.5 API documentation](https://docs.blender.org/api/4.5/) when adding Blender integration.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

## Current Tools

Audit all `.blend` assets and save their scene/object/material/image data and evaluated world-space mesh bounds:

```bash
BLENDER_BIN=/home/vkudak/software/blender-4.5.15-linux-x64/blender \
  .venv/bin/python scripts/audit_models.py
```

The audit writes `reports/model_inventory.json`. Bounds are in Blender scene units; `unit_system = METRIC` alone does not establish that each model has the correct real-world physical scale. `Topex_g.blend` and `Topex_g3.blend` currently contain mesh objects with no vertices. `Topex_g5_spb3.blend` contains one empty mesh object alongside its usable geometry.

Run the unit tests:

```bash
.venv/bin/python -m pytest -q
```

## Generate Light Curves

Both generator scripts read an INI file. Run them from the repository root; relative model and output paths in the INI are resolved from that root. `--config` is optional because each script has a default: `config/curve.ini` for one curve and `config/dataset.ini` for a batch.

### Single Curve

Edit `config/curve.ini` to choose the Blender executable, model, output CSV, and scenario settings. Then run:

```bash
.venv/bin/python scripts/generate_curve.py --config config/curve.ini
```

The single-curve config selects one model via `[paths] model`. The script writes the CSV named by `[paths] output` plus matching `.json` metadata and `.svg` diagnostic plot. To override common values without editing the INI:

```bash
.venv/bin/python scripts/generate_curve.py \
  --config config/curve.ini \
  --model models/Lotos_model.blend \
  --output reports/lotos_test.csv \
  --seed 123 --device cpu
```

Supported single-curve overrides are `--model`, `--output`, `--seed`, and `--device`.

To save the Blender-side Python script used for a curve, set `[render] script_output` in `config/curve.ini`, for example `script_output = reports/generated_curve.py`. The saved file contains the renderer code that prepares and updates the scene, with that run's arguments embedded, and is also the script Blender executes. Open it in Blender's text editor to inspect or run the same configuration. Leave it blank to use the normal renderer script directly.

The render scene uses `[render] scene_meters_per_unit` to define the physical scale (default `1`, or 1 Blender unit = 1 m). Mesh geometry is uniformly scaled so its longest bounding-box dimension equals `[render] satellite_size_m` (default 4 m), which gives the `Topex_good.blend` model a scale factor close to `0.01`. The satellite stays near the local origin for rendering precision; orbit, Earth, observer, and Sun coordinates are kept physically scaled relative to the satellite. Every output sample must be above the observer elevation mask. `[sun] max_eclipse_fraction` defaults to `0.15`: curves are retained with up to 15% eclipsed samples, which have zero flux; the chosen Sun direction is rejected if the eclipse fraction is higher. The JSON metadata records the actual retained pass duration and eclipse fraction. The camera frames the satellite close-up; Cycles denoising and the AgX view transform are enabled. `[sun] energy` is irradiance in W/m^2 and defaults to 1361, approximately the solar irradiance at 1 AU. `[render] exposure` defaults to -8.8 EV to keep the 4 m model's rendered highlights within a useful display range; adjust it for different models/materials. When the saved script is run from Blender's Text Editor, it also adds a smooth Timeline animation of the pass; the camera tracks the satellite center but does not rotate with the body. The source model and its mesh/material data are retained rather than clearing the scene.

### Dataset

Edit `config/dataset.ini`. Set `[paths] models_dir`, optional comma-separated `[paths] models`, `[paths] skip_models`, `[paths] output_dir`, and `[dataset] curves_per_model`. If `models` is blank, every `.blend` in `models_dir` is used except names listed in `skip_models`. If it is non-empty, it selects those models instead. Empty-geometry models cannot render and should be excluded.

Run the configured batch:

```bash
.venv/bin/python scripts/generate_dataset.py --config config/dataset.ini
```

For a small smoke run on one model, without changing the INI:

```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --model Lotos_model.blend \
  --curves-per-model 1 \
  --output-dir reports/dataset_smoke \
  --device cpu
```

Dataset options `--model` can be repeated to select multiple models; each selected name is resolved in `models_dir`. The other supported overrides are `--output-dir`, `--curves-per-model`, `--seed`, and `--device`. Total curves are the number of selected usable models multiplied by `curves_per_model`. Output names follow `{model}_seed{model-seed}_n{index:04d}.csv`; the seed advances by 10,000 for each model, and the zero-based index restarts at `0000` for each model. Each CSV has matching `.json` and `.svg` sidecars.

### INI Settings And Render Device

The INI files share `[blender]`, `[paths]`, `[run]`, `[observer]`, `[orbit]`, `[pass]`, `[attitude]`, `[sun]`, and `[render]` sections. The dataset config additionally has `[dataset]`. Edit these sections to configure the Blender executable and paths, seed/device, fixed or random observer and orbit, pass duration/cadence/elevation mask, attitude/spin and optional spin-axis precession, sun direction, and render resolution/samples. For a single curve, `[attitude]` sets fixed `precession_angle_deg` (cone half-angle), `precession_period_s`, and `precession_phase_deg`. For datasets, `[dataset]` sets `precession_angle_min_deg`/`precession_angle_max_deg` and `precession_period_min_s`/`precession_period_max_s`; each rotating curve also gets a random phase from 0 to 360 degrees. Precession is applied only to rotating curves. CLI values listed above override the corresponding INI values; other settings are controlled in the INI.

`[run] seed` sets the starting value for the pseudo-random generator that chooses scenario parameters configured for random sampling. These can include the observer or orbit, spin axis and phase, and sun direction. With the same seed, model, configuration, curve index, and code, those choices repeat; a different seed can produce different choices. The command-line `--seed` option overrides the value in the INI. For dataset runs, each model gets a seed offset of 10,000, and each curve uses its zero-based index as an additional offset, so curves do not all start from the same random sequence. The seed does not determine output filenames or guarantee identical rendered pixels across Blender versions, hardware, or render settings.

`[run] device` accepts `auto`, `cuda`, `optix`, or `cpu`. `auto` prefers an available GPU backend; use `cpu` as a compatibility fallback. If Blender detects a GPU but cannot load its render kernel, the render fails rather than silently moving a large batch to CPU. The checked-in configs request `cuda`, which has been confirmed working on the Quadro P520 with driver 580. For dataset-scale runs, verify the GPU with a small batch first; select `cpu` only if you need a compatibility fallback.

The renderer parents every mesh with geometry to a common root, so multi-part models can spin as one body. Sun direction is sampled per curve; samples in a cylindrical Earth shadow are stored with zero flux and are not rendered. Relative flux remains a linear RGB proxy with a simple inverse-square range correction, not a calibrated magnitude.

The current Python core includes WGS-84 ground observer coordinates, circular two-body orbit propagation for altitudes of 300-3000 km, seeded parameter samplers, and visible-pass selection. The pass sampler aligns orbital phase to closest approach, rejects candidates below a configurable elevation mask, and samples the satellite's moving position, velocity, range, azimuth, and elevation over the pass window. Earth rotation is intentionally ignored, so the observer and local horizon remain fixed during each synthetic pass.

Satellite self-rotation is separate from orbital motion. Period 0 means no rotation; rotating periods from 3 through 180 seconds are retained. Positive periods below 3 seconds and periods over 180 seconds are excluded and rejected, not relabeled as static.

Allowed spin axes are configured in `models/spin_axes.json`, keyed by `.blend` filename. For example, `{"SL-14.blend": {"spin_axes": ["X", "Z"]}}` selects one of those Blender scene axes for each curve. Models not listed there select from X, Y, and Z. The selection is deterministic for a given seed.

Physical-scale calibration of the `.blend` assets and a large 5–10k GPU dataset run are the next stages.
