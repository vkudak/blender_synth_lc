# Parallel Dataset Generation Guide

## Quick Start

To enable parallel generation, either:

### Option 1: Edit config file

Edit `config/dataset.ini`:
```ini
[dataset]
workers = 4
```

Then run:
```bash
.venv/bin/python scripts/generate_dataset.py --config config/dataset.ini
```

### Option 2: Use command-line override

```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 10000 \
  --workers 4 \
  --device cuda
```

**Windows PowerShell:**
```powershell
.venv\Scripts\python scripts/generate_dataset.py `
  --config config/dataset.ini `
  --total-curves 10000 `
  --workers 4 `
  --device cuda
```

## What is Parallel Generation?

Instead of rendering curves one Blender process at a time (sequential), the parallel mode launches multiple Blender instances simultaneously. Each process renders curves independently, drastically reducing total generation time.

**Sequential (1 worker):** Process models one at a time
```
Model A (0-1000 curves): ============================================ 1h
Model B (0-1000 curves):                                             ============================================ 1h
Total time: ~2 hours
```

**Parallel (4 workers):** Process multiple models simultaneously
```
Worker 1 → Model A (0-250 curves): ==============
Worker 2 → Model B (0-250 curves): ==============
Worker 3 → Model A (250-500): ==================
Worker 4 → Model B (250-500): ==================
Total time: ~30 minutes
```

## Recommended Settings

### For CUDA (GPU) Rendering

**Desktop/Workstation (8-16 GB GPU VRAM):**
```bash
--workers 3 --device cuda
```

**High-end GPU (24+ GB VRAM):**
```bash
--workers 4 --device cuda
```

**Limited GPU Memory (4-8 GB):**
```bash
--workers 2 --device cuda
```

### For CPU Rendering

**8-core CPU:**
```bash
--workers 2 --device cpu
```

**16-core CPU:**
```bash
--workers 4 --device cpu
```

**Note:** CPU rendering is much slower; use GPU when possible.

## Monitoring Progress

### Linux/Mac
Monitor memory and GPU usage:
```bash
watch -n 1 'nvidia-smi'  # GPU
top -p $(pgrep -f blender | tr '\n' ',')  # CPU/Memory
```

### Windows PowerShell
Monitor GPU:
```powershell
Watch-Output nvidia-smi
```

Monitor system resources:
```powershell
Get-Process blender | Select-Object -Property ProcessName, CPU, Memory
```

Monitor Blender output log:
```powershell
Get-Content reports\dataset\blender.log -Wait -Tail 50
```

## Managing Large Datasets

### Generating 100,000 curves
```bash
# Estimate: 25 hours with 4 workers
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 100000 \
  --workers 4 \
  --device cuda
```

If interrupted, simply re-run the **exact same command** to resume from where it stopped. The system automatically skips completed curves.

### Generating curves for multiple models
```bash
# Distribute 8000 curves across 4 models (2000 each)
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --model Model_A.blend \
  --model Model_B.blend \
  --model Model_C.blend \
  --model Model_D.blend \
  --total-curves 8000 \
  --workers 4 \
  --device cuda
```

## Troubleshooting

### Out of Memory Error
**Problem:** Worker processes crash with OOM
**Solution:** Reduce worker count
```bash
--workers 2  # instead of 4
```

### GPU Out of Memory
**Problem:** CUDA errors during rendering
**Solution:** Reduce workers or switch to CPU
```bash
--workers 2 --device cuda  # or --device cpu
```

### Slow Progress
**Problem:** Only one Blender process appears to be running
**Solution:** Check system resources and verify workers actually started
```bash
# Check for blender processes (Linux/Mac)
ps aux | grep blender

# Check for blender processes (Windows PowerShell)
Get-Process | Select-String blender
```

### Partial Results After Crash
**Solution:** The system is designed to handle this! Re-run the command:
```bash
# Re-run same command - will skip completed curves
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 10000 \
  --workers 4 \
  --device cuda
```

Completed curves are tracked in `.dataset_indexes.jsonl` in your output directory.

## Performance Expectations

### CUDA Rendering Times (approximate)
- **Single Curve (128x128 resolution, 8 samples):** 10-30 seconds
- **1000 Curves / Sequential:** 3-8 hours
- **1000 Curves / 4 Workers:** 45 minutes - 2 hours
- **Speedup:** ~2-4x depending on model complexity

### CPU Rendering Times (approximate)
- **Single Curve:** 2-5 minutes
- **1000 Curves / Sequential:** 33-83 hours
- **1000 Curves / 4 Workers:** 8-20 hours
- **Speedup:** ~3-4x (CPU-bound, linear scaling limited)

## Resuming After Interruption

The parallel generation system is fully resumable:

```bash
# Start generation (interrupted after 2000/10000 curves)
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 10000 \
  --workers 4 \
  --device cuda
# ... Ctrl+C ...

# Resume (will skip 2000 completed curves)
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 10000 \
  --workers 4 \
  --device cuda
```

## Important Notes

1. **Worker Processes are Independent:** Each worker runs its own Blender instance; ensure your system can handle the memory overhead.

2. **Output Coordination:** All workers safely write to shared output directory via atomic index file operations.

3. **Logging:** All Blender output (stdout/stderr) is appended to `blender.log`; check this file for any rendering errors.

4. **Seed Consistency:** Each model gets a consistent seed offset (model_index × 10,000) ensuring reproducibility regardless of worker count.

5. **Progress Tracking:** The progress bar updates as completed curves are recorded in the shared index journal.

## Examples

### Smoke Test (1 curve, 1 worker)
```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --model Lotos_model.blend \
  --total-curves 1 \
  --workers 1 \
  --device cpu
```

### Quick Validation (100 curves, 2 workers)
```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 100 \
  --workers 2 \
  --device cuda
```

### Production Run (50,000 curves, 4 workers)
```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 50000 \
  --workers 4 \
  --device cuda
```

## For More Information

- See [README.md](../README.md) for general dataset generation documentation
- See [MULTIPROCESSING_IMPLEMENTATION.md](MULTIPROCESSING_IMPLEMENTATION.md) for technical implementation details
- See `config/dataset.ini` for all configuration options
