"""Launch Blender to generate a batch of synthetic light curves from config/dataset.ini."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from blender_synth_lc.config import PROJECT_ROOT, apply_overrides, load_config, usable_models
from blender_synth_lc.jobs import blender_command, run_blender


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
    parser.add_argument("--curves-per-model", type=int)
    return parser.parse_args()


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
        count=args.curves_per_model,
    )
    models = usable_models(config)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    failures = 0
    for model_index, model in enumerate(models):
        returncode = run_blender(
            blender_command(
                config,
                model,
                count=config.count,
                seed=config.seed + 10_000 * model_index,
                output_dir=config.output_dir,
                device=config.device,
            )
        )
        if returncode != 0:
            failures += 1
            print(f"FAIL {model.name} (exit {returncode})", file=sys.stderr)

    if failures:
        print(f"Completed with {failures} failed model runs.", file=sys.stderr)
        return 1
    print(f"Wrote curves for {len(models)} models to {config.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
