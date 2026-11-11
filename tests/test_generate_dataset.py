from concurrent.futures import Future
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
    monkeypatch.setattr(
        generate_dataset, "run_blender", lambda command, on_progress=None, log_file=None: 0
    )
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

    def fake_run_blender(command, on_progress=None, log_file=None):
        assert log_file == config.output_dir / "blender.log"
        for curve_index in range(command["count"]):
            if curve_index not in command["skip_indices"]:
                record_completed_curve(
                    command["index_file"],
                    command["index_run_key"],
                    command["model"],
                    curve_index,
                )
                if on_progress is not None:
                    on_progress()
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


def test_curve_progress_recovers_after_truncated_index_tail(tmp_path):
    model = tmp_path / "model.blend"
    model.touch()
    index_file = tmp_path / "dataset" / ".dataset_indexes.jsonl"
    config = load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset")
    run_key = generate_dataset.dataset_run_key(config, model, config.seed)
    record_completed_curve(index_file, run_key, model, 0)
    with index_file.open("a", encoding="utf-8") as journal:
        journal.write('{"version":1,"run_key":')

    class Progress:
        updates = 0

        def update(self):
            self.updates += 1

    progress = Progress()
    update_progress = generate_dataset._curve_progress_callback(
        index_file, run_key, model, 2, (0,), progress
    )
    record_completed_curve(index_file, run_key, model, 1)

    update_progress()

    assert progress.updates == 1


def test_parallel_dataset_runner_updates_progress_for_each_completed_curve(
    tmp_path, monkeypatch
):
    model = tmp_path / "model.blend"
    model.touch()
    blender = tmp_path / "blender"
    blender.touch()
    config = replace(
        load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset"),
        blender=blender,
        models_dir=tmp_path,
        output_dir=tmp_path / "dataset",
        count=3,
        workers=2,
        device="cpu",
    )

    class Progress:
        instance = None

        def __init__(self, *args, **kwargs):
            self.updates = 0
            type(self).instance = self

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def update(self, amount=1):
            self.updates += amount

    class Executor:
        def __init__(self, max_workers):
            assert max_workers == 2

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, worker, worker_config, worker_model, model_index, count, seed, index_file, *args):
            run_key = generate_dataset.dataset_run_key(worker_config, worker_model, seed)
            for curve_index in range(count):
                record_completed_curve(index_file, run_key, worker_model, curve_index)
            future = Future()
            future.set_result((worker_model.name, count, count, 0, True))
            return future

    def wait_for_worker(futures, timeout, return_when):
        assert timeout == 0.2
        assert Progress.instance.updates == 3
        return set(futures), set()

    monkeypatch.setattr(generate_dataset, "load_config", lambda *args, **kwargs: config)
    monkeypatch.setattr(generate_dataset, "apply_overrides", lambda config, **kwargs: config)
    monkeypatch.setattr(generate_dataset, "usable_models", lambda config: (model,))
    monkeypatch.setattr(generate_dataset, "find_empty_meshes", lambda *args: ())
    monkeypatch.setattr(generate_dataset, "tqdm", Progress)
    monkeypatch.setattr(generate_dataset, "ProcessPoolExecutor", Executor)
    monkeypatch.setattr(generate_dataset, "wait", wait_for_worker)
    monkeypatch.setattr(sys, "argv", ["generate_dataset.py", "--config", "dataset.ini"])

    assert generate_dataset.main() == 0
    assert Progress.instance.updates == 3


def test_dataset_runner_logs_both_streams_and_reports_failure(tmp_path, monkeypatch, capfd):
    model = tmp_path / "model.blend"
    model.touch()
    blender = tmp_path / "blender"
    blender.touch()
    config = replace(
        load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset"),
        blender=blender,
        models_dir=tmp_path,
        output_dir=tmp_path / "dataset",
        script_output=tmp_path / "generated.py",
        count=1,
    )
    monkeypatch.setattr(generate_dataset, "load_config", lambda *args, **kwargs: config)
    monkeypatch.setattr(generate_dataset, "apply_overrides", lambda config, **kwargs: config)
    monkeypatch.setattr(generate_dataset, "usable_models", lambda config: (model,))
    monkeypatch.setattr(generate_dataset, "find_empty_meshes", lambda *args: ())
    monkeypatch.setattr(
        generate_dataset,
        "blender_command",
        lambda *args, **kwargs: [
            sys.executable,
            "-c",
            "import sys; print('render stdout'); print('render stderr', file=sys.stderr); sys.exit(3)",
        ],
    )
    monkeypatch.setattr(sys, "argv", ["generate_dataset.py"])

    assert generate_dataset.main() == 1

    log_file = config.output_dir / "blender.log"
    log = log_file.read_text(encoding="utf-8")
    assert "render stdout" in log
    assert "render stderr" in log
    stdout, stderr = capfd.readouterr()
    assert "render stdout" not in stdout.splitlines()
    assert "render stderr" not in stderr.splitlines()
    assert "FAIL model.blend (exit 3)" in stderr
    assert str(log_file) in stderr