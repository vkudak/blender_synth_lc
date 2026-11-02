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

Light-curve rendering defaults to `--device auto`, which prefers an enumerated GPU and uses CPU only when Cycles finds no GPU. Explicit options are `--device cuda`, `--device optix`, and `--device cpu`. If a GPU is detected but its render kernel fails to load, Blender reports an error instead of silently shifting a large run to CPU.

The current Quadro P520 is detected by Cycles, but driver 470.256.02 fails to load Blender's `sm_61` CUDA kernel. NVIDIA's CUDA compatibility table gives 525 as the minimum driver branch for CUDA 12.x; Blender 4.5's OptiX path requires driver 535 or newer. A supported 535+ driver is a reasonable next test, but the GPU render must be revalidated after installation.

The current Python core includes WGS-84 ground observer coordinates, circular two-body orbit propagation for altitudes of 300-3000 km, seeded parameter samplers, and visible-pass selection. The pass sampler aligns orbital phase to closest approach, rejects candidates below a configurable elevation mask, and samples the satellite's moving position, velocity, range, azimuth, and elevation over the pass window. Earth rotation is intentionally ignored, so the observer and local horizon remain fixed during each synthetic pass.

Satellite self-rotation is separate from orbital motion. Period 0 means no rotation; rotating periods from 3 through 180 seconds are retained. Positive periods below 3 seconds and periods over 180 seconds are excluded and rejected, not relabeled as static.

Light-curve photometry/rendering, physical-scale calibration, and batch dataset generation are the next implementation stages.
