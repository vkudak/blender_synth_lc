# Blender Synthetic Light Curves

This project generates synthetic light curves of resident space objects. In combination with real light curves these data will be used to train an AI model to determine the operational state of an RSO (stable/tumbling). The synthetic data provides controlled examples with known orbit, illumination, and attitude parameters; it is not a substitute for validating the model against representative real observations.

## Project Overview

The host-side Python scripts read INI configuration, select models and seeds, then launch Blender in background mode. `scripts/render_lightcurve.py` builds a pass scenario, updates a Blender scene for each observation time, renders the illuminated model, and writes the curve and metadata.

Main components:

- `scripts/generate_curve.py`: render one curve for one model.
- `scripts/generate_dataset.py`: render a batch for selected or discovered models (with optional parallel processing).
- `scripts/render_lightcurve.py`: Blender-side scenario generation, rendering, and output.
- `scripts/audit_models.py` and `scripts/inspect_blend.py`: inspect `.blend` assets and report scene/object information.
- `src/blender_synth_lc/`: configuration, orbit, attitude, illumination, and Blender job helpers.
- `config/curve.ini` and `config/dataset.ini`: example configurations.

The initial implementation targets Blender 4.5 LTS and uses the Blender 4.5 Python API. The installed and tested executable is Blender 4.5.15 LTS. See the [Blender 4.5 API documentation](https://docs.blender.org/api/4.5/) when changing Blender integration.

**For accelerated dataset generation with multiple parallel Blender processes, see the [parallel generation guide](docs/PARALLEL_GENERATION_GUIDE.md).**

## Requirements and Setup

- Python 3.10 or later (use a project virtual environment).
- Blender 4.5 LTS, with a working CPU or supported GPU Cycles device.
- `.blend` spacecraft models with at least one mesh object containing vertices.

Create the environment and install development dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Set the Blender executable in the configuration's `[blender] executable` field. The checked-in examples currently contain a machine-specific path. Relative model and output paths are resolved from the repository root, and commands should be run from that root.

Run tests with:

```bash
.venv/bin/python -m pytest -q
```

## Generate a Single Curve

Edit `config/curve.ini`, then run:

```bash
.venv/bin/python scripts/generate_curve.py --config config/curve.ini
```

`--config` is optional; the default is `config/curve.ini`. Supported overrides:

```text
--model PATH       Override [paths] model
--output PATH      Override [paths] output
--seed INTEGER     Override [run] seed
--device DEVICE    auto, cpu, cuda, or optix
```

Example:

```bash
.venv/bin/python scripts/generate_curve.py \
  --config config/curve.ini \
  --model models/Lotos_model.blend \
  --output reports/lotos_test.csv \
  --seed 123 --device cpu
```

The configured output is a filename stem: the renderer adds a timestamp (and a collision suffix if needed) so an existing curve is not overwritten. Each run writes a CSV, a same-stem JSON metadata file, and a same-stem SVG diagnostic plot.

To save the Blender-side renderer with the run arguments embedded, set `[render] script_output`, for example `reports/generated_curve.py`. That script is both saved and executed by Blender. Leave it empty to run `scripts/render_lightcurve.py` directly. Running a saved script from Blender's Text Editor also creates a Timeline animation of the pass.

## Generate a Dataset

Edit `config/dataset.ini`, then run:

```bash
.venv/bin/python scripts/generate_dataset.py --config config/dataset.ini
```

`--config` is optional; the default is `config/dataset.ini`. Supported overrides:

```text
--model NAME         Select a model; repeat to select multiple models
--output-dir PATH    Override [paths] output_dir
--total-curves N     Override [dataset] total_curves (default 10000)
--seed INTEGER       Override [run] seed
--device DEVICE      auto, cpu, cuda, or optix
--workers N          Override [dataset] workers (number of parallel Blender processes)
```

Example smoke run:

```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --model Lotos_model.blend \
  --total-curves 1 \
  --output-dir reports/dataset_smoke \
  --device cpu
```

### Parallel Dataset Generation

Dataset generation supports running multiple Blender processes in parallel to accelerate rendering. The `workers` parameter can be set in the configuration file or overridden via the command line:

**In config file (config/dataset.ini):**
```ini
[dataset]
workers = 4
```

**Or via command line:**
```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 4000 \
  --workers 4 \
  --device cuda
```

**Windows PowerShell:**
```powershell
.venv\Scripts\python scripts/generate_dataset.py `
  --config config/dataset.ini `
  --total-curves 8000 `
  --workers 4 `
  --device cuda
```

The `workers` parameter defaults to 1 (sequential processing). Recommended values are 3-4 depending on available system resources (CPU cores, GPU memory). Each worker runs an independent Blender process, so ensure sufficient system memory (typically 2-4 GB per process for CUDA renders). Results from all workers are coordinated through a shared index file (`.dataset_indexes.jsonl`), allowing safe resumption and incremental runs.

For the technical details of how the multiprocessing is implemented, see the [multiprocessing implementation notes](docs/MULTIPROCESSING_IMPLEMENTATION.md) and the [implementation summary](docs/IMPLEMENTATION_SUMMARY.md).

If `[paths] models` is empty, every `.blend` in `models_dir` is selected except entries in `skip_models`. If it is non-empty, it is an explicit comma-separated selection. CLI `--model` values are names resolved under `models_dir` (unless an absolute path is supplied); the option may be repeated. Before rendering, dataset generation inspects every selected model with Blender. If any mesh object has zero evaluated vertices, it warns with the model and object names and stops before creating the output directory or rendering; the user must repair or remove the affected model. Dataset filenames contain the model stem, seed, zero-based curve index, and a unique random token; the index restarts for each model. Each curve also has JSON and SVG sidecars.

Dataset runs are resumable. The output directory contains a hidden `.dataset_indexes.jsonl` journal that records each curve index only after its CSV, JSON, and SVG have been written. Re-running with the same settings, models, and seed skips recorded curves and continues missing indexes. Increasing `total_curves` continues at the new indexes. A changed configuration, model file, or seed gets a separate index entry. Use `--force_indexes` (or `--force-indexes`) to delete the saved indexes and regenerate all requested curves. This removes only the index file; existing outputs are kept, and regenerated curves get new filenames.

Dataset generation displays completed-curve progress using a progress bar (tqdm) on stderr. Blender's stdout and stderr are appended to `blender.log` in the configured output directory; reruns retain earlier logs, so the file can grow over time. Failed model runs report the log location on the console. Model validation errors remain visible on the console, and single-curve generation keeps Blender output on the console. To monitor the dataset log in PowerShell, use:

```powershell
Get-Content reports\dataset\blender.log -Wait -Tail 20
```

`total_curves` is the total number of curves across all selected models. The runner divides this total as evenly as possible; model counts differ by at most one, with any remainder assigned to the first models in selection order. Automatically discovered models are sorted by filename. The total must be at least the number of selected models so every model receives at least one curve. A model's base seed is offset by 10,000 for each model in the selection; the curve index is added within that model.

## Configuration

Both INI files use `[blender]`, `[paths]`, `[run]`, `[observer]`, `[orbit]`, `[pass]`, `[sun]`, `[noise]`, `[sensor]`, and `[render]`. Single-curve configuration uses `[attitude]`; dataset configuration instead uses `[dataset]`, `[dataset.period]`, `[dataset.tumbling]`, `[dataset.precession]`, and `[dataset.scale]`.

The full per-section option reference, including the model metadata files `models/model_shapes.json` and `models/spin_axes.json`, lives in [Configuration Reference](docs/CONFIGURATION.md). Topic-specific details:

- [Photometric Filters](docs/PHOTOMETRIC_FILTERS.md) — `[sensor]` monochrome sensor weighting and Johnson-Cousins B/V/R approximations.
- [Sensor Noise Model](docs/SENSOR_NOISE_MODEL.md) — `[noise]` shot noise and detector effects.
- [Coordinate System and Scenario Model](docs/COORDINATE_SYSTEM.md) — reference frames and epoch conventions for orbit and observer geometry.

## How a Light Curve Is Generated

1. The renderer initializes a seeded random generator for the curve and chooses fixed or random observer and attitude parameters.
2. It creates a circular orbit. Random mode samples altitude, inclination, RAAN, and phase, then retries candidates until closest approach clears the elevation mask and the longest consecutive visible segment retains at least 85% of the requested samples. Fixed mode either aligns phase or uses the configured phase according to `align_for_pass`; it fails if the retained segment is shorter than this limit.
3. The requested time window is sampled symmetrically around the orbit epoch (`t=0`), which is closest approach when the orbit is aligned. Samples below the elevation mask are removed by selecting the longest consecutive visible segment. Trimming exactly 15% is accepted; trimming more rejects the whole curve.
4. A Sun direction is selected. Random directions are sampled over the sphere; vector mode uses the configured vector. Directions are rejected if the retained pass exceeds the allowed eclipse fraction.
5. The loaded spacecraft mesh objects are centered under a common root and scaled. For each sample outside the umbra, the root attitude is updated, the camera observes from the current line of sight, and Blender renders an OpenEXR frame. Penumbra flux is scaled by the visible solar-disk fraction; umbra samples are recorded with zero flux without rendering.
6. The renderer sums linear RGB values across rendered pixels, applying the `[sensor]` filter weights per pixel when a `filter_type` other than `none` is selected. It applies the inverse-square range correction relative to the first retained sample, then divides by the maximum corrected value to obtain `relative_flux` in `[0, 1]`.
7. CSV data, JSON scenario/render metadata, and an SVG plot are written together.

Rotation period `0` represents a static body. Rotating periods below `3 s` or above `180 s` are excluded by default. Precession changes the spin-axis orientation around a cone and is applied only to rotating bodies.

## Output Format

Each curve writes three files with a common stem: a CSV with per-sample geometry and flux columns, a JSON sidecar with scenario/render metadata, and an SVG diagnostic plot. The CSV columns, JSON sidecar contents, and interpretation caveats are documented in [Output Format and Interpretation](docs/OUTPUT_FORMAT.md).

## Audit Blender Models

Audit `.blend` files and write a combined JSON inventory:

```bash
BLENDER_BIN=/path/to/blender \
  .venv/bin/python scripts/audit_models.py \
  --models models \
  --output reports/model_inventory.json
```

Options:

- `--blender PATH`: Blender executable; defaults to `BLENDER_BIN` or `blender` on `PATH`. The script requires Blender 4.5 LTS.
- `--models PATH`: directory of `.blend` files; default `models`.
- `--output PATH`: combined JSON report; default `reports/model_inventory.json`.

The audit reports scene/object/material/image data and evaluated world-space mesh bounds. Bounds use Blender scene units; `unit_system = METRIC` alone does not guarantee real-world scale. The current inventory notes some TOPEX models with empty mesh objects, which cannot be used as render geometry.

## License

This project is licensed under the GNU General Public License, version 3.0. See [LICENSE](LICENSE) for the full text.
