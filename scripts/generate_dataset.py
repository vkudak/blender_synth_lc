"""Launch Blender to generate a batch of synthetic light curves from config/dataset.ini."""

import argparse
import json
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

from tqdm import tqdm

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from blender_synth_lc.config import PROJECT_ROOT, apply_overrides, load_config, usable_models
from blender_synth_lc.jobs import (
    blender_command,
    clear_dataset_indexes,
    completed_curve_indices,
    dataset_index_path,
    dataset_run_key,
    find_empty_meshes,
    run_blender,
)


def parse_arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_ROOT / "config" / "dataset.ini",
        help="INI file with dataset settings.",
    )
    parser.add_argument("--model", type=Path, action="append", dest="selected_models")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "optix"))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--total-curves", type=int)
    parser.add_argument(
        "--workers",
        type=int,
        help="Number of parallel Blender processes (overrides [dataset] workers from config).",
    )
    parser.add_argument(
        "--force_indexes",
        "--force-indexes",
        action="store_true",
        help="Delete saved dataset indexes and generate all requested curves again.",
    )
    return parser.parse_args()


def distribute_curve_counts(total_curves: int, model_count: int) -> tuple[int, ...]:
    if model_count < 1:
        raise ValueError("At least one model is required")
    if total_curves < model_count:
        raise ValueError("total_curves must be at least the number of selected models")
    curves_per_model, remainder = divmod(total_curves, model_count)
    return tuple(
        curves_per_model + (model_index < remainder)
        for model_index in range(model_count)
    )


def _run_model_batch(
    config,
    model,
    model_index,
    model_count,
    seed,
    index_file,
    output_dir,
    device,
    log_file,
):
    """Worker function to process one model batch. Called by multiprocessing."""
    model_seed = seed + 10_000 * model_index
    run_key = dataset_run_key(config, model, model_seed)
    completed = completed_curve_indices(index_file, run_key, model)
    skip_indices = tuple(
        curve_index for curve_index in completed if curve_index < model_count
    )

    if len(skip_indices) == model_count:
        return (model.name, model_count, 0, 0, True)

    returncode = run_blender(
        blender_command(
            config,
            model,
            count=model_count,
            seed=model_seed,
            output_dir=output_dir,
            device=device,
            skip_indices=skip_indices,
            index_file=index_file,
            index_run_key=run_key,
        ),
        on_progress=None,
        log_file=log_file,
    )

    completed_after = completed_curve_indices(index_file, run_key, model)
    newly_completed = len([i for i in completed_after if i not in completed])

    return (model.name, model_count, newly_completed, returncode, returncode == 0)


def _curve_progress_callback(
    index_file, run_key, model, curve_count, completed_indices, progress
):
    offset = index_file.stat().st_size if index_file.exists() else 0
    pending = b""
    model_path = str(model.resolve())
    seen_indices = set(completed_indices)

    def update():
        nonlocal offset, pending
        if not index_file.exists():
            return
        with index_file.open("rb") as journal:
            journal.seek(offset)
            appended = journal.read()
            offset = journal.tell()
        if not appended:
            return
        lines = (pending + appended).split(b"\n")
        pending = lines.pop()
        for line in lines:
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                for curve_index in completed_curve_indices(index_file, run_key, model):
                    if curve_index < curve_count and curve_index not in seen_indices:
                        seen_indices.add(curve_index)
                        progress.update()
                with index_file.open("rb") as journal:
                    journal.seek(0, 2)
                    offset = journal.tell()
                pending = b""
                return
            if record.get("run_key") == run_key and record.get("model") == model_path:
                curve_index = record.get("curve_index")
                if (
                    type(curve_index) is int
                    and 0 <= curve_index < curve_count
                    and curve_index not in seen_indices
                ):
                    seen_indices.add(curve_index)
                    progress.update()

    return update


def main():
    args = parse_arguments()
    config = load_config(args.config, kind="dataset")
    selected = tuple(str(path) for path in args.selected_models) if args.selected_models else None
    output_dir = args.output_dir.resolve() if args.output_dir is not None else None
    config = apply_overrides(
        config,
        selected_models=selected,
        output_dir=output_dir,
        device=args.device,
        seed=args.seed,
        count=args.total_curves,
        workers=args.workers,
    )
    models = usable_models(config)
    try:
        curve_counts = distribute_curve_counts(config.count, len(models))
    except ValueError as error:
        print(f"WARNING: Dataset generation stopped: {error}", file=sys.stderr)
        return 1
    try:
        empty_mesh_models = find_empty_meshes(config.blender, models)
    except (OSError, RuntimeError, ValueError, KeyError) as error:
        print(f"WARNING: Dataset generation stopped; model validation failed: {error}", file=sys.stderr)
        return 1
    if empty_mesh_models:
        for model, object_names in empty_mesh_models:
            print(
                f"WARNING: {model.name} contains empty mesh object(s): "
                f"{', '.join(object_names)}",
                file=sys.stderr,
            )
        print(
            "Dataset generation stopped. Repair or remove the affected model(s).",
            file=sys.stderr,
        )
        return 1

    config.output_dir.mkdir(parents=True, exist_ok=True)
    index_file = dataset_index_path(config.output_dir)
    blender_log = config.output_dir / "blender.log"
    if args.force_indexes:
        clear_dataset_indexes(index_file)
        print(f"Cleared dataset indexes: {index_file}")

    print(f"Blender logs will be saved to: {blender_log}")
    print(f"Running with {config.workers} parallel worker(s)")

    failures = 0
    with tqdm(total=config.count, desc="Dataset", unit="curve", file=sys.stderr) as progress:
        if config.workers == 1:
            for model_index, (model, model_count) in enumerate(zip(models, curve_counts)):
                progress.set_postfix_str(f"{model.name}: {model_count} curves", refresh=True)
                model_seed = config.seed + 10_000 * model_index
                run_key = dataset_run_key(config, model, model_seed)
                completed = completed_curve_indices(index_file, run_key, model)
                skip_indices = tuple(
                    curve_index for curve_index in completed if curve_index < model_count
                )
                progress.update(len(skip_indices))
                if len(skip_indices) == model_count:
                    print(f"SKIP {model.name}: all {model_count} curve indexes are complete")
                    continue
                returncode = run_blender(
                    blender_command(
                        config,
                        model,
                        count=model_count,
                        seed=model_seed,
                        output_dir=config.output_dir,
                        device=config.device,
                        skip_indices=skip_indices,
                        index_file=index_file,
                        index_run_key=run_key,
                    ),
                    on_progress=_curve_progress_callback(
                        index_file,
                        run_key,
                        model,
                        model_count,
                        skip_indices,
                        progress,
                    ),
                    log_file=blender_log,
                )
                if returncode != 0:
                    failures += 1
                    print(
                        f"FAIL {model.name} (exit {returncode}); see {blender_log}",
                        file=sys.stderr,
                    )
        else:
            jobs = []
            progress_callbacks = []
            for model_index, (model, model_count) in enumerate(zip(models, curve_counts)):
                model_seed = config.seed + 10_000 * model_index
                run_key = dataset_run_key(config, model, model_seed)
                completed = completed_curve_indices(index_file, run_key, model)
                skip_indices = tuple(
                    curve_index for curve_index in completed if curve_index < model_count
                )
                progress.update(len(skip_indices))
                if len(skip_indices) == model_count:
                    print(f"SKIP {model.name}: all {model_count} curve indexes are complete")
                    continue
                jobs.append((model_index, model, model_count))
                progress_callbacks.append(
                    _curve_progress_callback(
                        index_file,
                        run_key,
                        model,
                        model_count,
                        skip_indices,
                        progress,
                    )
                )

            with ProcessPoolExecutor(max_workers=config.workers) as executor:
                futures = {}
                for model_index, model, model_count in jobs:
                    future = executor.submit(
                        _run_model_batch,
                        config,
                        model,
                        model_index,
                        model_count,
                        config.seed,
                        index_file,
                        config.output_dir,
                        config.device,
                        blender_log,
                    )
                    futures[future] = (model_index, model.name, model_count)

                while futures:
                    for update_progress in progress_callbacks:
                        update_progress()
                    completed_futures, _ = wait(
                        futures,
                        timeout=0.2,
                        return_when=FIRST_COMPLETED,
                    )
                    for future in completed_futures:
                        model_index, model_name, model_count = futures.pop(future)
                        try:
                            model_name, requested_count, completed_count, returncode, success = future.result()
                            if success and returncode == 0:
                                print(f"DONE {model_name}: completed {completed_count} curves")
                            else:
                                failures += 1
                                print(f"FAIL {model_name} (exit {returncode}); see {blender_log}", file=sys.stderr)
                        except Exception as error:
                            failures += 1
                            print(f"ERROR in worker for {model_name}: {error}", file=sys.stderr)
                for update_progress in progress_callbacks:
                    update_progress()

    if failures:
        print(f"Completed with {failures} failed model runs.", file=sys.stderr)
        return 1
    print(
        f"Dataset indexes are up to date for {config.count} curves across "
        f"{len(models)} models in {config.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
