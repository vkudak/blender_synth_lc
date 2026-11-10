from pathlib import Path

import pytest

from blender_synth_lc.config import (
    load_config,
    ModelShape,
    load_model_shapes,
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
    assert config.model_scale_min == 1.0
    assert config.model_scale_max == 1.5
    assert config.reference_snr == 50.0


def test_curve_config_loads_reference_snr():
    config = load_config(PROJECT_ROOT / "config" / "curve.ini", kind="curve")

    assert config.reference_snr == 50.0


@pytest.mark.parametrize("value", ("0", "-1", "nan", "inf"))
def test_invalid_reference_snr_is_rejected(tmp_path, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(
        source.replace("reference_snr = 50", f"reference_snr = {value}"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="noise.reference_snr must be finite and positive"):
        load_config(config_path, kind="dataset")


@pytest.mark.parametrize("setting,value", (
    ("model_scale_min", "0"),
    ("model_scale_max", "nan"),
    ("model_scale_max", "0.5"),
))
def test_invalid_dataset_model_scale_ranges_are_rejected(tmp_path, setting, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    original = "1" if setting == "model_scale_min" else "1.5"
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(
        source.replace(f"{setting} = {original}", f"{setting} = {value}"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="model scale range"):
        load_config(config_path, kind="dataset")


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


def test_model_shapes_load_required_fields_and_optional_dimensions(tmp_path):
    config_path = tmp_path / "model_shapes.json"
    config_path.write_text(
        '{"Lotos_model.blend": {"body_shape": ["cube"], "solar_panel_count": 2, '
        '"dimensions_m": {"x": 4.0, "y": 2.0, "z": 1.0}},'
        ' "Other.blend": {"body_shape": ["cylinder"], "solar_panel_count": 0}}',
        encoding="utf-8",
    )

    shapes = load_model_shapes(config_path)

    assert shapes["Lotos_model.blend"] == ModelShape(("cube",), 2, (4.0, 2.0, 1.0))
    assert shapes["Other.blend"] == ModelShape(("cylinder",), 0, None)


def test_model_without_dimensions_uses_native_dimensions(tmp_path):
    config_path = tmp_path / "model_shapes.json"
    config_path.write_text(
        '{"Lotos_model.blend": {"body_shape": ["cube"], "solar_panel_count": 0}}',
        encoding="utf-8",
    )

    model_scale, dimensions_m, calibrated = resolve_model_dimensions(
        "Lotos_model.blend", (2.0, 4.0, 1.0), load_model_shapes(config_path), 0.5
    )

    assert model_scale == (1.0, 1.0, 1.0)
    assert dimensions_m == (1.0, 2.0, 0.5)
    assert not calibrated


def test_model_missing_from_shapes_is_rejected():
    with pytest.raises(ValueError, match="model_shapes.json"):
        resolve_model_dimensions("Lotos_model.blend", (1.0, 1.0, 1.0), {}, 1.0)


@pytest.mark.parametrize(
    ("content", "message"),
    (
        ('{"M.blend": {"solar_panel_count": 1}}', "body_shape"),
        ('{"M.blend": {"body_shape": [], "solar_panel_count": 1}}', "body_shape"),
        ('{"M.blend": {"body_shape": ["cube"]}}', "solar_panel_count"),
        ('{"M.blend": {"body_shape": ["cube"], "solar_panel_count": -1}}', "solar_panel_count"),
        ('{"M.blend": {"body_shape": ["cube"], "solar_panel_count": 1.5}}', "solar_panel_count"),
        (
            '{"M.blend": {"body_shape": ["cube"], "solar_panel_count": 1, '
            '"dimensions_m": {"x": 1, "y": 2}}}',
            "dimensions_m",
        ),
        (
            '{"M.blend": {"body_shape": ["cube"], "solar_panel_count": 1, '
            '"dimensions_m": {"x": 1, "y": 2, "z": 0}}}',
            "dimensions_m",
        ),
    ),
)
def test_invalid_model_shapes_are_rejected(tmp_path, content, message):
    config_path = tmp_path / "model_shapes.json"
    config_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_model_shapes(config_path)


def test_repository_model_shapes_cover_all_models():
    shapes = load_model_shapes(PROJECT_ROOT / "models" / "model_shapes.json")

    for model in (PROJECT_ROOT / "models").glob("*.blend"):
        assert model.name in shapes


def test_model_size_map_scales_each_axis_to_target_meters():
    model_scale, dimensions_m, calibrated = resolve_model_dimensions(
        "Lotos_model.blend",
        (2.0, 4.0, 8.0),
        {"Lotos_model.blend": ModelShape(("cube",), 1, (4.0, 2.0, 1.0))},
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