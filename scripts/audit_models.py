import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INVENTORY_SCRIPT = Path(__file__).with_name("inspect_blend.py")
SUPPORTED_BLENDER_MINOR = "4.5."


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Inventory Blender model assets with Blender 4.5 LTS."
    )
    parser.add_argument(
        "--blender",
        default=os.environ.get("BLENDER_BIN") or shutil.which("blender"),
        help="Blender 4.5 LTS executable (or set BLENDER_BIN).",
    )
    parser.add_argument(
        "--models",
        type=Path,
        default=PROJECT_ROOT / "models",
        help="Directory containing .blend assets.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "reports" / "model_inventory.json",
        help="Path for the combined JSON report.",
    )
    return parser.parse_args()


def run_command(command):
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )


def main():
    args = parse_arguments()
    if not args.blender:
        print("Blender executable not found; pass --blender or set BLENDER_BIN.", file=sys.stderr)
        return 2

    models_dir = args.models.resolve()
    model_files = sorted(models_dir.glob("*.blend"))
    if not model_files:
        print(f"No .blend assets found in {models_dir}.", file=sys.stderr)
        return 2

    version_result = run_command([args.blender, "--version"])
    if version_result.returncode != 0:
        print(version_result.stderr or version_result.stdout, file=sys.stderr)
        return version_result.returncode

    version_line = version_result.stdout.splitlines()[0]
    if not version_line.startswith(f"Blender {SUPPORTED_BLENDER_MINOR}"):
        print(
            f"Expected Blender 4.5 LTS, found {version_line!r}.",
            file=sys.stderr,
        )
        return 2

    assets = []
    failures = 0
    with tempfile.TemporaryDirectory(prefix="blender-model-audit-") as temp_dir:
        for model_file in model_files:
            result_path = Path(temp_dir) / f"{model_file.stem}.json"
            command = [
                args.blender,
                "--background",
                str(model_file),
                "--python",
                str(INVENTORY_SCRIPT),
                "--",
                "--output",
                str(result_path),
            ]
            result = run_command(command)

            if result.returncode == 0 and result_path.is_file():
                asset = json.loads(result_path.read_text(encoding="utf-8"))
                asset["asset"] = str(model_file.relative_to(models_dir))
                empty_meshes = [
                    obj["name"]
                    for obj in asset["objects"]
                    if obj["type"] == "MESH" and not obj["mesh_vertices"]
                ]
                asset["usable_mesh_count"] = sum(
                    obj["type"] == "MESH" and bool(obj["mesh_vertices"])
                    for obj in asset["objects"]
                )
                asset["warnings"] = (
                    [f"Mesh objects without vertices: {', '.join(empty_meshes)}"]
                    if empty_meshes
                    else []
                )
                assets.append(asset)
                bounds = asset["combined_mesh_world_bounds"]
                size_text = (
                    "no mesh bounds"
                    if bounds is None
                    else " x ".join(f"{axis:.4g}" for axis in bounds["size"])
                )
                mesh_count = sum(obj["type"] == "MESH" for obj in asset["objects"])
                status = "WARN" if empty_meshes or not asset["usable_mesh_count"] else "OK  "
                print(
                    f"{status} {model_file.name}: {mesh_count} mesh objects, "
                    f"{asset['usable_mesh_count']} with geometry; world bounds {size_text}"
                )
            else:
                failures += 1
                details = (result.stdout + "\n" + result.stderr).splitlines()
                print(f"FAIL {model_file.name}", file=sys.stderr)
                print("\n".join(details[-12:]), file=sys.stderr)
                assets.append(
                    {
                        "asset": str(model_file.relative_to(models_dir)),
                        "error": "Blender inventory process failed",
                        "returncode": result.returncode,
                    }
                )

    inventory = {
        "schema_version": 1,
        "blender_version": version_line.removeprefix("Blender "),
        "models_directory": str(models_dir),
        "assets": assets,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(inventory, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote inventory for {len(assets)} assets to {args.output}.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())