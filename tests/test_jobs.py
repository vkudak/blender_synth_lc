from dataclasses import replace
import json
from pathlib import Path

import blender_synth_lc.jobs as jobs

from blender_synth_lc.config import PROJECT_ROOT, load_config
from blender_synth_lc.jobs import (
    RENDER_SCRIPT,
    blender_command,
    clear_dataset_indexes,
    completed_curve_indices,
    dataset_index_path,
    dataset_run_key,
    find_empty_meshes,
    record_completed_curve,
)


def test_find_empty_meshes_reports_empty_objects_for_all_selected_models(
    tmp_path, monkeypatch
):
    first_model = tmp_path / "first.blend"
    second_model = tmp_path / "second.blend"
    inspected_models = []

    def fake_run(command, **kwargs):
        model = Path(command[2])
        inspected_models.append(model)
        output_path = Path(command[command.index("--output") + 1])
        objects = (
            [{"name": "EmptyPanel", "type": "MESH", "mesh_vertices": 0}]
            if model == first_model
            else [{"name": "Body", "type": "MESH", "mesh_vertices": 12}]
        )
        output_path.write_text(json.dumps({"objects": objects}), encoding="utf-8")
        return jobs.subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(jobs.subprocess, "run", fake_run)

    invalid_models = find_empty_meshes(Path("/blender"), (first_model, second_model))

    assert inspected_models == [first_model, second_model]
    assert invalid_models == ((first_model, ("EmptyPanel",)),)


def test_blender_command_saves_and_uses_configured_runner(tmp_path):
    config_text = (PROJECT_ROOT / "config" / "curve.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "curve.ini"
    script_output = tmp_path / "generated" / "curve_runner.py"
    config_path.write_text(
        config_text.replace("script_output =", f"script_output = {script_output}"),
        encoding="utf-8",
    )
    config = load_config(config_path, kind="curve")
    assert config.scene_meters_per_unit == 1.0
    assert config.sun_energy == 1361.0
    assert config.max_eclipse_fraction == 0.15
    assert config.exposure == -8.8
    blender = tmp_path / "blender"
    blender.touch()
    config = replace(config, blender=blender)

    command = blender_command(config, config.model)

    assert command[command.index("--python") + 1] == str(script_output)
    assert command[-1] == "--"
    render_source = script_output.read_text(encoding="utf-8")
    assert f"sys.argv = [{str(script_output)!r}, '--', *[" in render_source
    assert str(config.model) in render_source
    assert "def parent_meshes_to_root(" in render_source
    assert "def add_camera_and_sun(" in render_source
    assert 'camera.constraints.new(type="TRACK_TO")' in render_source
    assert "track_constraint.target = target_object" in render_source
    assert 'track_constraint.track_axis = "TRACK_NEGATIVE_Z"' in render_source
    assert 'track_constraint.up_axis = "UP_Y"' in render_source
    assert 'camera_data.ortho_scale = camera_distance * 1.3' in render_source
    assert 'scene.cycles.use_denoising = True' in render_source
    assert 'scene.view_settings.view_transform = "AgX"' in render_source
    assert 'satellite_root.keyframe_insert(data_path="rotation_quaternion", frame=frame)' in render_source
    assert 'if args.script_output is not None and not bpy.app.background:' in render_source
    assert 'satellite_root.location = (0.0, 0.0, 0.0)' in render_source
    assert 'observer_marker.location = observer_position - sample_position' in render_source
    assert "if actual_eclipse_fraction > args.max_eclipse_fraction:" in render_source
    assert 'area.spaces.active.region_3d.view_perspective = "CAMERA"' in render_source
    assert "bmesh.ops.create_uvsphere(" in render_source
    assert "bpy.context.object" not in render_source
    assert "scene.unit_settings.scale_length = args.scene_meters_per_unit" in render_source
    assert 'load_model_shapes(REPO_ROOT / "models" / "model_shapes.json")' in render_source
    assert "args.satellite_size_m" not in render_source
    assert "light.location = sun_position - sample_position" in render_source
    assert "scene_units_per_m = 1.0 / args.scene_meters_per_unit" in render_source
    assert 'module_name.startswith("blender_synth_lc.")' in render_source
    assert "runpy" not in render_source
    compile(render_source, str(script_output), "exec")


def test_dataset_indexes_record_completed_curves_and_can_be_cleared(tmp_path):
    model = tmp_path / "model.blend"
    model.touch()
    output_dir = tmp_path / "dataset"
    index_file = dataset_index_path(output_dir)
    config = load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset")
    run_key = dataset_run_key(config, model, config.seed)

    record_completed_curve(index_file, run_key, model, 2)
    record_completed_curve(index_file, run_key, model, 0)
    record_completed_curve(index_file, run_key, model, 2)

    assert completed_curve_indices(index_file, run_key, model) == (0, 2)

    clear_dataset_indexes(index_file)

    assert completed_curve_indices(index_file, run_key, model) == ()


def test_dataset_index_recovers_from_a_truncated_last_record(tmp_path):
    model = tmp_path / "model.blend"
    model.touch()
    index_file = dataset_index_path(tmp_path / "dataset")
    config = load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset")
    run_key = dataset_run_key(config, model, config.seed)
    record_completed_curve(index_file, run_key, model, 0)
    with index_file.open("a", encoding="utf-8") as output:
        output.write('{"version":1,"run_key":')

    assert completed_curve_indices(index_file, run_key, model) == (0,)

    record_completed_curve(index_file, run_key, model, 1)

    assert completed_curve_indices(index_file, run_key, model) == (0, 1)


def test_dataset_run_key_ignores_requested_count_but_tracks_settings(tmp_path):
    model = tmp_path / "model.blend"
    model.touch()
    config = load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset")
    changed_count = replace(config, count=config.count + 1)
    changed_device = replace(config, device="cpu")
    changed_precession_fraction = replace(config, precession_fraction=1.0)

    assert dataset_run_key(config, model, config.seed) == dataset_run_key(
        changed_count, model, config.seed
    )
    assert dataset_run_key(config, model, config.seed) != dataset_run_key(
        changed_device, model, config.seed
    )
    assert dataset_run_key(config, model, config.seed) != dataset_run_key(
        changed_precession_fraction, model, config.seed
    )