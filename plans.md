# Future Plans

Roadmap items for the Blender Synthetic Light Curves project. Items are ordered roughly by priority; statuses are tentative and can change.

## Near Term

- [ ] **Object (satellite) precession / attitude nutation** — Add physical precession of the rotating body (e.g., torque-free precession of an asymmetric rigid body and/or gyroscopic effects) on top of the current constant spin-axis model. Keep the existing simple spin mode as a fallback and gate precession behind configuration so existing seeds stay reproducible.
- [ ] **Enforce 20° minimum object elevation** — Verify the rendered object is above a 20° elevation mask throughout (or at the start of) each pass and reject/regenerate passes whose object falls below it. Expose the threshold via INI/config instead of hard-coding.
- [ ] **Visible-only sampling cleanup** — Mark/flag samples where the object is below the mask or in Earth shadow consistently in CSV sidecars; document which rows are physically excluded vs. zero-flux placeholders.
- [ ] **Model scale calibration** — Establish real-world physical scale for `.blend` assets (meters) and validate bounds in `reports/model_inventory.json`.
- [ ] **Empty-geometry model handling** — Exclude or repair `Topex_g.blend`, `Topex_g3.blend`, and the empty mesh in `Topex_g5_spb3.blend` in dataset runs.

## Mid Term

- [ ] **Earth rotation during pass** — Remove the “observer and horizon fixed” simplification; propagate observer ECEF position with Earth rotation and update look angles accordingly.
- [ ] **Eclipse/shadow refinement** — Replace the cylindrical Earth-shadow approximation with a conical shadow (umbra/penumbra) and report shadow state per sample.
- [ ] **Non-circular orbits** — Support elliptical (Keplerian) orbits and perigee/apogee sampling.
- [ ] **Attitude expansions** — Add tumbling/non-principal-axis rotation modes and configurable attitude quaternion timelines.
- [ ] **GPU batch validation** — Run a full 5–10k curve dataset on available GPU hardware and confirm throughput/reliability.

## Long Term

- [ ] **Hardware-in-the-loop realism** — Sensor response (noise, saturation, detector blur, stray light) and calibrated photometric units instead of linear RGB proxy.
- [ ] **Multi-object scenes** — Handle multiple spacecraft/fragments sharing a render.
- [ ] **CI & reproducibility** — Golden-file regression tests for rendered curves and automated checks of config/schema.
- [ ] **Documentation** — Per-section INI reference and worked examples for custom spin-axis/precession configurations.
