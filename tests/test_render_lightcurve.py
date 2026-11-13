import runpy
import sys
from dataclasses import replace
from types import ModuleType, SimpleNamespace

import pytest

from blender_synth_lc.config import PROJECT_ROOT, load_config
from blender_synth_lc.jobs import completed_curve_indices


@pytest.fixture
def renderer(monkeypatch):
    modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "blender_synth_lc" or name.startswith("blender_synth_lc.")
    }
    original_path = sys.path[:]
    monkeypatch.setitem(sys.modules, "bmesh", ModuleType("bmesh"))
    monkeypatch.setitem(sys.modules, "bpy", ModuleType("bpy"))
    mathutils = ModuleType("mathutils")
    mathutils.Quaternion = object
    mathutils.Vector = lambda value: value
    monkeypatch.setitem(sys.modules, "mathutils", mathutils)
    try:
        namespace = runpy.run_path(str(PROJECT_ROOT / "scripts" / "render_lightcurve.py"))
        yield namespace["main"].__globals__
    finally:
        for name in tuple(sys.modules):
            if name == "blender_synth_lc" or name.startswith("blender_synth_lc."):
                del sys.modules[name]
        sys.modules.update(modules)
        sys.path[:] = original_path


@pytest.mark.parametrize("kind", ["curve", "dataset"])
def test_renderer_preserves_runtime_index_arguments(renderer, monkeypatch, tmp_path, kind):
    model = tmp_path / "model.blend"
    model.touch()
    index_file = tmp_path / "indexes.jsonl"
    argv = [
        "render_lightcurve.py", "--", "--config",
        str(PROJECT_ROOT / "config" / f"{kind}.ini"),
        "--kind", kind, "--model", str(model), "--count", "3",
        "--seed", "1", "--device", "cpu",
    ]
    if kind == "dataset":
        argv += [
            "--skip-index", "0", "--skip-index", "2",
            "--index-file", str(index_file), "--index-run-key", "run-key",
        ]
    monkeypatch.setattr(sys, "argv", argv)

    scene = SimpleNamespace(
        unit_settings=SimpleNamespace(),
        cycles=SimpleNamespace(),
        render=SimpleNamespace(),
        view_settings=SimpleNamespace(),
    )
    root = SimpleNamespace(location=(0, 0, 0))
    bpy = SimpleNamespace(
        data=SimpleNamespace(filepath=str(model), objects=SimpleNamespace(remove=lambda *a, **k: None)),
        context=SimpleNamespace(scene=scene),
    )
    written = []
    replacements = {
        "bpy": bpy,
        "load_model_spin_axes": lambda *a: {},
        "load_model_shapes": lambda *a: {},
        "require_model_shape": lambda *a: SimpleNamespace(body_shape=["cube"], solar_panel_count=0),
        "usable_meshes": lambda *a: [object()],
        "hide_existing_lights_and_cameras": lambda *a: None,
        "configure_black_world": lambda *a: None,
        "combined_world_bounds": lambda *a: ((0, 0, 0), 1, (1, 1, 1)),
        "resolve_model_dimensions": lambda *a: ((1, 1, 1), (1, 1, 1), True),
        "parent_meshes_to_root": lambda *a: root,
        "configure_device": lambda *a: {},
        "add_spatial_references": lambda *a: object(),
        "add_camera_and_sun": lambda *a: (object(), object()),
        "build_scenario": lambda *a: {"model_scale_factor": 1},
        "write_curve_files": lambda args, index, *rest: written.append((index, rest[-1])),
    }
    for name, replacement in replacements.items():
        monkeypatch.setitem(renderer, name, replacement)

    renderer["main"]()

    if kind == "dataset":
        assert written == [(1, "run-key")]
        assert completed_curve_indices(index_file, "run-key", model) == (1,)
    else:
        assert written == [(0, None), (1, None), (2, None)]
        assert not index_file.exists()


@pytest.mark.parametrize(
    "extra",
    [
        ["--skip-index", "-1"],
        ["--skip-index", "1"],
        ["--index-file", "indexes.jsonl"],
        ["--index-run-key", "run-key"],
    ],
)
def test_renderer_rejects_invalid_runtime_index_arguments(renderer, monkeypatch, extra):
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "render_lightcurve.py", "--", "--config", "config/dataset.ini",
            "--kind", "dataset", "--model", "model.blend",
            "--count", "1", "--seed", "1", "--device", "cpu", *extra,
        ],
    )
    with pytest.raises(SystemExit) as error:
        renderer["parse_args"]()
    assert error.value.code == 2


def test_tumbling_overrides_static_mode_and_precession(renderer, monkeypatch):
    config = replace(
        load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset"),
        model=PROJECT_ROOT / "models" / "model.blend",
        attitude_mode="static",
        precession_fraction=1.0,
        tumbling_fraction=1.0,
    )
    sample = SimpleNamespace(position_m=(0.0, 0.0, 0.0))
    observer, visible_pass = object(), object()
    for name, replacement in {
        "build_observer": lambda *args: observer,
        "build_visible_pass": lambda *args: visible_pass,
        "sample_pass_window": lambda *args, **kwargs: [sample, sample],
        "select_visible_window": lambda samples: samples,
        "build_sun_direction": lambda *args: (1.0, 0.0, 0.0),
    }.items():
        monkeypatch.setitem(renderer, name, replacement)

    scenario = renderer["build_scenario"](config, 0, {})
    assert scenario == renderer["build_scenario"](config, 0, {})
    assert scenario["tumbling_active"]
    assert scenario["spin_period_s"] == scenario["tumbling_periods_s"][0]
    assert len(scenario["tumbling_periods_s"]) == 3
    assert all(3.0 <= period <= 180.0 for period in scenario["tumbling_periods_s"])
    assert len(scenario["tumbling_phases_rad"]) == 3
    assert not scenario["precession_active"]
    assert scenario["precession_angle_deg"] == 0.0
    assert scenario["precession_period_s"] == 0.0

    static = renderer["build_scenario"](replace(config, tumbling_fraction=0.0), 0, {})
    assert not static["tumbling_active"]
    assert static["spin_period_s"] == 0.0
    assert static["tumbling_periods_s"] == ()

    rotating = renderer["build_scenario"](
        replace(config, attitude_mode="rotating", tumbling_fraction=0.0), 0, {}
    )
    assert rotating["precession_active"]

    one_percent = replace(config, tumbling_fraction=0.01)
    selected = sum(
        renderer["build_scenario"](one_percent, index, {})["tumbling_active"]
        for index in range(10_000)
    )
    assert 70 <= selected <= 130


def test_tumbling_quaternion_is_used_for_renderer_rotation(renderer, monkeypatch):
    class OriginalRotation:
        def __matmul__(self, value):
            return value

    monkeypatch.setitem(renderer, "Quaternion", lambda value: value)
    scenario = {
        "tumbling_active": True,
        "tumbling_periods_s": (4.0, 6.0, 8.0),
        "tumbling_phases_rad": (0.0, 0.0, 0.0),
        "precession_active": True,
    }
    at_start = renderer["satellite_rotation"](scenario, OriginalRotation(), 0.0)
    later = renderer["satellite_rotation"](scenario, OriginalRotation(), 1.0)
    assert at_start == pytest.approx((1.0, 0.0, 0.0, 0.0))
    assert later != pytest.approx(at_start)
