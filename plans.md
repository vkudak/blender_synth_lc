# Future Plans

Roadmap items for the Blender Synthetic Light Curves project. Items are ordered roughly by priority; statuses are tentative and can change.

## Near Term

- [x] **Physical precession / attitude nutation** — Add Simple spin mode with angle of spin axis, phase and period.
- [x] **Enforce 20° minimum satellite elevation** — The configurable INI mask defaults to 20°. Retain the longest consecutive segment above the mask only when it removes at most 15% of the requested samples; random mode retries rejected candidates and fixed configurations fail clearly. The threshold is validated as finite and within `[0, 90)` before Blender starts.
- [x] **Visible-only sampling cleanup** — Below-mask samples are excluded from CSV rows; retained samples carry visibility/eclipsed flags, and eclipsed rows are documented as zero-flux placeholders.
- [x] **Model scale calibration** — Add optional per-model X/Y/Z target dimensions in meters to `models/model_shapes.json`; models without dimensions retain their native bounds and are assumed correct. Populate calibrated dimensions and validate them against Blender inventory bounds.
- [x] **Empty-geometry model handling** — Inspect selected models before dataset runs; warn and stop if a mesh object has zero vertices so the user can repair or remove the affected model.
- [x] **Earth rotation during pass** — Rotate the observer and local horizon at the sidereal rate, including look angles, pass alignment, rendering, and playback.
- [x] **Progres bar** for dataset script
- [x] **Change RSO scale** from 1 to 1.5
- [x] **Additional features** like phase angle, distance to object, elevation above horizont
- [x] **Add Noise** with respect to the elevation of RSO

## Mid Term

- [x] **Eclipse/shadow refinement** — Use conical umbra/penumbra geometry with finite-Sun-disk illumination, count both shadow states toward the eclipse limit, scale penumbra flux, and report shadow state per sample.
- [x] **Attitude expansions** — Add tumbling/non-principal-axis rotation modes and configurable attitude quaternion timelines.

## Long Term

- [x] **Hardware-in-the-loop realism** — Enhanced sensor response for ML training:
  - Detector bit-depth quantization (e.g., 12-bit or 16-bit ADC)
  - Small baseline offset (detector bias/dark current) per frame
  - Time-correlated noise (AR(1) frame-to-frame correlation for realistic sensor behavior)
  - Elevation-dependent shot noise retained ✓
  - Saturation clipping and readout noise included; cosmic rays intentionally omitted
  - Documented in `docs/SENSOR_NOISE_MODEL.md`
- [x] **Monochrome sensor and filters** — Linear RGB renders are integrated into a single sensor-weighted flux per sample via `[sensor] filter_type` (optional; `none` keeps the current plain `R + G + B` behavior).
  - Filter config: `[sensor] filter_type = none | luminance | johnson_b | johnson_v | johnson_r | custom`
  - RGB weight factors: `rgb_weights = w_R, w_G, w_B` for `custom` (validated, normalized to sum 1.0)
  - Presets: luminance/Johnson V (0.2126, 0.7152, 0.0722), Johnson B (0.10, 0.30, 0.60), Cousins R (0.75, 0.22, 0.03)
  - RGB-based spectral response documented as approximate until material and sensor spectra are available.
- [x] **Documentation** — Per-section INI reference and worked examples for custom spin-axis/precession configurations.
