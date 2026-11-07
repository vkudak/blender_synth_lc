import math

import pytest

from random import Random

from blender_synth_lc.attitude import (
    is_rotating,
    load_model_spin_axes,
    precession_phase_rad,
    sample_precession_parameters,
    sample_spin_axis,
    sample_spin_period_s,
    spin_axis_options,
    spin_phase_rad,
)


def test_period_at_three_minutes_is_rotating():
    assert is_rotating(180.0)


def test_period_at_three_seconds_is_rotating():
    assert is_rotating(3.0)


def test_period_under_three_seconds_is_excluded():
    with pytest.raises(ValueError, match="below 3 seconds"):
        is_rotating(2.999999)


def test_period_over_three_minutes_is_excluded():
    with pytest.raises(ValueError, match="are excluded"):
        is_rotating(180.000001)


def test_zero_period_is_non_rotating():
    assert not is_rotating(0.0)


def test_zero_period_keeps_phase_static_for_entire_pass():
    initial_phase = 1.25

    assert spin_phase_rad(0.0, -30.0, initial_phase) == initial_phase
    assert spin_phase_rad(0.0, 300.0, initial_phase) == initial_phase


def test_excluded_period_cannot_be_used_for_phase_propagation():
    with pytest.raises(ValueError, match="are excluded"):
        spin_phase_rad(240.0, 30.0)


def test_rotating_phase_advances_and_wraps():
    phase = spin_phase_rad(60.0, 90.0, 0.0)

    assert phase == pytest.approx(math.pi)


def test_precession_phase_advances_from_configured_initial_phase():
    phase = precession_phase_rad(60.0, 15.0, math.pi / 3.0)

    assert phase == pytest.approx(5.0 * math.pi / 6.0)


def test_precession_phase_wraps_for_negative_time():
    phase = precession_phase_rad(60.0, -15.0)

    assert phase == pytest.approx(3.0 * math.pi / 2.0)


def test_precession_requires_positive_finite_period():
    for period_s in (0.0, -1.0, math.inf, math.nan):
        with pytest.raises(ValueError):
            precession_phase_rad(period_s, 0.0)


def test_sampled_precession_parameters_stay_in_ranges_and_are_reproducible():
    parameters = sample_precession_parameters(Random(23), True, 5.0, 30.0, 20.0, 180.0)
    repeated = sample_precession_parameters(Random(23), True, 5.0, 30.0, 20.0, 180.0)
    angle_deg, period_s, phase_rad = parameters

    assert parameters == repeated
    assert 5.0 <= angle_deg <= 30.0
    assert 20.0 <= period_s <= 180.0
    assert 0.0 <= phase_rad < math.tau


def test_static_satellite_has_no_sampled_precession():
    assert sample_precession_parameters(Random(23), False, 5.0, 30.0, 20.0, 180.0) == (
        0.0,
        0.0,
        0.0,
    )


def test_precession_fraction_selects_rotating_curves_reproducibly():
    def sample(seed, fraction):
        return sample_precession_parameters(
            Random(seed), True, 5.0, 30.0, 20.0, 180.0, fraction
        )

    assert sample(1, 0.0) == (0.0, 0.0, 0.0)
    assert sample(2, 1.0)[0] > 0.0
    assert sample(1, 0.5)[0] > 0.0
    assert sample(1, 0.5) == sample(1, 0.5)
    assert sample(2, 0.5) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize("period_s", [-1.0, math.inf, math.nan])
def test_invalid_period_is_rejected(period_s):
    with pytest.raises(ValueError):
        is_rotating(period_s)


def test_sampled_static_period_is_zero():
    assert sample_spin_period_s(Random(3), rotating=False) == 0.0


def test_sampled_rotating_period_stays_inside_allowed_window():
    period = sample_spin_period_s(Random(3), rotating=True)

    assert 3.0 <= period <= 180.0
    assert is_rotating(period)


def test_model_spin_axes_are_loaded_and_unlisted_models_allow_xyz(tmp_path):
    config_path = tmp_path / "spin_axes.json"
    config_path.write_text(
        '{"SL-14.blend": {"spin_axes": ["X", "Z"]}}', encoding="utf-8"
    )

    model_spin_axes = load_model_spin_axes(config_path)

    assert spin_axis_options("SL-14.blend", model_spin_axes) == (
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    assert spin_axis_options("Topex_good.blend", model_spin_axes) == (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    assert sample_spin_axis(Random(7), "SL-14.blend", model_spin_axes) in {
        (1.0, 0.0, 0.0),
        (0.0, 0.0, 1.0),
    }


def test_model_spin_axes_reject_invalid_axis_names(tmp_path):
    config_path = tmp_path / "spin_axes.json"
    config_path.write_text(
        '{"SL-14.blend": {"spin_axes": ["W"]}}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="invalid spin axis"):
        load_model_spin_axes(config_path)