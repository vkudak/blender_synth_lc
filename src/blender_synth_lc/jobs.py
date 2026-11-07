"""Host-side helpers for launching Blender render jobs."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import os
import subprocess
import json
import tempfile
from pathlib import Path

from .config import PROJECT_ROOT, SynthConfig


RENDER_SCRIPT = PROJECT_ROOT / "scripts" / "render_lightcurve.py"
INVENTORY_SCRIPT = PROJECT_ROOT / "scripts" / "inspect_blend.py"
DATASET_INDEX_FILENAME = ".dataset_indexes.jsonl"
DATASET_INDEX_VERSION = 1


def dataset_index_path(output_dir: Path) -> Path:
    return output_dir / DATASET_INDEX_FILENAME


def dataset_run_key(config: SynthConfig, model: Path, seed: int) -> str:
    config_values = asdict(config)
    for key in (
        "config_path",
        "model",
        "selected_models",
        "skip_models",
        "output",
        "output_dir",
        "script_output",
        "count",
    ):
        config_values.pop(key, None)
    model_path = model.resolve()
    model_stat = model_path.stat()
    identity = {
        "config": config_values,
        "model": str(model_path),
        "model_size": model_stat.st_size,
        "model_mtime_ns": model_stat.st_mtime_ns,
        "seed": seed,
    }
    serialized = json.dumps(identity, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def completed_curve_indices(index_path: Path, run_key: str, model: Path) -> tuple[int, ...]:
    indexes = _read_dataset_indexes(index_path)
    model_key = str(model.resolve())
    values = indexes["runs"].get(run_key, {}).get("models", {}).get(model_key, [])
    return tuple(sorted(set(values)))


def record_completed_curve(
    index_path: Path, run_key: str, model: Path, curve_index: int
) -> None:
    if curve_index < 0:
        raise ValueError("curve_index must be non-negative")
    index_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "version": DATASET_INDEX_VERSION,
        "run_key": run_key,
        "model": str(model.resolve()),
        "curve_index": curve_index,
    }
    _truncate_incomplete_index_record(index_path)
    with index_path.open("a", encoding="utf-8") as index_file:
        index_file.write(json.dumps(record, separators=(",", ":")) + "\n")
        index_file.flush()
        os.fsync(index_file.fileno())


def clear_dataset_indexes(index_path: Path) -> None:
    index_path.unlink(missing_ok=True)


def _read_dataset_indexes(index_path: Path) -> dict:
    if not index_path.exists():
        return {"version": DATASET_INDEX_VERSION, "runs": {}}
    try:
        indexes = {"version": DATASET_INDEX_VERSION, "runs": {}}
        with index_path.open(encoding="utf-8") as index_file:
            for line in index_file:
                if not line.endswith("\n"):
                    break
                record = json.loads(line)
                if (
                    not isinstance(record, dict)
                    or record.get("version") != DATASET_INDEX_VERSION
                    or not isinstance(record.get("run_key"), str)
                    or not isinstance(record.get("model"), str)
                    or type(record.get("curve_index")) is not int
                    or record["curve_index"] < 0
                ):
                    raise ValueError("invalid dataset index record")
                models = indexes["runs"].setdefault(record["run_key"], {}).setdefault(
                    "models", {}
                )
                models.setdefault(record["model"], []).append(record["curve_index"])
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(
            f"Could not read dataset index {index_path}; "
            "use --force_indexes to rebuild it"
        ) from error
    return indexes


def _truncate_incomplete_index_record(index_path: Path) -> None:
    if not index_path.exists():
        return
    with index_path.open("r+b") as index_file:
        index_file.seek(0, os.SEEK_END)
        end = index_file.tell()
        if end == 0:
            return
        index_file.seek(-1, os.SEEK_END)
        if index_file.read(1) == b"\n":
            return
        position = end
        while position > 0:
            chunk_size = min(4096, position)
            position -= chunk_size
            index_file.seek(position)
            chunk = index_file.read(chunk_size)
            newline = chunk.rfind(b"\n")
            if newline >= 0:
                index_file.truncate(position + newline + 1)
                return
        index_file.truncate(0)


def find_empty_meshes(
    blender: Path, models: tuple[Path, ...]
) -> tuple[tuple[Path, tuple[str, ...]], ...]:
    empty_mesh_models = []
    with tempfile.TemporaryDirectory(prefix="blender-model-validation-") as temp_dir:
        for index, model in enumerate(models):
            report_path = Path(temp_dir) / f"model-{index}.json"
            result = subprocess.run(
                [
                    str(blender),
                    "--background",
                    str(model),
                    "--python",
                    str(INVENTORY_SCRIPT),
                    "--",
                    "--output",
                    str(report_path),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not report_path.is_file():
                details = (result.stdout + "\n" + result.stderr).splitlines()
                raise RuntimeError(
                    f"Could not validate {model.name}: " + "\n".join(details[-12:])
                )

            report = json.loads(report_path.read_text(encoding="utf-8"))
            empty_meshes = tuple(
                obj["name"]
                for obj in report["objects"]
                if obj["type"] == "MESH" and obj["mesh_vertices"] == 0
            )
            if empty_meshes:
                empty_mesh_models.append((model, empty_meshes))

    return tuple(empty_mesh_models)


def blender_command(
    config: SynthConfig,
    model: Path,
    *,
    count: int | None = None,
    seed: int | None = None,
    output: Path | None = None,
    output_dir: Path | None = None,
    device: str | None = None,
    skip_indices: tuple[int, ...] = (),
    index_file: Path | None = None,
    index_run_key: str | None = None,
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
    for curve_index in skip_indices:
        render_args.extend(["--skip-index", str(curve_index)])
    if index_file is not None:
        if index_run_key is None:
            raise ValueError("index_run_key is required when index_file is set")
        render_args.extend(["--index-file", str(index_file)])
        render_args.extend(["--index-run-key", index_run_key])

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
