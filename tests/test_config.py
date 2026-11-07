from pathlib import Path

import pytest

from blender_synth_lc.config import (
    load_config,
    load_model_sizes,
    resolve_model_dimensions,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dataset_config_loads_precession_settings():
    config = load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset")

    assert config.count == 10_000
    assert config.precession_angle_deg == 0.0
    assert config.precession_period_s == 60.0
    assert config.precession_phase_deg == 0.0
    assert config.precession_fraction == 0.5
    assert config.precession_angle_min_deg == 5.0
    assert config.precession_angle_max_deg == 30.0
    assert config.precession_period_min_s == 20.0
    assert config.precession_period_max_s == 180.0


@pytest.mark.parametrize("value", ("0", "-1"))
def test_invalid_dataset_total_curves_are_rejected(tmp_path, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source.replace("total_curves = 10000", f"total_curves = {value}"), encoding="utf-8")

    with pytest.raises(ValueError, match="count/total_curves must be at least 1"):
        load_config(config_path, kind="dataset")


def test_legacy_curves_per_model_setting_requires_migration(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace("total_curves = 10000", "curves_per_model = 2")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match="use dataset.total_curves"):
        load_config(config_path, kind="dataset")


def test_dataset_precession_fraction_defaults_to_half(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source.replace("precession_fraction = 0.5\n", ""), encoding="utf-8")

    assert load_config(config_path, kind="dataset").precession_fraction == 0.5


@pytest.mark.parametrize("value", ("-0.1", "1.1", "nan", "inf"))
def test_invalid_dataset_precession_fraction_is_rejected(tmp_path, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source.replace("precession_fraction = 0.5", f"precession_fraction = {value}"), encoding="utf-8")

    with pytest.raises(ValueError, match=r"dataset.precession_fraction must be in \[0, 1\]"):
        load_config(config_path, kind="dataset")


def test_elevation_mask_defaults_to_twenty_degrees(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace("minimum_elevation_deg = 20\n", "")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    config = load_config(config_path, kind="dataset")

    assert config.minimum_elevation_deg == 20.0


def test_elevation_mask_ini_override_is_preserved(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace("minimum_elevation_deg = 20", "minimum_elevation_deg = 25")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    config = load_config(config_path, kind="dataset")

    assert config.minimum_elevation_deg == 25.0


@pytest.mark.parametrize("value", ("nan", "inf", "90", "100"))
def test_invalid_elevation_masks_are_rejected(tmp_path, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace(
        "minimum_elevation_deg = 20", f"minimum_elevation_deg = {value}"
    )
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match=r"finite and in \[0, 90\)"):
        load_config(config_path, kind="dataset")


@pytest.mark.parametrize("value", ("5", "0", "-1"))
def test_elevation_masks_below_ten_warn_and_clamp(tmp_path, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace(
        "minimum_elevation_deg = 20", f"minimum_elevation_deg = {value}"
    )
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.warns(UserWarning, match="using 10 degrees"):
        config = load_config(config_path, kind="dataset")

    assert config.minimum_elevation_deg == 10.0


def test_model_sizes_load_per_axis_dimensions(tmp_path):
    config_path = tmp_path / "model_sizes.json"
    config_path.write_text(
        '{"Lotos_model.blend": {"dimensions_m": '
        '{"x": 4.0, "y": 2.0, "z": 1.0}}}',
        encoding="utf-8",
    )

    assert load_model_sizes(config_path) == {"Lotos_model.blend": (4.0, 2.0, 1.0)}


def test_empty_model_sizes_map_uses_native_dimensions(tmp_path):
    config_path = tmp_path / "model_sizes.json"
    config_path.write_text("{}\n", encoding="utf-8")

    model_scale, dimensions_m, calibrated = resolve_model_dimensions(
        "Lotos_model.blend", (2.0, 4.0, 1.0), load_model_sizes(config_path), 0.5
    )

    assert model_scale == (1.0, 1.0, 1.0)
    assert dimensions_m == (1.0, 2.0, 0.5)
    assert not calibrated


@pytest.mark.parametrize(
    "content",
    (
        '{"Lotos_model.blend": {"dimensions_m": {"x": 1, "y": 2}}}',
        '{"Lotos_model.blend": {"dimensions_m": {"x": 1, "y": 2, "z": 0}}}',
        '{"Lotos_model.blend": {"dimensions_m": {"x": 1, "y": 2, "z": NaN}}}',
    ),
)
def test_invalid_model_sizes_are_rejected(tmp_path, content):
    config_path = tmp_path / "model_sizes.json"
    config_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="dimensions_m"):
        load_model_sizes(config_path)


def test_model_size_map_scales_each_axis_to_target_meters():
    model_scale, dimensions_m, calibrated = resolve_model_dimensions(
        "Lotos_model.blend",
        (2.0, 4.0, 8.0),
        {"Lotos_model.blend": (4.0, 2.0, 1.0)},
        0.5,
    )

    assert model_scale == (4.0, 1.0, 0.25)
    assert dimensions_m == (4.0, 2.0, 1.0)
    assert calibrated


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    (
        ("precession_angle_deg", "181", "must be in \\[0, 180\\]"),
        ("precession_period_s", "0", "must be positive"),
        ("precession_phase_deg", "nan", "must be finite"),
    ),
)
def test_invalid_precession_settings_are_rejected(tmp_path, setting, value, message):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace(f"{setting} = 0", f"{setting} = {value}")
    if setting == "precession_period_s":
        source = source.replace("precession_angle_deg = 0", "precession_angle_deg = 10")
        source = source.replace(f"{setting} = 60", f"{setting} = {value}")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_config(config_path, kind="dataset")


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    (
        ("precession_angle_min_deg", "31", "angle range"),
        ("precession_period_max_s", "10", "period range"),
    ),
)
def test_invalid_dataset_precession_ranges_are_rejected(tmp_path, setting, value, message):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace(f"{setting} = { {'precession_angle_min_deg': '5', 'precession_period_max_s': '180'}[setting] }", f"{setting} = {value}")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_config(config_path, kind="dataset")