# Multiprocessing Implementation for Dataset Generation

## Overview

The dataset generation script now supports parallel Blender process execution to accelerate rendering of synthetic light curves. This implementation uses Python's `concurrent.futures.ProcessPoolExecutor` to manage multiple worker processes.

## Changes Made

### 1. Modified `src/blender_synth_lc/config.py`

#### Added to SynthConfig dataclass
- `workers: int` field to store the number of parallel workers

#### Enhanced `load_config()` function
- Reads `[dataset] workers` parameter (default 1, only for dataset configs)
- Validates that `workers >= 1`
- Passes `workers` to SynthConfig constructor

### 2. Modified `scripts/generate_dataset.py`

#### Updated `parse_arguments()`
- Changed `--workers` to be optional (no default value)
- Allows command-line override of config value
- Help text indicates it overrides `[dataset] workers` from config

#### Enhanced `main()` function
- Calls `apply_overrides()` with `workers=args.workers` (may be None)
- Uses `config.workers` instead of `args.workers` throughout
- Config value takes precedence if CLI option not provided

### 3. Updated configuration files

#### `config/dataset.ini`
- Added `workers = 1` to `[dataset]` section (with Ukrainian comment)
- Default value 1 maintains backward compatibility

#### `config/curve.ini`
- No changes (single-curve rendering doesn't use workers)

### 2. Key Design Decisions

#### Process Safety
- **Shared Index File**: All workers coordinate through a single `.dataset_indexes.jsonl` file
- **Atomic Writes**: Each worker uses `fsync()` to ensure index records persist immediately
- **Skip Indices**: Completed curves are tracked per run_key, allowing safe resumption

#### Backward Compatibility
- Default `--workers=1` maintains sequential behavior
- All existing command-line options work unchanged
- Resumption logic unchanged (based on index file)

#### Progress Tracking
- The parent process polls the shared index journal while workers run
- The progress bar updates as each curve is recorded, not only when a worker finishes
- Previously completed curves are counted before new jobs are submitted

## Usage

### Configuration File Setup

Edit `config/dataset.ini`:
```ini
[dataset]
workers = 4
total_curves = 10000
```

Then run without `--workers` (uses config value):
```bash
.venv/bin/python scripts/generate_dataset.py --config config/dataset.ini
```

### Command-Line Override

Override config file value with `--workers`:
```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --workers 2  # overrides [dataset] workers = 4 from config
```

### Configuration Priority

1. **CLI `--workers` flag**: Highest priority (if provided)
2. **Config file `[dataset] workers`**: Used if CLI flag not provided
3. **Default value**: 1 (sequential processing)

### Sequential (Single Worker, default)
```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 1000 \
  --device cuda
```

### Parallel (via config file)
```ini
; config/dataset.ini
[dataset]
workers = 4
total_curves = 4000
```

```bash
.venv/bin/python scripts/generate_dataset.py --config config/dataset.ini
```

### Parallel (via CLI override)
```bash
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 4000 \
  --workers 4 \
  --device cuda
```

## Performance Considerations

### Memory Usage
- Each Blender process requires ~2-4 GB of memory (varies by model complexity and resolution)
- Total memory needed: `workers * 3GB` (approximate)
- Example: 4 workers × 3 GB ≈ 12 GB required

### GPU Memory
- CUDA rendering with multiple workers requires sufficient GPU memory
- Monitor GPU usage with `nvidia-smi` (on NVIDIA systems)
- Reduce worker count if out-of-memory errors occur

### Recommended Worker Counts
- **CPU Rendering**: 2-3 workers (depends on core count)
- **GPU Rendering (CUDA)**: 3-4 workers (depends on GPU memory)
- **Test System**: Start with `--workers=2` and scale up

## Resumption

The parallel implementation fully supports resumption:

```bash
# First run: interrupted after some curves
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 10000 \
  --workers 4 \
  --device cuda

# Resume later: automatically skips completed curves
.venv/bin/python scripts/generate_dataset.py \
  --config config/dataset.ini \
  --total-curves 10000 \
  --workers 4 \
  --device cuda
```

Completed curve indices are stored in `.dataset_indexes.jsonl`, allowing safe resumption regardless of worker count changes.

## Testing

All existing tests pass:
- `test_distribute_curve_counts_*`: Ensures fair curve distribution
- `test_dataset_runner_*`: Validates runner behavior
- `test_curve_progress_*`: Confirms progress tracking

Run tests:
```bash
.venv/bin/python -m pytest tests/test_generate_dataset.py -v
```

## Implementation Details

### Worker Function Signature
```python
def _run_model_batch(
    config,           # Full SynthConfig object
    model,            # Path to .blend file
    model_index,      # Index in models list (for seed offset)
    model_count,      # Number of curves to generate for this model
    seed,             # Base seed
    index_file,       # Path to .dataset_indexes.jsonl
    output_dir,       # Output directory for curves
    device,           # Rendering device
    log_file,         # Shared log file for Blender output
) -> tuple:
    # Returns: (model_name, requested_count, newly_completed, returncode, success)
```

### Process Execution Flow

```
1. Parse arguments and load config
2. Validate models and check for empty meshes
3. Distribute curves evenly across models
4. If --workers == 1:
   - Use original sequential loop (with progress callback)
5. Else:
   - Create ProcessPoolExecutor with N workers
   - Submit all (model, count) tuples to workers
   - Poll the shared index journal while waiting for worker completion
   - Update progress for each newly recorded curve
   - Aggregate failures
6. Report results
```

## Limitations and Future Work

1. **Worker Count**: Limited by available system resources (memory, CPU cores, GPU memory)
2. **Model Validation**: Still runs sequentially before rendering (could be parallelized)

## Debugging

If workers fail silently:

1. Check `blender.log` for errors
2. Monitor system resources: `nvidia-smi` (GPU), `top` (CPU/memory)
3. Try with fewer workers: `--workers 2`
4. Enable subprocess output in the worker function for debugging

## References

- Python `concurrent.futures` documentation
- Blender 4.5 background rendering documentation
- `src/blender_synth_lc/jobs.py`: Core Blender execution logic
- [Parallel generation guide](PARALLEL_GENERATION_GUIDE.md)
