from math import cos, sin, sqrt, tau
from random import Random

from .orbit import EARTH_EQUATORIAL_RADIUS_M, Vector3


def sample_unit_vector(rng: Random) -> Vector3:
    """Sample a direction uniformly on the sphere."""
    z_component = rng.uniform(-1.0, 1.0)
    azimuth = rng.uniform(0.0, tau)
    radial = sqrt(max(0.0, 1.0 - z_component * z_component))
    return (radial * cos(azimuth), radial * sin(azimuth), z_component)


def sample_sun_direction(rng: Random) -> Vector3:
    """Return a unit vector pointing from Earth toward the Sun."""
    return sample_unit_vector(rng)


def perpendicular_distance_to_axis(position_m: Vector3, axis_direction: Vector3) -> float:
    axis_length = sqrt(sum(component**2 for component in axis_direction))
    if axis_length == 0.0:
        raise ValueError("axis_direction must be a non-zero vector")
    unit_axis = tuple(component / axis_length for component in axis_direction)
    projection = sum(position_m[axis] * unit_axis[axis] for axis in range(3))
    perpendicular = tuple(
        position_m[axis] - projection * unit_axis[axis] for axis in range(3)
    )
    return sqrt(sum(component**2 for component in perpendicular))


def is_eclipsed(
    position_m: Vector3,
    sun_direction: Vector3,
    earth_radius_m: float = EARTH_EQUATORIAL_RADIUS_M,
) -> bool:
    """Return True when Earth occults the Sun in a cylindrical shadow model."""
    sun_length = sqrt(sum(component**2 for component in sun_direction))
    if sun_length == 0.0:
        raise ValueError("sun_direction must be a non-zero vector")
    if earth_radius_m <= 0.0:
        raise ValueError("earth_radius_m must be positive")

    unit_sun = tuple(component / sun_length for component in sun_direction)
    along_sun = sum(position_m[axis] * unit_sun[axis] for axis in range(3))
    if along_sun >= 0.0:
        return False
    return perpendicular_distance_to_axis(position_m, unit_sun) < earth_radius_m


def sunlit_pass_exists(positions_m: tuple[Vector3, ...], sun_direction: Vector3) -> bool:
    return any(not is_eclipsed(position, sun_direction) for position in positions_m)
