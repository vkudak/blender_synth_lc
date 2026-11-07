from math import asin, atan2, cos, sin, sqrt, tau
from random import Random

from .orbit import EARTH_EQUATORIAL_RADIUS_M, Vector3

SUN_RADIUS_M = 695_700_000.0
SUN_DISTANCE_M = 149_597_870_700.0
SUNLIT = "sunlit"
PENUMBRA = "penumbra"
UMBRA = "umbra"


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


def solar_illumination_fraction(
    position_m: Vector3,
    sun_direction: Vector3,
    earth_radius_m: float = EARTH_EQUATORIAL_RADIUS_M,
    sun_radius_m: float = SUN_RADIUS_M,
    sun_distance_m: float = SUN_DISTANCE_M,
) -> float:
    """Return the visible fraction of the solar disk using conical shadow geometry."""
    sun_length = sqrt(sum(component**2 for component in sun_direction))
    if sun_length == 0.0:
        raise ValueError("sun_direction must be a non-zero vector")
    if earth_radius_m <= 0.0 or sun_radius_m <= 0.0 or sun_distance_m <= sun_radius_m:
        raise ValueError("Earth radius, Sun radius, and Sun distance must be positive")

    unit_sun = tuple(component / sun_length for component in sun_direction)
    position_length = sqrt(sum(component**2 for component in position_m))
    if position_length <= earth_radius_m:
        raise ValueError("position_m must be outside Earth")

    earth_direction = tuple(-component / position_length for component in position_m)
    sun_position = tuple(
        sun_distance_m * unit_sun[axis] - position_m[axis] for axis in range(3)
    )
    satellite_to_sun_distance = sqrt(sum(component**2 for component in sun_position))
    sun_from_satellite = tuple(
        component / satellite_to_sun_distance for component in sun_position
    )
    cosine_separation = sum(
        earth_direction[axis] * sun_from_satellite[axis] for axis in range(3)
    )
    sine_separation = sqrt(
        sum(
            (
                earth_direction[(axis + 1) % 3] * sun_from_satellite[(axis + 2) % 3]
                - earth_direction[(axis + 2) % 3] * sun_from_satellite[(axis + 1) % 3]
            )
            ** 2
            for axis in range(3)
        )
    )
    separation = atan2(sine_separation, cosine_separation)
    earth_angular_radius = asin(earth_radius_m / position_length)
    sun_angular_radius = asin(sun_radius_m / satellite_to_sun_distance)

    if separation >= earth_angular_radius + sun_angular_radius:
        return 1.0
    if separation <= earth_angular_radius - sun_angular_radius:
        return 0.0

    distance_squared = separation**2
    earth_radius_squared = earth_angular_radius**2
    sun_radius_squared = sun_angular_radius**2
    earth_angle = acos_clamped(
        (distance_squared + earth_radius_squared - sun_radius_squared)
        / (2.0 * separation * earth_angular_radius)
    )
    sun_angle = acos_clamped(
        (distance_squared + sun_radius_squared - earth_radius_squared)
        / (2.0 * separation * sun_angular_radius)
    )
    overlap_area = (
        earth_radius_squared * earth_angle
        + sun_radius_squared * sun_angle
        - 0.5
        * sqrt(
            max(
                0.0,
                (-separation + earth_angular_radius + sun_angular_radius)
                * (separation + earth_angular_radius - sun_angular_radius)
                * (separation - earth_angular_radius + sun_angular_radius)
                * (separation + earth_angular_radius + sun_angular_radius),
            )
        )
    )
    visible_fraction = 1.0 - overlap_area / (tau * sun_radius_squared / 2.0)
    return min(1.0, max(0.0, visible_fraction))


def acos_clamped(value: float) -> float:
    from math import acos

    return acos(min(1.0, max(-1.0, value)))


def shadow_state(position_m: Vector3, sun_direction: Vector3) -> str:
    fraction = solar_illumination_fraction(position_m, sun_direction)
    if fraction <= 0.0:
        return UMBRA
    if fraction < 1.0:
        return PENUMBRA
    return SUNLIT


def is_eclipsed(
    position_m: Vector3,
    sun_direction: Vector3,
    earth_radius_m: float = EARTH_EQUATORIAL_RADIUS_M,
) -> bool:
    """Return True when Earth partially or fully occults the solar disk."""
    return solar_illumination_fraction(
        position_m, sun_direction, earth_radius_m=earth_radius_m
    ) < 1.0


def sunlit_pass_exists(positions_m: tuple[Vector3, ...], sun_direction: Vector3) -> bool:
    return any(not is_eclipsed(position, sun_direction) for position in positions_m)


def eclipse_fraction(positions_m: tuple[Vector3, ...], sun_direction: Vector3) -> float:
    if not positions_m:
        raise ValueError("positions_m must not be empty")
    return sum(is_eclipsed(position, sun_direction) for position in positions_m) / len(
        positions_m
    )
