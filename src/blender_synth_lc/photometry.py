"""Sensor filter presets combining linear RGB render channels into scalar flux.

The weights approximate a monochrome sensor response as a linear combination of
the three wide RGB bands of the render: flux = w_R * R + w_G * G + w_B * B per
pixel. This is a first-order proxy only: scene materials carry RGB albedos
rather than reflectance spectra, so no true spectral filtering is possible.
"""

from math import isfinite


# Heuristic, peak-aligned approximations normalized to sum 1.0. They are not
# derived from a convolution with measured bandpass data. The photopic
# (luminance) weights peak near 555 nm, close to Johnson V (~550 nm), so the
# same values approximate the V band. Johnson B and Cousins R weights place
# most of the response on the blue and red channels respectively.
FILTER_PRESETS = {
    "luminance": (0.2126, 0.7152, 0.0722),
    "johnson_b": (0.10, 0.30, 0.60),
    "johnson_v": (0.2126, 0.7152, 0.0722),
    "johnson_r": (0.75, 0.22, 0.03),
}

FILTER_TYPES = ("none", "custom", *FILTER_PRESETS)


def normalize_rgb_weights(weights) -> tuple[float, float, float]:
    """Validate three RGB weights and return them normalized to sum 1.0.

    Normalization is safe because the light curve itself is normalized to its
    maximum, so only the relative weight ratios affect the curve shape.
    """
    values = tuple(float(weight) for weight in weights)
    if len(values) != 3:
        raise ValueError("sensor.rgb_weights must contain exactly 3 comma-separated values")
    if any(not isfinite(weight) for weight in values):
        raise ValueError("sensor.rgb_weights must be finite")
    if any(weight < 0.0 for weight in values):
        raise ValueError("sensor.rgb_weights must be non-negative")
    total = sum(values)
    if total <= 0.0:
        raise ValueError("sensor.rgb_weights must have a positive sum")
    return tuple(weight / total for weight in values)


def resolve_sensor_filter(
    filter_type: str, rgb_weights_value: str | None
) -> tuple[str, tuple[float, float, float] | None]:
    """Resolve the [sensor] filter settings to a normalized type and weights.

    Returns ``("none", None)`` when no weighting is applied, which reproduces
    the plain R + G + B pixel sum. ``rgb_weights_value`` is the raw INI string
    and is only valid (and required) for ``filter_type = custom``.
    """
    resolved_type = filter_type.strip().lower()
    if resolved_type not in FILTER_TYPES:
        raise ValueError(
            "sensor.filter_type must be one of: " + ", ".join(FILTER_TYPES)
        )
    if resolved_type != "custom":
        if rgb_weights_value:
            raise ValueError(
                "sensor.rgb_weights is only valid with filter_type = custom"
            )
        if resolved_type == "none":
            return resolved_type, None
        return resolved_type, FILTER_PRESETS[resolved_type]
    if not rgb_weights_value:
        raise ValueError("sensor.rgb_weights is required with filter_type = custom")
    weights = tuple(part.strip() for part in rgb_weights_value.split(","))
    return resolved_type, normalize_rgb_weights(weights)
