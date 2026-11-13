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

- [ ] **Hardware-in-the-loop realism** — Enhanced sensor response for ML training:
  - Detector bit-depth quantization (e.g., 12-bit or 16-bit ADC)
  - Small baseline offset (detector bias/dark current) per frame
  - Time-correlated noise (frame-to-frame correlation for realistic sensor behavior)
  - Keep existing elevation-dependent noise ✓
  - Optional: saturation clipping, readout noise, cosmic rays
- [ ] **Monochrome sensor and filters** — Integrate linear RGB renders into single sensor-weighted flux per sample with configurable filter responses (optional; when `filter_type=None`, output flux as current RGB-based behavior).
  - Define filter config: `[sensor] filter_type = V-band | custom | None`
  - RGB weight factors: `rgb_weights = w_R, w_G, w_B` (sum to 1.0)
  - Examples: luminosity (0.21, 0.72, 0.07), equal RGB (0.33, 0.33, 0.33)
  - Treat RGB-based spectral response as approximate until material and sensor spectra available.
- [x] **Documentation** — Per-section INI reference and worked examples for custom spin-axis/precession configurations.
