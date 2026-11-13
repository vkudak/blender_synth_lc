import math
from random import Random

import pytest

from blender_synth_lc.noise import (
    SensorChain,
    SensorResponse,
    photometric_noise_sigma,
    relative_airmass,
    sample_noisy_flux,
)


def test_reference_snr_sets_two_percent_noise_at_unit_flux_and_zenith():
    sigma = photometric_noise_sigma(1.0, 90.0, 50.0)

    assert sigma == pytest.approx(0.02)
    assert relative_airmass(90.0) == pytest.approx(1.0)


def test_noise_grows_for_fainter_flux_and_lower_elevation():
    reference_sigma = photometric_noise_sigma(1.0, 90.0, 50.0)
    faint_sigma = photometric_noise_sigma(0.25, 90.0, 50.0)
    low_elevation_sigma = photometric_noise_sigma(1.0, 20.0, 50.0)

    assert faint_sigma / 0.25 > reference_sigma
    assert low_elevation_sigma > reference_sigma
    assert relative_airmass(20.0) > relative_airmass(90.0)


def test_noisy_flux_sampling_is_seeded_and_returns_sigma():
    first = sample_noisy_flux(0.5, 45.0, 50.0, Random(8))
    second = sample_noisy_flux(0.5, 45.0, 50.0, Random(8))

    assert first == second
    assert first[1] == photometric_noise_sigma(0.5, 45.0, 50.0)
    assert math.isfinite(first[0])


@pytest.mark.parametrize(
    ("relative_flux", "elevation_deg", "reference_snr"),
    ((-0.1, 90.0, 50.0), (1.0, 0.0, 50.0), (1.0, 90.0, 0.0)),
)
def test_invalid_noise_inputs_are_rejected(relative_flux, elevation_deg, reference_snr):
    with pytest.raises(ValueError):
        photometric_noise_sigma(relative_flux, elevation_deg, reference_snr)

def test_default_sensor_chain_matches_legacy_shot_noise_stream():
    chain = SensorChain(SensorResponse(), Random(11))
    legacy_rng = Random(11)

    for flux in (0.2, 0.7, 1.0):
        measured, sigma = chain.measure(flux, 60.0, 50.0, 2.0)
        legacy_value, legacy_sigma = sample_noisy_flux(flux, 60.0, 50.0, legacy_rng)
        assert measured == legacy_value
        assert sigma == legacy_sigma


def test_bias_shifts_output_by_constant():
    chain = SensorChain(SensorResponse(bias_level=0.05), Random(3))
    value, sigma = chain.measure(0.5, 90.0, 50.0, 1.0)
    legacy_value, legacy_sigma = sample_noisy_flux(0.5, 90.0, 50.0, Random(3))

    assert value == pytest.approx(legacy_value + 0.05)
    assert sigma == pytest.approx(legacy_sigma)


def test_saturation_clips_peak_flux():
    chain = SensorChain(SensorResponse(saturation_level=0.8), Random(1))
    value, _ = chain.measure(1.0, 90.0, 1e9, 1.0)

    assert value == pytest.approx(0.8)


def test_adc_quantization_produces_discrete_nonnegative_levels():
    chain = SensorChain(SensorResponse(adc_bits=4), Random(7))
    step = 1.0 / (2**4 - 1)

    for flux in (0.0, 0.3, 0.55, 1.0):
        value, _ = chain.measure(flux, 90.0, 1e9, 1.0)
        assert 0.0 <= value <= 1.0
        assert value / step == pytest.approx(round(value / step))


def test_adc_quantization_uses_saturation_as_full_scale():
    chain = SensorChain(SensorResponse(adc_bits=4, saturation_level=2.0), Random(7))
    value, _ = chain.measure(2.0, 90.0, 1e9, 1.0)

    assert value == pytest.approx(2.0)


def test_combined_sigma_adds_components_in_quadrature():
    response = SensorResponse(readout_noise_std=0.03, correlated_noise_std=0.04, correlation_time_s=10.0)
    chain = SensorChain(response, Random(5))
    shot_sigma = photometric_noise_sigma(1.0, 90.0, 50.0)

    _, sigma = chain.measure(1.0, 90.0, 50.0, 1.0)

    assert sigma == pytest.approx(math.sqrt(shot_sigma**2 + 0.03**2 + 0.04**2))


def test_correlated_noise_is_reproducible_and_slow_with_long_tau():
    response = SensorResponse(correlated_noise_std=0.01, correlation_time_s=1e9)
    chain_a = SensorChain(response, Random(9))
    chain_b = SensorChain(response, Random(9))

    values_a = [chain_a.measure(0.5, 90.0, 1e9, 1.0)[0] for _ in range(50)]
    values_b = [chain_b.measure(0.5, 90.0, 1e9, 1.0)[0] for _ in range(50)]

    assert values_a == values_b
    # With tau >> dt the AR(1) innovation per step is tiny, so consecutive
    # samples of the correlated component barely move.
    steps = [abs(b - a) for a, b in zip(values_a, values_a[1:])]
    assert max(steps) < 1e-3
    assert any(abs(value - 0.5) > 1e-6 for value in values_a)
