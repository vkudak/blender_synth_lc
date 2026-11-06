# Blender Synthetic Light Curves

This project generates synthetic light curves of resident space objects. In combination with real light curves these data will be used to train an AI model to determine the operational state of an RSO (stable/tumbling). The synthetic data provides controlled examples with known orbit, illumination, and attitude parameters; it is not a substitute for validating the model against representative real observations.

## Project Overview

The host-side Python scripts read INI configuration, select models and seeds, then launch Blender in background mode. `scripts/render_lightcurve.py` builds a pass scenario, updates a Blender scene for each observation time, renders the illuminated model, and writes the curve and metadata.

Main components:

- `scripts/generate_curve.py`: render one curve for one model.
- `scripts/generate_dataset.py`: render a batch for selected or discovered models.
- `scripts/render_lightcurve.py`: Blender-side scenario generation, rendering, and output.
- `scripts/audit_models.py` and `scripts/inspect_blend.py`: inspect `.blend` assets and report scene/object information.
- `src/blender_synth_lc/`: configuration, orbit, attitude, illumination, and Blender job helpers.
- `config/curve.ini` and `config/dataset.ini`: example configurations.

The initial implementation targets Blender 4.5 LTS and uses the Blender 4.5 Python API. The installed and tested executable is Blender 4.5.15 LTS. See the [Blender 4.5 API documentation](https://docs.blender.org/api/4.5/) when changing Blender integration.

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
--curves-per-model N Override [dataset] curves_per_model
--seed INTEGER       Override [run] seed
--device DEVICE      auto, cpu, cuda, or optix
```

Example smoke run:

```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --model Lotos_model.blend \
  --curves-per-model 1 \
  --output-dir reports/dataset_smoke \
  --device cpu
```

If `[paths] models` is empty, every `.blend` in `models_dir` is selected except entries in `skip_models`. If it is non-empty, it is an explicit comma-separated selection. CLI `--model` values are names resolved under `models_dir` (unless an absolute path is supplied); the option may be repeated. Empty-geometry assets fail at render time and should be excluded. Dataset filenames contain the model stem, seed, zero-based curve index, and a unique random token; the index restarts for each model. Each curve also has JSON and SVG sidecars.

The total requested curve count is the number of selected models multiplied by `curves_per_model`. A model's base seed is offset by 10,000 for each model in the selection; the curve index is added within that model.

## Configuration Reference

Both INI files use `[blender]`, `[paths]`, `[run]`, `[observer]`, `[orbit]`, `[pass]`, `[attitude]`, `[sun]`, and `[render]`. Dataset configuration additionally uses `[dataset]`. Values below are the supported options and their meanings; numeric defaults are the defaults in the loader unless a value is explicitly described as being from the example INI.

### `[blender]`

- `executable`: path to Blender. Must point to an existing executable.

### `[paths]`

- `model`: single-curve model path. Required for `kind=curve`; overridden by CLI `--model`.
- `models_dir`: directory containing `.blend` assets; default `models`.
- `models`: dataset-only comma-separated model names. Empty means discover all `.blend` files in `models_dir` except skipped names.
- `skip_models`: comma-separated model filenames excluded during discovery. Defaults to `Topex_g.blend,Topex_g3.blend`.
- `output`: single-curve output filename; default `reports/lotos_lightcurve.csv` in the example.
- `output_dir`: batch output directory; defaults to `reports/dataset` for dataset runs and `reports` for curve runs.

Paths can be absolute or repository-relative. Dataset model names may be supplied with or without the `.blend` suffix.

### `[run]`

- `seed`: integer seed; default `42` for a curve and `1` in the dataset example. Controls reproducible random choices for a fixed code, model, and configuration.
- `device`: `auto`, `cpu`, `cuda`, or `optix`. `auto` selects an available GPU backend when Blender can initialize one, otherwise CPU. An explicitly requested but unavailable GPU backend is an error. For large batches, validate the chosen backend with a small run first.

### `[observer]`

- `mode`: `fixed` or `random`. Random mode samples latitude uniformly by surface area and longitude uniformly; the configured altitude is retained.
- `latitude_deg`: fixed geodetic latitude in `[-90, 90]`; default `48.633`.
- `longitude_deg`: fixed longitude in `[-180, 180]`; default `22.33`.
- `altitude_m`: observer height in meters; default `0`. Must be finite and at least `-1000`.

### `[orbit]`

- `mode`: `random` or `fixed`.
- `altitude_min_km`, `altitude_max_km`: random circular-orbit altitude bounds, inclusive, in `[300, 3000] km`; defaults `300` and `3000`.
- `altitude_km`: fixed-orbit altitude in `[300, 3000] km`; default `800`.
- `inclination_min_deg`, `inclination_max_deg`: random inclination bounds in `[0, 180] deg`; defaults `0` and `180`. When the full range is used, sampling is uniform in cosine, not uniform in angle.
- `inclination_deg`: fixed-orbit inclination in `[0, 180] deg`; default `51.6`.
- `raan_deg`: fixed orbit right ascension of the ascending node in `[0, 360)`; default `0`.
- `phase_deg`: fixed orbit phase in `[0, 360)` at the pass epoch; default `0`.
- `align_for_pass`: boolean. For a fixed orbit, `true` adjusts phase so closest approach to the observer occurs at epoch and rejects an orbit that fails the elevation mask; `false` uses the configured phase as-is. Random orbit mode always samples/alines candidates to find a visible closest approach.

The orbit is circular and propagated with a two-body Earth gravitational parameter. The altitude bounds are validated to remain in the implemented 300-3000 km range.

### `[pass]`

- `duration_s`: requested observation window centered on closest approach; default `60`.
- `cadence_s`: time between samples; default `10`. The duration must be an integer multiple of cadence, and at least one interval is required. The initial sampling grid contains `duration / cadence + 1` points.
- `minimum_elevation_deg`: observer elevation mask in `[0, 90)`; default `10`. The selected curve uses the longest consecutive segment above the mask and must contain at least two samples. Consequently, the retained pass duration can be shorter than requested.
- `max_attempts`: maximum random orbit candidates to try; default `1000`. Relevant to random orbit generation; failure suggests lowering the elevation mask or increasing this value.

### `[attitude]`

- `mode`: `static`, `rotating`, or `random`. Static means spin period `0`; rotating uses `spin_period_s`; random chooses static or rotating. In random mode the default `rotating_fraction=0.5` alternates static and rotating curves by index for balance; other fractions use a seeded random choice.
- `spin_period_s`: fixed rotating period in seconds; default `20`. Accepted rotating periods are `3` through `180` seconds, subject to configured limits. Period `0` is static; positive periods below the minimum or values above the maximum are rejected.
- `spin_period_min_s`, `spin_period_max_s`: allowed random-period bounds; defaults `3` and `180`. Minimum must be positive and no greater than maximum.
- `rotating_fraction`: in `[0, 1]`; default `0.5`. In dataset configuration, `[dataset] rotating_fraction` overrides it for random attitude mode.
- `initial_phase_mode`: `fixed` or `random`; default `fixed` for a curve and `random` in the dataset example.
- `initial_phase_rad`: fixed spin phase in radians; default `0`.
- `precession_angle_deg`: fixed precession cone half-angle in `[0, 180] deg`; `0` disables precession. Default `0`.
- `precession_period_s`: fixed precession period in seconds; must be positive when the angle is nonzero. Default `60`.
- `precession_phase_deg`: fixed precession phase in degrees; default `0`.

Precession applies only to rotating curves. Dataset runs instead sample the angle and period from the ranges in `[dataset]` and sample a phase uniformly from `0` to `360 deg`.

### `[sun]`

- `mode`: `random` or `vector`.
- `x`, `y`, `z`: components of the configured Earth-to-Sun direction for vector mode; default example `0.71, -0.42, 0.56`. The vector is normalized by the renderer; it must not be zero.
- `energy`: Sun irradiance in `W/m^2`; the example uses `1361`, approximately solar irradiance at 1 AU. This controls the Blender Sun light energy.
- `max_eclipse_fraction`: maximum fraction of retained pass samples that may be eclipsed; default `0.15`, valid in `[0, 1)`. A vector mode exceeding the limit is rejected; random mode resamples a direction.

Earth occultation uses a cylindrical shadow: samples behind Earth and within the Earth-radius shadow cylinder are marked eclipsed and assigned zero flux.

### `[render]`

- `resolution`: square render width and height in pixels; default `128`.
- `samples`: Cycles samples per rendered frame; default `8`.
- `exposure`: Blender exposure in EV; default `-8.8`. Adjust for model materials and highlights.
- `scene_meters_per_unit`: physical meters represented by one Blender unit; default `1`, must be positive.
- `satellite_size_m`: target length in meters of the model's longest bounding-box dimension after uniform scaling; default `4`, must be positive. Geometry is centered and scaled to this size while the satellite root remains at the local origin.
- `script_output`: optional path for a saved renderer script; empty means use the normal renderer entry point.

The render uses Cycles, denoising, AgX, a black background, a close-up orthographic camera, and a Sun light. Existing cameras and lights in the model are hidden from rendering.

### `[dataset]`

- `curves_per_model`: positive integer number of curves generated for every selected model; default `2`.
- `rotating_fraction`: probability of a rotating curve when `[attitude] mode=random`, in `[0, 1]`; default `0.5`. At exactly `0.5`, the renderer alternates static/rotating curves by curve index.
- `precession_angle_min_deg`, `precession_angle_max_deg`: ordered range in `[0, 180] deg`; example defaults `5` and `30`.
- `precession_period_min_s`, `precession_period_max_s`: ordered positive period range in seconds; example defaults `20` and `180`.

### Spin-axis rules

`models/spin_axes.json` optionally constrains spin-axis selection per model filename. Each value has a non-empty `spin_axes` array containing any of `X`, `Y`, and `Z`, for example:

```json
{
  "SL-14.blend": {"spin_axes": ["X", "Z"]}
}
```

Unlisted models use all three axes. These are Blender scene axes; selection is made for each curve using its seeded random generator.

## Coordinate System and Scenario Model

The orbit and ground-site calculations use Cartesian coordinates in meters with a common Earth-centered reference frame. The orbit propagation is ECI-like: the `XY` plane is the equatorial plane, `+Z` is the north-pole direction, and the orbit is first parameterized in its plane, then rotated by inclination and RAAN. At the orbit epoch, `phase_deg` sets the satellite's angle in that plane. Circular-orbit position and velocity are propagated from mean motion derived from Earth gravitational parameter and radius.

The observer's latitude and longitude are geodetic WGS-84 coordinates converted to Earth-fixed Cartesian coordinates. The local horizon basis defines azimuth clockwise from north and elevation above the horizon. For simplicity, Earth rotation is ignored during a pass: the observer remains fixed and the orbit coordinates are compared directly against that fixed site. This is a simplified shared frame, not a full Earth-orientation transformation.

Blender uses a satellite-centered rendering scene for numerical precision. The satellite root stays at the origin; at each sample, Earth, the observer marker, and the Sun are positioned relative to the satellite. The camera is placed in the observer-to-satellite direction and tracks the satellite center, but does not rotate with the spacecraft body. `scene_meters_per_unit` converts physical distances to Blender units. The model's longest combined mesh-bounds dimension is uniformly scaled to `satellite_size_m`.

## How a Light Curve Is Generated

1. The renderer initializes a seeded random generator for the curve and chooses fixed or random observer and attitude parameters.
2. It creates a circular orbit. Random mode samples altitude, inclination, RAAN, and phase, then aligns candidates to closest approach and retries until the elevation mask is met. Fixed mode either aligns phase or uses the configured phase according to `align_for_pass`.
3. The requested time window is sampled symmetrically around the orbit epoch (`t=0`), which is closest approach when the orbit is aligned. Samples below the elevation mask are removed by selecting the longest consecutive visible segment.
4. A Sun direction is selected. Random directions are sampled over the sphere; vector mode uses the configured vector. Directions are rejected if the retained pass exceeds the allowed eclipse fraction.
5. The loaded spacecraft mesh objects are centered under a common root and scaled. For each non-eclipsed sample, the root attitude is updated, the camera observes from the current line of sight, and Blender renders an OpenEXR frame. Eclipsed samples are recorded with zero flux without rendering.
6. The renderer sums linear RGB values across rendered pixels. It applies the inverse-square range correction relative to the first retained sample, then divides by the maximum corrected value to obtain `relative_flux` in `[0, 1]`.
7. CSV data, JSON scenario/render metadata, and an SVG plot are written together.

Rotation period `0` represents a static body. Rotating periods below `3 s` or above `180 s` are excluded by default. Precession changes the spin-axis orientation around a cone and is applied only to rotating bodies.

## Output Format and Interpretation

The CSV columns are:

- `time_from_start_s`: seconds from the first retained sample.
- `range_m`, `azimuth_deg`, `elevation_deg`: observer geometry at that sample.
- `visible`: visibility-mask flag (`0` or `1`); retained rows are expected to be visible.
- `eclipsed`: cylindrical Earth-shadow flag (`0` or `1`).
- `render_flux_linear_rgb`: sum of linear RGB render pixels before range correction.
- `flux_with_range_correction`: raw render flux multiplied by `(reference_range / current_range)^2`.
- `relative_flux`: corrected flux normalized to the largest value in the curve.

The JSON sidecar records the model, seed, observer, orbit, retained pass, attitude/precession, Blender version/device/render settings, eclipse fraction, and limitations. The SVG displays normalized relative flux against time.

These values are a rendering-based relative-flux proxy, not calibrated magnitude or absolute photometry. Current limitations include uncalibrated physical model dimensions/material reflectance, no atmosphere, cylindrical rather than conical shadow, circular two-body orbits, and no Earth rotation. Physical-scale asset calibration and large GPU dataset runs remain follow-up work.

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
