from dataclasses import replace
import sys

import scripts.generate_dataset as generate_dataset
from blender_synth_lc.config import PROJECT_ROOT, load_config
from blender_synth_lc.jobs import record_completed_curve


def test_dataset_runner_resumes_and_force_indexes_restarts(tmp_path, monkeypatch):
    model = tmp_path / "model.blend"
    model.touch()
    blender = tmp_path / "blender"
    blender.touch()
    config = load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset")
    config = replace(
        config,
        blender=blender,
        models_dir=tmp_path,
        output_dir=tmp_path / "dataset",
        count=3,
        device="cpu",
    )
    commands = []

    monkeypatch.setattr(generate_dataset, "load_config", lambda *args, **kwargs: config)
    monkeypatch.setattr(
        generate_dataset, "apply_overrides", lambda config, **kwargs: config
    )
    monkeypatch.setattr(generate_dataset, "usable_models", lambda config: (model,))
    monkeypatch.setattr(generate_dataset, "find_empty_meshes", lambda *args: ())

    def fake_blender_command(config, model, **kwargs):
        command = {"config": config, "model": model, **kwargs}
        commands.append(command)
        return command

    def fake_run_blender(command):
        for curve_index in range(command["count"]):
            if curve_index not in command["skip_indices"]:
                record_completed_curve(
                    command["index_file"],
                    command["index_run_key"],
                    command["model"],
                    curve_index,
                )
        return 0

    monkeypatch.setattr(generate_dataset, "blender_command", fake_blender_command)
    monkeypatch.setattr(generate_dataset, "run_blender", fake_run_blender)

    monkeypatch.setattr(sys, "argv", ["generate_dataset.py", "--config", "dataset.ini"])
    assert generate_dataset.main() == 0
    assert commands[0]["skip_indices"] == ()

    assert generate_dataset.main() == 0
    assert len(commands) == 1

    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_dataset.py", "--config", "dataset.ini", "--force_indexes"],
    )
    assert generate_dataset.main() == 0
    assert len(commands) == 2
    assert commands[1]["skip_indices"] == ()