import math
from random import Random

import pytest

from blender_synth_lc.noise import (
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