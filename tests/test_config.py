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
    assert config.attitude_mode == "random"
    assert config.spin_period_s == 20.0
    assert config.spin_period_min_s == 3.0
    assert config.spin_period_max_s == 180.0
    assert config.rotating_fraction == 0.5
    assert config.tumbling_fraction == 0.01
    assert config.initial_phase_mode == "random"
    assert config.initial_phase_rad == 0.0
    assert config.precession_fraction == 0.5
    assert config.precession_angle_min_deg == 5.0
    assert config.precession_angle_max_deg == 30.0
    assert config.precession_period_min_s == 20.0
    assert config.precession_period_max_s == 180.0
    assert config.precession_phase_deg == 0.0
    assert config.model_scale_min == 1.0
    assert config.model_scale_max == 1.5
    assert config.reference_snr == 50.0
    assert config.bias_level == 0.01
    assert config.readout_noise_std == 0.005
    assert config.correlated_noise_std == 0.003
    assert config.correlation_time_s == 5.0
    assert config.saturation_level == 1.05
    assert config.adc_bits == 12


def test_curve_config_loads_reference_snr():
    config = load_config(PROJECT_ROOT / "config" / "curve.ini", kind="curve")

    assert config.reference_snr == 50.0


@pytest.mark.parametrize("value", ("-0.1", "1.1", "nan", "inf"))
def test_invalid_dataset_tumbling_fraction_is_rejected(tmp_path, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(
        source.replace("fraction = 0.01", f"fraction = {value}"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"dataset.tumbling.fraction must be in \[0, 1\]"):
        load_config(config_path, kind="dataset")


def test_tumbling_fraction_defaults_and_can_be_disabled(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source.replace("[dataset.tumbling]", "[unused.tumbling]"), encoding="utf-8")
    assert load_config(config_path, kind="dataset").tumbling_fraction == 0.01
    config_path.write_text(source.replace("fraction = 0.01", "fraction = 0"), encoding="utf-8")
    assert load_config(config_path, kind="dataset").tumbling_fraction == 0.0
    assert load_config(PROJECT_ROOT / "config" / "curve.ini", kind="curve").tumbling_fraction == 0.0


@pytest.mark.parametrize("value", ("nan", "inf"))
def test_non_finite_tumbling_period_bounds_are_rejected(tmp_path, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(
        source.replace("spin_period_max_s = 180", f"spin_period_max_s = {value}"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="spin period bounds must be finite"):
        load_config(config_path, kind="dataset")


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


@pytest.mark.parametrize("value", ("-0.1", "1.1", "nan"))
def test_invalid_bias_level_is_rejected(tmp_path, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(
        source.replace("bias_level = 0.01", f"bias_level = {value}"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"noise.bias_level must be finite and in \[0, 1\]"):
        load_config(config_path, kind="dataset")


def test_correlated_noise_requires_positive_correlation_time(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(
        source.replace("correlation_time_s = 5", "correlation_time_s = 0"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="noise.correlation_time_s must be positive"):
        load_config(config_path, kind="dataset")


@pytest.mark.parametrize("value", ("-1", "1", "25"))
def test_invalid_adc_bits_is_rejected(tmp_path, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(
        source.replace("adc_bits = 12", f"adc_bits = {value}"),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"noise.adc_bits must be 0 \(disabled\) or in \[2, 24\]"):
        load_config(config_path, kind="dataset")


@pytest.mark.parametrize("setting,value", (
    ("min_factor", "0"),
    ("max_factor", "nan"),
    ("max_factor", "0.5"),
))
def test_invalid_dataset_model_scale_ranges_are_rejected(tmp_path, setting, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    original = "1" if setting == "min_factor" else "1.5"
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


def test_dataset_precession_fraction_is_required(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source.replace("\nfraction = 0.5\n", "\n"), encoding="utf-8")

    with pytest.raises(ValueError, match=r"dataset.precession options are invalid \(missing: fraction\)"):
        load_config(config_path, kind="dataset")


@pytest.mark.parametrize("value", ("-0.1", "1.1", "nan", "inf"))
def test_invalid_dataset_precession_fraction_is_rejected(tmp_path, value):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source.replace("\nfraction = 0.5", f"\nfraction = {value}"), encoding="utf-8")

    with pytest.raises(ValueError, match=r"dataset.precession.fraction must be in \[0, 1\]"):
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
        ("angle_max_deg", "181", "angle range"),
        ("period_min_s", "0", "period range"),
    ),
)
def test_invalid_dataset_precession_ranges_are_rejected(tmp_path, setting, value, message):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    original = "30" if setting == "angle_max_deg" else "20"
    source = source.replace(f"{setting} = {original}", f"{setting} = {value}")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_config(config_path, kind="dataset")

@pytest.mark.parametrize(
    ("setting", "original", "value", "message"),
    (
        ("angle_min_deg", "5", "31", "angle range"),
        ("period_max_s", "180", "10", "period range"),
    ),
)
def test_reversed_dataset_precession_ranges_are_rejected(tmp_path, setting, original, value, message):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace(f"{setting} = {original}", f"{setting} = {value}")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_config(config_path, kind="dataset")


def test_dataset_fixed_precession_period_and_scale_are_loaded(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace(
        "period_mode = random\nperiod_min_s = 20\nperiod_max_s = 180",
        "period_mode = fixed\nperiod_s = 60",
    )
    source = source.replace(
        "mode = random\nmin_factor = 1\nmax_factor = 1.5",
        "mode = fixed\nfactor = 1.25",
    )
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    config = load_config(config_path, kind="dataset")

    assert config.precession_period_min_s == config.precession_period_max_s == 60.0
    assert config.model_scale_min == config.model_scale_max == 1.25


def test_dataset_rejects_fields_unused_by_selected_mode(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace(
        "mode = random\nmin_factor = 1\nmax_factor = 1.5",
        "mode = fixed\nfactor = 1.25\nmin_factor = 1\nmax_factor = 1.5",
    )
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match="unused for selected mode"):
        load_config(config_path, kind="dataset")


def test_dataset_mode_uses_random_not_range_for_bounds(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace("angle_mode = random", "angle_mode = range")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match="must be 'fixed' or 'random'"):
        load_config(config_path, kind="dataset")


def test_dataset_config_requires_dataset_period_section(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace("[dataset.period]\n", "[attitude]\n")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match="dataset.period"):
        load_config(config_path, kind="dataset")


def test_dataset_config_rejects_curve_attitude_section(tmp_path):
    source = (PROJECT_ROOT / "config" / "dataset.ini").read_text(encoding="utf-8")
    source = source.replace("[dataset.period]\n", "[attitude]\nmode = random\n\n[dataset.period]\n")
    config_path = tmp_path / "dataset.ini"
    config_path.write_text(source, encoding="utf-8")

    with pytest.raises(ValueError, match=r"use \[dataset.period\], not \[attitude\]"):
        load_config(config_path, kind="dataset")