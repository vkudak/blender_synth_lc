from pathlib import Path

import pytest

from blender_synth_lc.config import load_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_dataset_config_loads_precession_settings():
    config = load_config(PROJECT_ROOT / "config" / "dataset.ini", kind="dataset")

    assert config.precession_angle_deg == 0.0
    assert config.precession_period_s == 60.0
    assert config.precession_phase_deg == 0.0
    assert config.precession_angle_min_deg == 5.0
    assert config.precession_angle_max_deg == 30.0
    assert config.precession_period_min_s == 20.0
    assert config.precession_period_max_s == 180.0


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