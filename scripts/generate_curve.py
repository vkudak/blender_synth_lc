"""Launch Blender to render one synthetic light curve from config/curve.ini."""

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
        default=PROJECT_ROOT / "config" / "curve.ini",
        help="INI file with single-curve settings.",
    )
    parser.add_argument("--model", type=Path, help="Override paths.model from the INI file.")
    parser.add_argument("--output", type=Path, help="Override paths.output from the INI file.")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "optix"))
    parser.add_argument("--seed", type=int)
    return parser.parse_args()


def main():
    args = parse_arguments()
    config = load_config(args.config, kind="curve")
    model = args.model.resolve() if args.model is not None else None
    output = args.output.resolve() if args.output is not None else None
    config = apply_overrides(
        config,
        model=model,
        output=output,
        device=args.device,
        seed=args.seed,
        count=1,
    )
    models = usable_models(config)
    returncode = run_blender(
        blender_command(
            config,
            models[0],
            count=1,
            seed=config.seed,
            output=config.output,
            device=config.device,
        )
    )
    if returncode != 0:
        print(f"Curve render failed (exit {returncode})", file=sys.stderr)
    return returncode


if __name__ == "__main__":
    raise SystemExit(main())
