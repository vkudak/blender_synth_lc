# Photometric Filters (`[sensor]`)

This page describes how linear RGB renders are integrated into a single
sensor-weighted flux per sample, approximating a monochrome sensor with an
optional photometric filter.

## Options

- `filter_type`: monochrome sensor filter approximation; one of `none`
  (default), `luminance`, `johnson_b`, `johnson_v`, `johnson_r`, or `custom`.
  `none` keeps the plain `R + G + B` pixel sum (the historical behavior); all
  other types compute the per-pixel flux as `w_R * R + w_G * G + w_B * B`
  before range correction and normalization.
- `rgb_weights`: three comma-separated non-negative weights with a positive
  sum, required only for `filter_type = custom` and rejected otherwise.
  Weights are normalized to sum 1 automatically.

Because every curve is normalized to its maximum, only the weight *ratios*
affect the light-curve shape; the absolute weight scale cancels. Likewise,
`none` and equal weights `(1/3, 1/3, 1/3)` produce identical normalized
curves.

## Presets

| `filter_type` | `w_R` | `w_G` | `w_B` | Approximates |
|---|---|---|---|---|
| `luminance` | 0.2126 | 0.7152 | 0.0722 | Photopic response / unfiltered ("clear") broadband monochrome CCD |
| `johnson_v` | 0.2126 | 0.7152 | 0.0722 | Johnson V band (effective wavelength ~550 nm; the photopic curve peaks at ~555 nm, so the same weights are a good V proxy) |
| `johnson_b` | 0.10 | 0.30 | 0.60 | Johnson B band (effective wavelength ~445 nm, blue-dominant) |
| `johnson_r` | 0.75 | 0.22 | 0.03 | Cousins R band (effective wavelength ~660 nm, red-dominant) |

## Approximation caveats

The B and R values follow the same idea as V: each bandpass is approximated by
the linear combination of the render's three wide RGB bands that peaks at the
filter's effective wavelength. These are heuristic first-order approximations,
not convolutions with measured Johnson-Cousins transmission curves. The
fundamental limit is that scene materials carry RGB albedos rather than
reflectance spectra, so a weighted RGB sum cannot reproduce true spectral
behavior (for example, a red surface being faint in B) beyond what the three
albedo numbers encode. Treat the filter response as approximate until spectral
materials and sensor response curves are available.

Filtering happens before normalization and before the
[noise pipeline](SENSOR_NOISE_MODEL.md); it changes the clean curve shape, not
the noise behavior. The selected `filter_type` and resolved `rgb_weights` are
recorded in each curve's JSON sidecar under `photometry.filter`.
