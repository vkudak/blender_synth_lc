"""Host-side helpers for launching Blender render jobs."""

from __future__ import annotations

import subprocess
from pathlib import Path

from .config import PROJECT_ROOT, SynthConfig


RENDER_SCRIPT = PROJECT_ROOT / "scripts" / "render_lightcurve.py"


def blender_command(
    config: SynthConfig,
    model: Path,
    *,
    count: int | None = None,
    seed: int | None = None,
    output: Path | None = None,
    output_dir: Path | None = None,
    device: str | None = None,
) -> list[str]:
    if not config.blender.is_file():
        raise FileNotFoundError(f"Blender executable not found: {config.blender}")
    command = [
        str(config.blender),
        "--background",
        str(model),
        "--python",
        str(RENDER_SCRIPT),
        "--",
        "--config",
        str(config.config_path),
        "--kind",
        config.kind,
        "--model",
        str(model),
        "--count",
        str(config.count if count is None else count),
        "--seed",
        str(config.seed if seed is None else seed),
        "--device",
        device or config.device,
    ]
    output_path = config.output if output is None else output
    output_directory = config.output_dir if output_dir is None else output_dir
    if config.kind == "curve" and output_path is not None:
        command.extend(["--output", str(output_path)])
    else:
        command.extend(["--output-dir", str(output_directory)])
    return command


def run_blender(command: list[str]) -> int:
    print(" ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode
