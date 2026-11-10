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
--total-curves N     Override [dataset] total_curves (default 10000)
--seed INTEGER       Override [run] seed
--device DEVICE      auto, cpu, cuda, or optix
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

If `[paths] models` is empty, every `.blend` in `models_dir` is selected except entries in `skip_models`. If it is non-empty, it is an explicit comma-separated selection. CLI `--model` values are names resolved under `models_dir` (unless an absolute path is supplied); the option may be repeated. Before rendering, dataset generation inspects every selected model with Blender. If any mesh object has zero evaluated vertices, it warns with the model and object names and stops before creating the output directory or rendering; the user must repair or remove the affected model. Dataset filenames contain the model stem, seed, zero-based curve index, and a unique random token; the index restarts for each model. Each curve also has JSON and SVG sidecars.

Dataset runs are resumable. The output directory contains a hidden `.dataset_indexes.jsonl` journal that records each curve index only after its CSV, JSON, and SVG have been written. Re-running with the same settings, models, and seed skips recorded curves and continues missing indexes. Increasing `total_curves` continues at the new indexes. A changed configuration, model file, or seed gets a separate index entry. Use `--force_indexes` (or `--force-indexes`) to delete the saved indexes and regenerate all requested curves. This removes only the index file; existing outputs are kept, and regenerated curves get new filenames.

Dataset generation displays completed-curve progress on stderr. Blender's stdout and stderr remain connected to the console, so its diagnostics and traceback are visible if a run fails.

`total_curves` is the total number of curves across all selected models. The runner divides this total as evenly as possible; model counts differ by at most one, with any remainder assigned to the first models in selection order. Automatically discovered models are sorted by filename. The total must be at least the number of selected models so every model receives at least one curve. A model's base seed is offset by 10,000 for each model in the selection; the curve index is added within that model.

## Configuration Reference

Both INI files use `[blender]`, `[paths]`, `[run]`, `[observer]`, `[orbit]`, `[pass]`, `[attitude]`, `[sun]`, `[noise]`, and `[render]`. Dataset configuration additionally uses `[dataset]`. Values below are the supported options and their meanings; numeric defaults are the defaults in the loader unless a value is explicitly described as being from the example INI.

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

- `duration_s`: requested observation window centered on the orbit epoch; default `60`. The epoch is closest approach when the orbit is aligned.
- `cadence_s`: time between samples; default `10`. The duration must be an integer multiple of cadence, and at least one interval is required. The initial sampling grid contains `duration / cadence + 1` points.
- `minimum_elevation_deg`: satellite-center elevation mask in `[10, 90)`; default `20`. Values below `10` emit a warning and are clamped to `10`. The selected curve uses the longest consecutive segment above the mask and must retain at least 85% of the requested samples (at most 15% may be trimmed). Otherwise the whole curve is rejected. Fixed configurations fail; random orbit generation retries candidates. Retained pass duration may be up to 15% shorter than requested.
- `max_attempts`: maximum random orbit candidates to try; default `1000`. Candidates must clear the elevation mask at closest approach and retain at least 85% of the requested sample grid. Failure suggests lowering the elevation mask, shortening the duration, or increasing this value.

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

Earth occultation uses a conical shadow with the finite angular disk of the Sun. Samples in either umbra or penumbra count toward `max_eclipse_fraction`; umbra samples have zero flux, while penumbra samples are rendered and their flux is scaled by the visible fraction of the solar disk. CSV rows report `shadow_state` (`sunlit`, `penumbra`, or `umbra`) and `solar_illumination_fraction` in addition to the backward-compatible `eclipsed` flag. The synthetic Earth does not cast a separate directional-light shadow in Blender; its occultation is represented by this per-sample solar-disk fraction.

### `[render]`

- `resolution`: square render width and height in pixels; default `128`.
- `samples`: Cycles samples per rendered frame; default `8`.
- `exposure`: Blender exposure in EV; default `-8.8`. Adjust for model materials and highlights.
- `scene_meters_per_unit`: physical meters represented by one Blender unit; default `1`, must be positive.
- `script_output`: optional path for a saved renderer script; empty means use the normal renderer entry point.

### `[noise]`

- `reference_snr`: signal-to-noise ratio for normalized flux `1` at `90 deg` elevation; default `50`. This defines the reference 1-sigma uncertainty as `1 / reference_snr`.

The initial measurement-noise model is a Gaussian approximation to photon shot noise. For normalized clean flux `f` and elevation `e`, it calculates relative airmass with the Kasten-Young formula, normalized to exactly `1` at zenith: `X(e) = [sin(e) + 0.50572 * (e + 6.07995)^(-1.6364)]^(-1) / X(90 deg)`. The absolute uncertainty in normalized-flux units is `sigma = sqrt(f * X(e)) / reference_snr`, and the noisy value is sampled from `Normal(f, sigma)`. Thus fainter points and lower elevations have larger relative uncertainty; noise has zero mean and the clean `relative_flux` remains unchanged. This first model omits sky background, read noise, extinction of the mean signal, and absolute brightness differences between objects. The noise seed is separate and deterministic for each curve.

The render uses Cycles, denoising, AgX, a black background, a close-up orthographic camera, and a Sun light. Existing cameras and lights in the model are hidden from rendering. Every model must be listed in `models/model_shapes.json` with its shape metadata; optional per-model physical dimensions can be configured there, and models without `dimensions_m` are used at their native Blender bounds, assumed to already be correct.

### `[dataset]`

- `total_curves`: positive integer target for the entire dataset; default `10000`. Curves are divided evenly among selected models, with any remainder assigned in selection order.
- `rotating_fraction`: probability of a rotating curve when `[attitude] mode=random`, in `[0, 1]`; default `0.5`. At exactly `0.5`, the renderer alternates static/rotating curves by curve index.
- `precession_fraction`: probability that a rotating curve has precession, in `[0, 1]`; default `0.5`. Selection is seeded and independent per curve, so the realized fraction can differ, especially in small datasets. Static curves never precess. A zero sampled precession angle also disables precession.
- `precession_angle_min_deg`, `precession_angle_max_deg`: ordered range in `[0, 180] deg`; example defaults `5` and `30`.
- `precession_period_min_s`, `precession_period_max_s`: ordered positive period range in seconds; example defaults `20` and `180`.
- `model_scale_min`, `model_scale_max`: ordered, finite, positive dimensionless multipliers; example range `1` to `1.5`. Dataset curves independently sample an isotropic multiplier from this range, scaling the model dimensions relative to its calibrated or native size. Curve generation always uses a multiplier of `1`.

### Spin-axis rules

`models/spin_axes.json` optionally constrains spin-axis selection per model filename. Each value has a non-empty `spin_axes` array containing any of `X`, `Y`, and `Z`, for example:

```json
{
  "SL-14.blend": {"spin_axes": ["X", "Z"]}
}
```

Unlisted models use all three axes. These are Blender scene axes; selection is made for each curve using its seeded random generator.

`models/model_shapes.json` is required and must contain an entry for every model rendered; rendering fails for unlisted models. Each entry has:

- `body_shape` (required): non-empty list of strings describing the bus geometry, for example `["cube"]` or `["cylinder"]`.
- `solar_panel_count` (required): non-negative integer number of solar panels.
- `dimensions_m` (optional): calibrated final dimensions in meters along the original Blender scene X/Y/Z axes, each positive. The renderer scales the model independently along each axis to reach these dimensions.

```json
{
  "Topex_good.blend": {
    "body_shape": ["cube"],
    "solar_panel_count": 1,
    "dimensions_m": {"x": 4.0, "y": 2.0, "z": 1.5}
  }
}
```

`body_shape` and `solar_panel_count` are written to each curve's JSON sidecar.

If a listed model has no `dimensions_m`, its native bounds are left unchanged and treated as already correct. `scene_meters_per_unit` converts those native Blender units to meters. The JSON sidecar records the resulting dimensions, axis scale factors, and whether values came from this calibration file or native bounds.

## Coordinate System and Scenario Model

The orbit and ground-site calculations use Cartesian coordinates in meters with a common Earth-centered reference frame. The orbit propagation is ECI-like: the `XY` plane is the equatorial plane, `+Z` is the north-pole direction, and the orbit is first parameterized in its plane, then rotated by inclination and RAAN. At the orbit epoch, `phase_deg` sets the satellite's angle in that plane. Circular-orbit position and velocity are propagated from mean motion derived from Earth gravitational parameter and radius.

The observer's latitude and longitude are geodetic WGS-84 coordinates converted to Earth-fixed Cartesian coordinates. At the orbit epoch (`t=0`), the Earth-fixed and inertial axes coincide; at other times, the observer and local horizon rotate eastward around `+Z` with a constant sidereal period of 86,164.0905 seconds. Azimuth is clockwise from north and elevation is above the rotating horizon. Pass alignment accounts for the observer's rotational velocity so the range is locally minimal at the epoch. This relative epoch convention does not use UTC, Greenwich sidereal time, polar motion, or a full Earth-orientation transformation; RAAN and Sun direction are specified in the same epoch frame, not tied to an actual observation date.

Blender uses a satellite-centered rendering scene for numerical precision. The satellite root stays at the origin; at each sample, Earth, the observer marker, and the Sun are positioned relative to the satellite. The camera is placed in the observer-to-satellite direction and tracks the satellite center, but does not rotate with the spacecraft body. `scene_meters_per_unit` converts physical distances to Blender units. If a model has a `dimensions_m` entry in `models/model_shapes.json`, its combined mesh bounds are scaled independently along X/Y/Z; otherwise its native bounds are retained.

## How a Light Curve Is Generated

1. The renderer initializes a seeded random generator for the curve and chooses fixed or random observer and attitude parameters.
2. It creates a circular orbit. Random mode samples altitude, inclination, RAAN, and phase, then retries candidates until closest approach clears the elevation mask and the longest consecutive visible segment retains at least 85% of the requested samples. Fixed mode either aligns phase or uses the configured phase according to `align_for_pass`; it fails if the retained segment is shorter than this limit.
3. The requested time window is sampled symmetrically around the orbit epoch (`t=0`), which is closest approach when the orbit is aligned. Samples below the elevation mask are removed by selecting the longest consecutive visible segment. Trimming exactly 15% is accepted; trimming more rejects the whole curve.
4. A Sun direction is selected. Random directions are sampled over the sphere; vector mode uses the configured vector. Directions are rejected if the retained pass exceeds the allowed eclipse fraction.
5. The loaded spacecraft mesh objects are centered under a common root and scaled. For each sample outside the umbra, the root attitude is updated, the camera observes from the current line of sight, and Blender renders an OpenEXR frame. Penumbra flux is scaled by the visible solar-disk fraction; umbra samples are recorded with zero flux without rendering.
6. The renderer sums linear RGB values across rendered pixels. It applies the inverse-square range correction relative to the first retained sample, then divides by the maximum corrected value to obtain `relative_flux` in `[0, 1]`.
7. CSV data, JSON scenario/render metadata, and an SVG plot are written together.

Rotation period `0` represents a static body. Rotating periods below `3 s` or above `180 s` are excluded by default. Precession changes the spin-axis orientation around a cone and is applied only to rotating bodies.

## Output Format and Interpretation

The CSV columns are:

- `time_from_start_s`: seconds from the first retained sample.
- `range_m`, `azimuth_deg`, `elevation_deg`: observer geometry at that sample.
- `phase_angle_deg`: Sun-satellite-observer angle in degrees, evaluated at the satellite for each sample. Let `r_sat` be the satellite's Earth-centered position, `r_obs` the observer's Earth-centered position, `u_sun` the unit Earth-to-Sun direction, and `D_sun` the configured Sun distance. The vectors are `v_obs = r_obs - r_sat` and `v_sun = D_sun * u_sun - r_sat`; the column is `acos(clamp(dot(v_sun, v_obs) / (|v_sun| * |v_obs|), -1, 1))` converted to degrees. Thus `0 deg` means full phase (Sun and observer in the same direction from the satellite), `90 deg` quadrature, and `180 deg` new phase. The Sun position uses the same finite-distance approximation as the illumination model.
- `visible`: visibility-mask flag (`0` or `1`); retained rows are expected to be visible.
- `eclipsed`: flag (`0` or `1`) set for both penumbra and umbra samples.
- `shadow_state`: `sunlit`, `penumbra`, or `umbra` for the sample.
- `solar_illumination_fraction`: visible fraction of the solar disk, from `0` in umbra to `1` in full sunlight.
- `render_flux_linear_rgb`: sum of linear RGB render pixels before range correction.
- `flux_with_range_correction`: raw render flux multiplied by `(reference_range / current_range)^2`.
- `relative_flux`: corrected flux normalized to the largest value in the curve.
- `relative_flux_noisy`: clean normalized flux plus a seeded Gaussian noise sample; values are not clipped, so a noisy measurement may be negative.
- `noise_sigma`: per-sample absolute 1-sigma uncertainty in normalized-flux units.

The JSON sidecar records the model, seed, observer, orbit, retained pass, attitude/precession, Blender version/device/render settings, sampled model scale factor, final dimensions, eclipse fraction, and limitations. The SVG displays normalized relative flux against time.

These values are a rendering-based relative-flux proxy, not calibrated magnitude or absolute photometry. Models without `dimensions_m` in `models/model_shapes.json` are assumed to have correct native physical dimensions; material reflectance remains uncalibrated. Other limitations include no atmosphere, uniform scaling of the rendered flux by the visible solar-disk fraction in penumbra, circular two-body orbits, and a simplified Earth-orientation model. Per-model physical dimensions still need to be supplied and validated for calibrated assets.

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
