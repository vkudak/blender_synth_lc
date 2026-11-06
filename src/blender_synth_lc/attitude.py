import json
from math import isfinite, tau
from pathlib import Path
from random import Random
from typing import Mapping

from . import MIN_ROTATION_PERIOD_S, ROTATION_PERIOD_CUTOFF_S


SPIN_AXIS_VECTORS = {
    "X": (1.0, 0.0, 0.0),
    "Y": (0.0, 1.0, 0.0),
    "Z": (0.0, 0.0, 1.0),
}
ALL_SPIN_AXIS_NAMES = tuple(SPIN_AXIS_VECTORS)


def load_model_spin_axes(path: Path) -> dict[str, tuple[str, ...]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("model spin-axis config must be a JSON object")

    rules = {}
    for model_name, model_config in data.items():
        if not isinstance(model_config, dict):
            raise ValueError(f"spin-axis config for {model_name!r} must be an object")
        axes = model_config.get("spin_axes")
        if not isinstance(axes, list) or not axes:
            raise ValueError(f"spin_axes for {model_name!r} must be a non-empty list")
        axis_names = []
        for axis in axes:
            if not isinstance(axis, str) or axis.upper() not in SPIN_AXIS_VECTORS:
                allowed = ", ".join(ALL_SPIN_AXIS_NAMES)
                raise ValueError(
                    f"invalid spin axis {axis!r} for {model_name!r}; use {allowed}"
                )
            normalized_axis = axis.upper()
            if normalized_axis not in axis_names:
                axis_names.append(normalized_axis)
        rules[model_name] = tuple(axis_names)
    return rules


def spin_axis_options(
    model_name: str,
    model_spin_axes: Mapping[str, tuple[str, ...]],
) -> tuple[tuple[float, float, float], ...]:
    axis_names = model_spin_axes.get(model_name, ALL_SPIN_AXIS_NAMES)
    return tuple(SPIN_AXIS_VECTORS[name] for name in axis_names)


def sample_spin_axis(
    rng: Random,
    model_name: str,
    model_spin_axes: Mapping[str, tuple[str, ...]],
) -> tuple[float, float, float]:
    return rng.choice(spin_axis_options(model_name, model_spin_axes))


def is_rotating(
    period_s: float,
    min_period_s: float = MIN_ROTATION_PERIOD_S,
    max_period_s: float = ROTATION_PERIOD_CUTOFF_S,
) -> bool:
    if not isfinite(period_s) or period_s < 0.0:
        raise ValueError("period_s must be a finite non-negative value")
    if not isfinite(min_period_s) or not isfinite(max_period_s):
        raise ValueError("spin period limits must be finite")
    if min_period_s <= 0.0 or max_period_s < min_period_s:
        raise ValueError("min_period_s must be positive and not exceed max_period_s")
    if 0.0 < period_s < min_period_s:
        raise ValueError(
            f"rotating periods below {min_period_s:g} seconds are excluded"
        )
    if period_s > max_period_s:
        raise ValueError(
            f"periods above {max_period_s:g} seconds are excluded"
        )
    return 0.0 < period_s <= max_period_s


def spin_phase_rad(
    period_s: float,
    time_s: float,
    initial_phase_rad: float = 0.0,
    min_period_s: float = MIN_ROTATION_PERIOD_S,
    max_period_s: float = ROTATION_PERIOD_CUTOFF_S,
) -> float:
    if not isfinite(time_s) or not isfinite(initial_phase_rad):
        raise ValueError("time_s and initial_phase_rad must be finite")
    if not is_rotating(period_s, min_period_s, max_period_s):
        return initial_phase_rad % tau
    return (initial_phase_rad + tau * time_s / period_s) % tau


def precession_phase_rad(
    period_s: float,
    time_s: float,
    initial_phase_rad: float = 0.0,
) -> float:
    if not all(isfinite(value) for value in (period_s, time_s, initial_phase_rad)):
        raise ValueError("period_s, time_s, and initial_phase_rad must be finite")
    if period_s <= 0.0:
        raise ValueError("precession period_s must be positive")
    return (initial_phase_rad + tau * time_s / period_s) % tau


def sample_precession_parameters(
    rng: Random,
    rotating: bool,
    angle_min_deg: float,
    angle_max_deg: float,
    period_min_s: float,
    period_max_s: float,
) -> tuple[float, float, float]:
    if not rotating:
        return 0.0, 0.0, 0.0
    angle_deg = rng.uniform(angle_min_deg, angle_max_deg)
    period_s = rng.uniform(period_min_s, period_max_s)
    phase_rad = rng.random() * tau
    return angle_deg, period_s, phase_rad


def sample_spin_period_s(
    rng: Random,
    rotating: bool | None = None,
    min_period_s: float = MIN_ROTATION_PERIOD_S,
    max_period_s: float = ROTATION_PERIOD_CUTOFF_S,
) -> float:
    """Return 0 s for a static satellite or a period inside the configured window."""
    if rotating is None:
        rotating = bool(rng.randrange(2))
    if not rotating:
        return 0.0
    if min_period_s <= 0.0 or max_period_s < min_period_s:
        raise ValueError("min_period_s must be positive and not exceed max_period_s")
    return rng.uniform(min_period_s, max_period_s)