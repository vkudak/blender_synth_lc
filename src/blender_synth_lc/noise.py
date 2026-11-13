"""Photon-limited noise and optional detector effects for normalized light curves."""

from dataclasses import dataclass
from math import exp, isfinite, radians, sin, sqrt
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
    """Return absolute 1-sigma shot noise in normalized-flux units."""
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


@dataclass(frozen=True)
class SensorResponse:
    """Optional detector effects; all levels are in normalized-flux units.

    Normalized-flux units mean the clean curve maximum is exactly 1.0, so
    ``bias_level = 0.01`` is a bias of 1% of the peak flux. Zero-valued
    parameters disable the corresponding effect, so the default instance
    reproduces plain shot-noise behavior.
    """

    bias_level: float = 0.0
    readout_noise_std: float = 0.0
    correlated_noise_std: float = 0.0
    correlation_time_s: float = 0.0
    saturation_level: float = 0.0
    adc_bits: int = 0

    @property
    def enabled(self) -> bool:
        return self != SensorResponse()


class SensorChain:
    """Apply a detector response to a normalized-flux time series.

    Effects are applied per sample in the order of a real sensor: Gaussian
    shot noise (elevation-dependent), AR(1) frame-correlated noise, Gaussian
    readout noise, constant bias/dark offset, saturation clipping, and ADC
    quantization. The chain is stateful because the correlated component
    evolves between samples; feed samples in time order.
    """

    def __init__(self, response: SensorResponse, rng: Random):
        self._response = response
        self._rng = rng
        self._correlated = 0.0
        self._correlated_initialized = False

    def measure(
        self,
        relative_flux: float,
        elevation_deg: float,
        reference_snr: float,
        dt_s: float,
    ) -> tuple[float, float]:
        """Return the measured flux and the combined absolute 1-sigma.

        ``dt_s`` is the elapsed time since the previous sample; it is used only
        for the correlated component and is ignored for the first sample, which
        draws from the stationary AR(1) distribution instead.
        """
        response = self._response
        shot_sigma = photometric_noise_sigma(relative_flux, elevation_deg, reference_snr)
        value = relative_flux + self._rng.gauss(0.0, shot_sigma)
        if response.correlated_noise_std > 0.0:
            value += self._next_correlated(dt_s)
        if response.readout_noise_std > 0.0:
            value += self._rng.gauss(0.0, response.readout_noise_std)
        if response.bias_level > 0.0:
            value += response.bias_level
        if response.saturation_level > 0.0:
            value = min(value, response.saturation_level)
        if response.adc_bits > 0:
            value = self._quantize(value)
        combined_sigma = sqrt(
            shot_sigma**2
            + response.readout_noise_std**2
            + response.correlated_noise_std**2
        )
        return value, combined_sigma

    def _next_correlated(self, dt_s: float) -> float:
        std = self._response.correlated_noise_std
        if not self._correlated_initialized:
            # Draw from the stationary distribution so the first sample has the
            # same marginal variance as later ones.
            self._correlated = self._rng.gauss(0.0, std)
            self._correlated_initialized = True
            return self._correlated
        tau = self._response.correlation_time_s
        phi = exp(-dt_s / tau) if tau > 0.0 else 0.0
        # Innovation scaled to keep the stationary variance equal to std^2
        # regardless of the sampling interval.
        self._correlated = (
            phi * self._correlated
            + std * sqrt(1.0 - phi * phi) * self._rng.gauss(0.0, 1.0)
        )
        return self._correlated

    def _quantize(self, value: float) -> float:
        response = self._response
        full_scale = response.saturation_level if response.saturation_level > 0.0 else 1.0
        levels = (1 << response.adc_bits) - 1
        clipped = min(max(value, 0.0), full_scale)
        return round(clipped / full_scale * levels) / levels * full_scale
