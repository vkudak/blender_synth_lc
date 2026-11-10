"""Simple photon-limited noise for normalized light-curve measurements."""

from math import isfinite, radians, sin, sqrt
from random import Random


def _kasten_young_airmass(elevation_deg: float) -> float:
    return 1.0 / (
        sin(radians(elevation_deg))
        + 0.50572 * (elevation_deg + 6.07995) ** -1.6364
    )


def relative_airmass(elevation_deg: float) -> float:
    """Return Kasten-Young airmass normalized to exactly 1 at zenith."""
    if not isfinite(elevation_deg) or not 0.0 < elevation_deg <= 90.0:
        raise ValueError("elevation_deg must be finite and in (0, 90]")
    return _kasten_young_airmass(elevation_deg) / _kasten_young_airmass(90.0)


def photometric_noise_sigma(
    relative_flux: float,
    elevation_deg: float,
    reference_snr: float,
) -> float:
    """Return absolute 1-sigma noise in normalized-flux units."""
    if not isfinite(relative_flux) or relative_flux < 0.0:
        raise ValueError("relative_flux must be finite and non-negative")
    if not isfinite(reference_snr) or reference_snr <= 0.0:
        raise ValueError("reference_snr must be finite and positive")
    return sqrt(relative_flux * relative_airmass(elevation_deg)) / reference_snr


def sample_noisy_flux(
    relative_flux: float,
    elevation_deg: float,
    reference_snr: float,
    rng: Random,
) -> tuple[float, float]:
    """Return a Gaussian shot-noise sample and its absolute 1-sigma uncertainty."""
    sigma = photometric_noise_sigma(relative_flux, elevation_deg, reference_snr)
    return relative_flux + rng.gauss(0.0, sigma), sigma