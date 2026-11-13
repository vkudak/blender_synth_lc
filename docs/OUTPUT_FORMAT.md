# Output Format and Interpretation

Each curve is written as three files with a common stem: a CSV with per-sample
geometry and flux columns, a JSON sidecar with scenario/render metadata, and
an SVG diagnostic plot of normalized relative flux against time.

The coordinate frames and conventions used by the columns below are described
in [Coordinate System and Scenario Model](COORDINATE_SYSTEM.md).

## CSV columns

- `time_from_start_s`: seconds from the first retained sample.
- `range_m`, `azimuth_deg`, `elevation_deg`: observer geometry at that sample.
- `phase_angle_deg`: Sun-satellite-observer angle in degrees, evaluated at the satellite for each sample. Let `r_sat` be the satellite's Earth-centered position, `r_obs` the observer's Earth-centered position, `u_sun` the unit Earth-to-Sun direction, and `D_sun` the configured Sun distance. The vectors are `v_obs = r_obs - r_sat` and `v_sun = D_sun * u_sun - r_sat`; the column is `acos(clamp(dot(v_sun, v_obs) / (|v_sun| * |v_obs|), -1, 1))` converted to degrees. Thus `0 deg` means full phase (Sun and observer in the same direction from the satellite), `90 deg` quadrature, and `180 deg` new phase. The Sun position uses the same finite-distance approximation as the illumination model.
- `visible`: visibility-mask flag (`0` or `1`); retained rows are expected to be visible.
- `eclipsed`: flag (`0` or `1`) set for both penumbra and umbra samples.
- `shadow_state`: `sunlit`, `penumbra`, or `umbra` for the sample.
- `solar_illumination_fraction`: visible fraction of the solar disk, from `0` in umbra to `1` in full sunlight.
- `render_flux_linear_rgb`: sum of linear RGB render pixels before range correction; with a `[sensor]` filter enabled it is the filter-weighted sum `w_R * R + w_G * G + w_B * B` per pixel (see [Photometric Filters](PHOTOMETRIC_FILTERS.md)).
- `flux_with_range_correction`: raw render flux multiplied by `(reference_range / current_range)^2`.
- `relative_flux`: corrected flux normalized to the largest value in the curve.
- `relative_flux_noisy`: clean normalized flux plus the seeded noise sample and any enabled sensor effects (bias, correlated/readout noise, saturation clipping, ADC quantization). Without sensor effects values are not clipped and may be negative; with `adc_bits` set they are non-negative and discrete. See [Sensor Noise Model](SENSOR_NOISE_MODEL.md).
- `noise_sigma`: per-sample combined absolute 1-sigma uncertainty in normalized-flux units: shot, readout, and correlated components added in quadrature.

## JSON sidecar

The JSON sidecar records the model, seed, observer, orbit, retained pass, attitude/precession, Blender version/device/render settings, sampled model scale factor, final dimensions, eclipse fraction, photometric filter selection (`photometry.filter`), noise and sensor-response parameters, and limitations.

## Interpretation caveats

These values are a rendering-based relative-flux proxy, not calibrated magnitude or absolute photometry. Models without `dimensions_m` in `models/model_shapes.json` are assumed to have correct native physical dimensions; material reflectance remains uncalibrated. Other limitations include no atmosphere, uniform scaling of the rendered flux by the visible solar-disk fraction in penumbra, circular two-body orbits, and a simplified Earth-orientation model. Per-model physical dimensions still need to be supplied and validated for calibrated assets.
