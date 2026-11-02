from math import isfinite, tau

from . import MIN_ROTATION_PERIOD_S, ROTATION_PERIOD_CUTOFF_S


def is_rotating(period_s: float) -> bool:
    if not isfinite(period_s) or period_s < 0.0:
        raise ValueError("period_s must be a finite non-negative value")
    if 0.0 < period_s < MIN_ROTATION_PERIOD_S:
        raise ValueError(
            f"rotating periods below {MIN_ROTATION_PERIOD_S:g} seconds are excluded"
        )
    if period_s > ROTATION_PERIOD_CUTOFF_S:
        raise ValueError(
            f"periods above {ROTATION_PERIOD_CUTOFF_S:g} seconds are excluded"
        )
    return 0.0 < period_s <= ROTATION_PERIOD_CUTOFF_S


def spin_phase_rad(period_s: float, time_s: float, initial_phase_rad: float = 0.0) -> float:
    if not isfinite(time_s) or not isfinite(initial_phase_rad):
        raise ValueError("time_s and initial_phase_rad must be finite")
    if not is_rotating(period_s):
        return initial_phase_rad % tau
    return (initial_phase_rad + tau * time_s / period_s) % tau