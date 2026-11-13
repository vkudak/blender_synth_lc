import pytest

from blender_synth_lc.photometry import (
    FILTER_PRESETS,
    normalize_rgb_weights,
    resolve_sensor_filter,
)


def test_presets_are_normalized_and_peak_aligned():
    for name, weights in FILTER_PRESETS.items():
        assert sum(weights) == pytest.approx(1.0), name
    assert FILTER_PRESETS["luminance"][1] == max(FILTER_PRESETS["luminance"])
    assert FILTER_PRESETS["johnson_b"][2] == max(FILTER_PRESETS["johnson_b"])
    assert FILTER_PRESETS["johnson_v"][1] == max(FILTER_PRESETS["johnson_v"])
    assert FILTER_PRESETS["johnson_r"][0] == max(FILTER_PRESETS["johnson_r"])


def test_none_filter_disables_weighting():
    assert resolve_sensor_filter("none", None) == ("none", None)


def test_preset_filter_returns_preset_weights():
    filter_type, weights = resolve_sensor_filter("Luminance", None)

    assert filter_type == "luminance"
    assert weights == FILTER_PRESETS["luminance"]


def test_custom_weights_are_parsed_and_normalized():
    filter_type, weights = resolve_sensor_filter("custom", "1, 1, 1")

    assert filter_type == "custom"
    assert weights == pytest.approx((1 / 3, 1 / 3, 1 / 3))


def test_custom_weights_keep_ratios_not_scale():
    _, weights = resolve_sensor_filter("custom", "0.4252, 1.4304, 0.1444")

    assert weights == pytest.approx((0.2126, 0.7152, 0.0722))


def test_single_channel_custom_filter():
    _, weights = resolve_sensor_filter("custom", "1, 0, 0")

    assert weights == (1.0, 0.0, 0.0)


@pytest.mark.parametrize(
    ("filter_type", "rgb_weights", "message"),
    (
        ("x-band", None, "sensor.filter_type must be one of"),
        ("none", "1, 1, 1", "only valid with filter_type = custom"),
        ("luminance", "1, 1, 1", "only valid with filter_type = custom"),
        ("custom", None, "sensor.rgb_weights is required"),
        ("custom", "1, 1", "exactly 3"),
        ("custom", "1, 1, -0.5", "non-negative"),
        ("custom", "0, 0, 0", "positive sum"),
        ("custom", "1, nan, 1", "must be finite"),
        ("custom", "1, inf, 1", "must be finite"),
    ),
)
def test_invalid_filter_settings_are_rejected(filter_type, rgb_weights, message):
    with pytest.raises(ValueError, match=message):
        resolve_sensor_filter(filter_type, rgb_weights)


def test_normalize_rgb_weights_validates_input():
    with pytest.raises(ValueError, match="positive sum"):
        normalize_rgb_weights((0.0, 0.0, 0.0))
