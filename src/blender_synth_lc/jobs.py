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
    render_args = [
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
        render_args.extend(["--output", str(output_path)])
    else:
        render_args.extend(["--output-dir", str(output_directory)])

    script_path = RENDER_SCRIPT
    script_args = render_args
    if config.script_output is not None:
        script_path = config.script_output
        _write_render_script(script_path, render_args)
        script_args = []

    command = [
        str(config.blender),
        "--background",
        str(model),
        "--python",
        str(script_path),
        "--",
        *script_args,
    ]
    return command


def _write_render_script(path: Path, render_args: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    source = RENDER_SCRIPT.read_text(encoding="utf-8")
    source = source.replace(
        "import sys\n",
        f"import sys\nsys.argv = [{str(path)!r}, '--', *{render_args!r}]\n",
        1,
    )
    source = source.replace(
        "REPO_ROOT = Path(__file__).resolve().parents[1]",
        f"REPO_ROOT = Path({str(PROJECT_ROOT)!r})",
        1,
    )
    path.write_text(source, encoding="utf-8")


def run_blender(command: list[str]) -> int:
    print(" ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode
