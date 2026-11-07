# Future Plans

Roadmap items for the Blender Synthetic Light Curves project. Items are ordered roughly by priority; statuses are tentative and can change.

## Near Term

- [x] **Physical precession / attitude nutation** — Add Simple spin mode with angle of spin axis, phase and period.
- [x] **Enforce 20° minimum satellite elevation** — The configurable INI mask defaults to 20°. Retain the longest consecutive segment above the mask only when it removes at most 15% of the requested samples; random mode retries rejected candidates and fixed configurations fail clearly. The threshold is validated as finite and within `[0, 90)` before Blender starts.
- [x] **Visible-only sampling cleanup** — Below-mask samples are excluded from CSV rows; retained samples carry visibility/eclipsed flags, and eclipsed rows are documented as zero-flux placeholders.
- [x] **Model scale calibration** — Add optional per-model X/Y/Z target dimensions in meters to `models/model_sizes.json`; absent models retain their native bounds and are assumed correct. Populate calibrated dimensions and validate them against Blender inventory bounds.
- [x] **Empty-geometry model handling** — Inspect selected models before dataset runs; warn and stop if a mesh object has zero vertices so the user can repair or remove the affected model.
- [x] **Earth rotation during pass** — Rotate the observer and local horizon at the sidereal rate, including look angles, pass alignment, rendering, and playback.

## Mid Term

- [x] **Eclipse/shadow refinement** — Use conical umbra/penumbra geometry with finite-Sun-disk illumination, count both shadow states toward the eclipse limit, scale penumbra flux, and report shadow state per sample.
- [ ] **Attitude expansions** — Add tumbling/non-principal-axis rotation modes and configurable attitude quaternion timelines.
- [ ] **GPU batch validation** — Run a full 5–10k curve dataset on available GPU hardware and confirm throughput/reliability.

## Long Term

- [ ] **Hardware-in-the-loop realism** — Sensor response (noise, saturation, detector blur, stray light) and calibrated photometric units instead of linear RGB proxy.
- [ ] **Monochrome sensor and filters** — Integrate linear RGB renders into one sensor-weighted flux per sample with configurable filter responses; treat RGB-based spectral response as approximate until material and sensor spectra are available.
- [ ] **Multi-object scenes** — Handle multiple spacecraft/fragments sharing a render.
- [ ] **CI & reproducibility** — Golden-file regression tests for rendered curves and automated checks of config/schema.
- [ ] **Documentation** — Per-section INI reference and worked examples for custom spin-axis/precession configurations.
