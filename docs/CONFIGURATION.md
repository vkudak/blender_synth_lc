# Configuration Reference

Both INI files use `[blender]`, `[paths]`, `[run]`, `[observer]`, `[orbit]`, `[pass]`, `[sun]`, `[noise]`, `[sensor]`, and `[render]`. Single-curve configuration uses `[attitude]`; dataset configuration instead uses `[dataset]`, `[dataset.period]`, `[dataset.tumbling]`, `[dataset.precession]`, and `[dataset.scale]`. Values below are the supported options and their meanings; numeric defaults are the defaults in the loader unless a value is explicitly described as being from the example INI.

Topic-specific details with formulas and caveats live in dedicated pages: [Photometric Filters](PHOTOMETRIC_FILTERS.md) for `[sensor]`, [Sensor Noise Model](SENSOR_NOISE_MODEL.md) for `[noise]`, and [Coordinate System and Scenario Model](COORDINATE_SYSTEM.md) for the reference frames used by orbit/observer settings.

## `[blender]`

- `executable`: path to Blender. Must point to an existing executable.

## `[paths]`

- `model`: single-curve model path. Required for `kind=curve`; overridden by CLI `--model`.
- `models_dir`: directory containing `.blend` assets; default `models`.
- `models`: dataset-only comma-separated model names. Empty means discover all `.blend` files in `models_dir` except skipped names.
- `skip_models`: comma-separated model filenames excluded during discovery. Defaults to `Topex_g.blend,Topex_g3.blend`.
- `output`: single-curve output filename; default `reports/lotos_lightcurve.csv` in the example.
- `output_dir`: batch output directory; defaults to `reports/dataset` for dataset runs and `reports` for curve runs.

Paths can be absolute or repository-relative. Dataset model names may be supplied with or without the `.blend` suffix.

## `[run]`

- `seed`: integer seed; default `42` for a curve and `1` in the dataset example. Controls reproducible random choices for a fixed code, model, and configuration.
- `device`: `auto`, `cpu`, `cuda`, or `optix`. `auto` selects an available GPU backend when Blender can initialize one, otherwise CPU. An explicitly requested but unavailable GPU backend is an error. For large batches, validate the chosen backend with a small run first.

## `[observer]`

- `mode`: `fixed` or `random`. Random mode samples latitude uniformly by surface area and longitude uniformly; the configured altitude is retained.
- `latitude_deg`: fixed geodetic latitude in `[-90, 90]`; default `48.633`.
- `longitude_deg`: fixed longitude in `[-180, 180]`; default `22.33`.
- `altitude_m`: observer height in meters; default `0`. Must be finite and at least `-1000`.

## `[orbit]`

- `mode`: `random` or `fixed`.
- `altitude_min_km`, `altitude_max_km`: random circular-orbit altitude bounds, inclusive, in `[300, 3000] km`; defaults `300` and `3000`.
- `altitude_km`: fixed-orbit altitude in `[300, 3000] km`; default `800`.
- `inclination_min_deg`, `inclination_max_deg`: random inclination bounds in `[0, 180] deg`; defaults `0` and `180`. When the full range is used, sampling is uniform in cosine, not uniform in angle.
- `inclination_deg`: fixed-orbit inclination in `[0, 180] deg`; default `51.6`.
- `raan_deg`: fixed orbit right ascension of the ascending node in `[0, 360)`; default `0`.
- `phase_deg`: fixed orbit phase in `[0, 360)` at the pass epoch; default `0`.
- `align_for_pass`: boolean. For a fixed orbit, `true` adjusts phase so closest approach to the observer occurs at epoch and rejects an orbit that fails the elevation mask; `false` uses the configured phase as-is. Random orbit mode always samples/alines candidates to find a visible closest approach.

The orbit is circular and propagated with a two-body Earth gravitational parameter. The altitude bounds are validated to remain in the implemented 300-3000 km range.

## `[pass]`

- `duration_s`: requested observation window centered on the orbit epoch; default `60`. The epoch is closest approach when the orbit is aligned.
- `cadence_s`: time between samples; default `10`. The duration must be an integer multiple of cadence, and at least one interval is required. The initial sampling grid contains `duration / cadence + 1` points.
- `minimum_elevation_deg`: satellite-center elevation mask in `[10, 90)`; default `20`. Values below `10` emit a warning and are clamped to `10`. The selected curve uses the longest consecutive segment above the mask and must retain at least 85% of the requested samples (at most 15% may be trimmed). Otherwise the whole curve is rejected. Fixed configurations fail; random orbit generation retries candidates. Retained pass duration may be up to 15% shorter than requested.
- `max_attempts`: maximum random orbit candidates to try; default `1000`. Candidates must clear the elevation mask at closest approach and retain at least 85% of the requested sample grid. Failure suggests lowering the elevation mask, shortening the duration, or increasing this value.

## `[attitude]`

Single-curve configuration only. Dataset attitude settings belong in `[dataset.period]`.

- `mode`: `static`, `rotating`, or `random`. Static means spin period `0`; rotating uses `spin_period_s`; random chooses static or rotating. In random mode the default `rotating_fraction=0.5` alternates static and rotating curves by index for balance; other fractions use a seeded random choice.
- `spin_period_s`: fixed rotating period in seconds; default `20`. Accepted rotating periods are `3` through `180` seconds, subject to configured limits. Period `0` is static; positive periods below the minimum or values above the maximum are rejected.
- `spin_period_min_s`, `spin_period_max_s`: allowed random-period bounds; defaults `3` and `180`. Minimum must be positive and no greater than maximum.
- `rotating_fraction`: probability in `[0, 1]`; default `0.5`.
- `initial_phase_mode`: `fixed` or `random`; default `fixed`.
- `initial_phase_rad`: fixed spin phase in radians; default `0`.
- `precession_angle_deg`, `precession_period_s`, `precession_phase_deg`: fixed precession values for a single curve. Dataset configs specify precession in `[dataset.precession]`.

Precession applies only to rotating curves. Dataset runs sample a phase uniformly from `0` to `360 deg`.

## `[sun]`

- `mode`: `random` or `vector`.
- `x`, `y`, `z`: components of the configured Earth-to-Sun direction for vector mode; default example `0.71, -0.42, 0.56`. The vector is normalized by the renderer; it must not be zero.
- `energy`: Sun irradiance in `W/m^2`; the example uses `1361`, approximately solar irradiance at 1 AU. This controls the Blender Sun light energy.
- `max_eclipse_fraction`: maximum fraction of retained pass samples that may be eclipsed; default `0.15`, valid in `[0, 1)`. A vector mode exceeding the limit is rejected; random mode resamples a direction.

Earth occultation uses a conical shadow with the finite angular disk of the Sun. Samples in either umbra or penumbra count toward `max_eclipse_fraction`; umbra samples have zero flux, while penumbra samples are rendered and their flux is scaled by the visible fraction of the solar disk. CSV rows report `shadow_state` (`sunlit`, `penumbra`, or `umbra`) and `solar_illumination_fraction` in addition to the backward-compatible `eclipsed` flag. The synthetic Earth does not cast a separate directional-light shadow in Blender; its occultation is represented by this per-sample solar-disk fraction.

## `[render]`

- `resolution`: square render width and height in pixels; default `128`.
- `samples`: Cycles samples per rendered frame; default `8`.
- `exposure`: Blender exposure in EV; default `-8.8`. Adjust for model materials and highlights.
- `scene_meters_per_unit`: physical meters represented by one Blender unit; default `1`, must be positive.
- `script_output`: optional path for a saved renderer script; empty means use the normal renderer entry point.

The render uses Cycles, denoising, AgX, a black background, a close-up orthographic camera, and a Sun light. Existing cameras and lights in the model are hidden from rendering.

## `[noise]`

- `reference_snr`: signal-to-noise ratio for normalized flux `1` at `90 deg` elevation; default `50`. This defines the reference 1-sigma uncertainty as `1 / reference_snr`.
- `bias_level`: constant detector bias/dark offset added to every sample, in normalized-flux units; default `0` (disabled).
- `readout_noise_std`: per-sample Gaussian readout noise 1-sigma; default `0`.
- `correlated_noise_std` and `correlation_time_s`: frame-to-frame AR(1) correlated noise amplitude and its correlation time in seconds; both default to `0` (white noise).
- `saturation_level`: full-well clipping level; default `0` (disabled).
- `adc_bits`: ADC quantization bit depth (for example `12` or `16`); default `0` (disabled).

The baseline noise model is a Gaussian approximation to photon shot noise, scaled by Kasten-Young relative airmass so that fainter points and lower elevations have larger relative uncertainty; the clean `relative_flux` remains unchanged. On top of it, the optional detector stages form a sensor pipeline: correlated noise, readout noise, bias, saturation clipping, and ADC quantization, all in normalized-flux units. See [Sensor Noise Model](SENSOR_NOISE_MODEL.md) for formulas, parameter semantics, and edge cases. The noise seed is separate and deterministic for each curve.

## `[sensor]`

- `filter_type`: monochrome sensor filter approximation; one of `none` (default), `luminance`, `johnson_b`, `johnson_v`, `johnson_r`, or `custom`.
- `rgb_weights`: three comma-separated non-negative weights with a positive sum, required only for `filter_type = custom` and rejected otherwise. Weights are normalized to sum 1 automatically.

See [Photometric Filters](PHOTOMETRIC_FILTERS.md) for the preset weight tables (including Johnson-Cousins B/V/R approximations) and the approximation caveats.

## `[dataset]`

- `total_curves`: positive integer target for the entire dataset; default `10000`. Curves are divided evenly among selected models, with any remainder assigned in selection order.
- `workers`: number of parallel Blender processes; defaults to `1` and can be overridden with `--workers`. See the [parallel generation guide](PARALLEL_GENERATION_GUIDE.md).

## `[dataset.tumbling]`

- `fraction`: probability in `[0, 1]` that any dataset curve tumbles; default `0.01`, including when the section is absent. Selection is seeded independently per curve, so the realized fraction is approximate. Tumbling overrides the selected static/rotating mode and disables precession for that curve; set this to `0` to disable it.

Tumbling is a kinematic approximation, not a torque-free rigid-body simulation. It composes local X, Y, and Z rotations as `Q = Qx @ Qy @ Qz` relative to the model's original orientation. Each axis receives an independently sampled period uniformly within `spin_period_min_s` and `spin_period_max_s` (seconds) and an initial phase uniformly in `[0, 2π)` radians. The quaternion is evaluated at each sample time and animation frame. The model's ordinary spin-axis restrictions do not apply. The JSON sidecar records `tumbling_active`, the X/Y/Z `tumbling_periods_s`, and `tumbling_phases_rad`; for a tumbling curve the legacy spin period, phase, and axis describe only its X component, not a single physical spin axis.

## `[dataset.period]`

- `mode`: `static`, `rotating`, or `random`. Static means spin period `0`; rotating uses `spin_period_s`; random chooses static or rotating.
- `spin_period_s`: fixed rotating period in seconds; default `20`.
- `spin_period_min_s`, `spin_period_max_s`: random rotating-period bounds in seconds; defaults `3` and `180`. Both must be finite, and the minimum must be positive and no greater than the maximum.
- `rotating_fraction`: probability of a rotating curve in random mode, in `[0, 1]`; default `0.5`. At exactly `0.5`, static and rotating curves alternate by curve index.
- `initial_phase_mode`: `fixed` or `random`; default `fixed`. `initial_phase_rad` sets the fixed spin phase in radians; default `0`.

## `[dataset.precession]`

- `fraction`: probability that a rotating curve has precession, in `[0, 1]`. Selection is seeded and independent per curve, so the realized fraction can differ, especially in small datasets. Static curves never precess.
- `angle_mode`, `period_mode`: each is `fixed` or `random`. Fixed angle uses `angle_deg`; random mode samples uniformly between `angle_min_deg` and `angle_max_deg` (ordered within `[0, 180] deg`). Fixed period uses `period_s`; random mode samples uniformly between `period_min_s` and `period_max_s` (positive and ordered, in seconds).
- Only the fields for the selected mode may be present. The example uses `random` for both angle and period.

## `[dataset.scale]`

- `mode`: `fixed` or `random`. Fixed mode uses `factor`; random mode samples uniformly between `min_factor` and `max_factor`.
- Scale factors are finite, positive, dimensionless, and ordered. Each dataset curve independently samples an isotropic multiplier from the selected value or bounds, scaling model dimensions relative to its calibrated or native size. Curve generation always uses a multiplier of `1`.
- Only the fields for the selected mode may be present.

## Spin-axis rules

`models/spin_axes.json` optionally constrains spin-axis selection per model filename. Each value has a non-empty `spin_axes` array containing any of `X`, `Y`, and `Z`, for example:

```json
{
  "SL-14.blend": {"spin_axes": ["X", "Z"]}
}
```

Unlisted models use all three axes. These are Blender scene axes; selection is made for each curve using its seeded random generator.

## Model shape metadata

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
