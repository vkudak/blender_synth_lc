# Sensor Noise Model

This page describes the measurement-noise pipeline applied to every rendered
light curve, including the optional hardware-in-the-loop detector effects.

## Units

All flux levels are in **normalized-flux units**: the clean range-corrected
curve maximum is exactly `1.0`. So `bias_level = 0.01` means a bias of 1% of
the peak flux, and `readout_noise_std = 0.005` is a per-sample 1-sigma of 0.5%
of the peak flux. The model remains a relative-flux proxy, not calibrated
photometry.

## Pipeline

Each sample passes through the following stages in order (the order matches a
real CCD/CMOS readout chain):

1. **Shot noise** (always on). Gaussian approximation to photon shot noise.
   For clean normalized flux `f` and elevation `e`, the relative airmass `X(e)`
   uses the Kasten-Young formula normalized to exactly `1` at zenith, and the
   1-sigma is `sigma_shot = sqrt(f * X(e)) / reference_snr`. Fainter points
   and lower elevations have larger relative uncertainty.
2. **Frame-correlated noise** (`correlated_noise_std`, optional). An AR(1)
   (Ornstein-Uhlenbeck) process modelling slowly varying sensor/sky effects:
   `x[t] = phi * x[t-1] + std * sqrt(1 - phi^2) * N(0, 1)` with
   `phi = exp(-dt / correlation_time_s)`, where `dt` is the time since the
   previous sample. The innovation scaling keeps the stationary variance equal
   to `correlated_noise_std^2` regardless of the sampling interval. The first
   sample draws from the stationary distribution `N(0, std)`.
   `correlation_time_s` is the lag over which the correlated component decays
   by a factor of `e`; it must be positive when `correlated_noise_std > 0`.
3. **Readout noise** (`readout_noise_std`, optional). Zero-mean Gaussian noise
   independent of the signal level, added per sample.
4. **Bias / dark offset** (`bias_level`, optional). A constant level added to
   every sample of the curve.
5. **Saturation clipping** (`saturation_level`, optional). The measured flux is
   clipped to at most `saturation_level` (full-well capacity). With the default
   normalization, values near `1.0` rarely clip; set it slightly above `1.0`
   (e.g. `1.05`) for occasional peak clipping, or below `1.0` for heavy
   saturation.
6. **ADC quantization** (`adc_bits`, optional). The flux is clamped to
   `[0, full_scale]` and rounded to `2^adc_bits - 1` evenly spaced levels, where
   `full_scale` is `saturation_level` if set, otherwise `1.0`. Typical detector
   values are 12-16 bits. Note that quantization clamps negative noise swings
   to zero.

Every parameter defaults to `0` (disabled), which reproduces the original
shot-noise-only behavior bit-for-bit for a given seed.

## Configuration (`[noise]` section)

| Parameter | Default | Meaning |
| --- | --- | --- |
| `reference_snr` | `50` | SNR for normalized flux `1` at zenith; 1-sigma is `1 / reference_snr`. Must be positive. |
| `bias_level` | `0` | Constant bias/dark offset added to every sample, in `[0, 1]`. |
| `readout_noise_std` | `0` | Per-sample Gaussian readout noise 1-sigma, `>= 0`. |
| `correlated_noise_std` | `0` | AR(1) correlated noise 1-sigma, `>= 0`. |
| `correlation_time_s` | `0` | AR(1) correlation time constant in seconds; must be `> 0` when `correlated_noise_std > 0`. |
| `saturation_level` | `0` | Full-well clipping level; `0` disables clipping. Also the ADC full scale. |
| `adc_bits` | `0` | ADC bit depth; `0` disables quantization, otherwise `[2, 24]`. |

The values shipped in `config/dataset.ini` and `config/curve.ini` are a
minimal realistic starting point: 1% bias, 0.5% readout noise, 0.3% correlated
noise with a 5 s correlation time, saturation at 105% of peak, and 12-bit
quantization.

## Output and metadata

- `relative_flux_noisy` is the final measured flux after all enabled stages.
  Unlike the pure shot-noise model, values are clipped at `saturation_level`
  when clipping is enabled, and are non-negative and discrete when `adc_bits`
  is set.
- `noise_sigma` is the combined 1-sigma per sample:
  `sqrt(sigma_shot^2 + readout_noise_std^2 + correlated_noise_std^2)`.
  Quantization and clipping are deterministic and not included.
- The JSON sidecar records every sensor parameter and the noise seed under
  `noise.sensor_response`, so datasets remain self-describing.

## Reproducibility

The noise generator is seeded deterministically per curve
(`{seed}:{curve_index}:photometric-noise`) and is independent from the
scenario RNG, so changing sensor parameters does not change the sampled
orbits, attitudes, or Sun directions. Disabling all sensor effects yields the
same noisy values as the original shot-noise-only model for a given seed.
