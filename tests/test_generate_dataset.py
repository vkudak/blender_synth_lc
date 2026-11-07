from dataclasses import replace
import sys

import scripts.generate_dataset as generate_dataset
from blender_synth_lc.config import PROJECT_ROOT, load_config
from blender_synth_lc.jobs import record_completed_curve


def test_distribute_curve_counts_is_even_and_totals_exactly():
    counts = generate_dataset.distribute_curve_counts(10_000, 11)

    assert sum(counts) == 10_000
    assert max(counts) - min(counts) == 1
    assert counts == (910,) + (909,) * 10


def test_distribute_curve_counts_requires_at_least_one_per_model():
    try:
        generate_dataset.distribute_curve_counts(2, 3)
    except ValueError as error:
        assert "at least the number of selected models" in str(error)
    else:
        raise AssertionError("Expected ValueError when curves cannot cover all models")


def test_dataset_runner_passes_even_total_allocation_to_models(tmp_path, monkeypatch):
    models = tuple(tmp_path / f"model_{index}.blend" for index in range(3))
    for model in models:
        model.touch()
    blender = tmp_path / "blender"
    blender.touch()
    config = load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset")
    config = replace(
        config,
        blender=blender,
        models_dir=tmp_path,
        output_dir=tmp_path / "dataset",
        count=10,
        device="cpu",
    )
    allocated_counts = []

    monkeypatch.setattr(generate_dataset, "load_config", lambda *args, **kwargs: config)
    monkeypatch.setattr(
        generate_dataset, "apply_overrides", lambda config, **kwargs: config
    )
    monkeypatch.setattr(generate_dataset, "usable_models", lambda config: models)
    monkeypatch.setattr(generate_dataset, "find_empty_meshes", lambda *args: ())
    monkeypatch.setattr(
        generate_dataset,
        "blender_command",
        lambda config, model, **kwargs: allocated_counts.append(kwargs["count"]) or [],
    )
    monkeypatch.setattr(generate_dataset, "run_blender", lambda command: 0)
    monkeypatch.setattr(
        sys,
        "argv",
        ["generate_dataset.py", "--config", "dataset.ini", "--total-curves", "10"],
    )

    assert generate_dataset.main() == 0
    assert allocated_counts == [4, 3, 3]


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