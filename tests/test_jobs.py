from dataclasses import replace

from blender_synth_lc.config import PROJECT_ROOT, load_config
from blender_synth_lc.jobs import RENDER_SCRIPT, blender_command


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
    assert config.satellite_size_m == 4.0
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
    assert "light.location = sun_position - sample_position" in render_source
    assert "scene_units_per_m = 1.0 / args.scene_meters_per_unit" in render_source
    assert 'module_name.startswith("blender_synth_lc.")' in render_source
    assert "runpy" not in render_source
    compile(render_source, str(script_output), "exec")