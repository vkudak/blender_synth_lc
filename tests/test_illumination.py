from random import Random

from blender_synth_lc.illumination import (
    is_eclipsed,
    sample_sun_direction,
    sunlit_pass_exists,
)
from blender_synth_lc.orbit import EARTH_EQUATORIAL_RADIUS_M


def test_dayside_satellite_is_not_eclipsed():
    position = (EARTH_EQUATORIAL_RADIUS_M + 800_000.0, 0.0, 0.0)
    sun_direction = (1.0, 0.0, 0.0)

    assert not is_eclipsed(position, sun_direction)


def test_nightside_satellite_behind_earth_is_eclipsed():
    position = (-EARTH_EQUATORIAL_RADIUS_M - 800_000.0, 0.0, 0.0)
    sun_direction = (1.0, 0.0, 0.0)

    assert is_eclipsed(position, sun_direction)


def test_nightside_satellite_beside_earth_is_sunlit():
    position = (
        -EARTH_EQUATORIAL_RADIUS_M - 800_000.0,
        2.0 * EARTH_EQUATORIAL_RADIUS_M,
        0.0,
    )
    sun_direction = (1.0, 0.0, 0.0)

    assert not is_eclipsed(position, sun_direction)


def test_sun_direction_sampling_is_seeded():
    assert sample_sun_direction(Random(7)) == sample_sun_direction(Random(7))


def test_sunlit_pass_requires_at_least_one_visible_sample():
    night = (-EARTH_EQUATORIAL_RADIUS_M - 800_000.0, 0.0, 0.0)
    day = (EARTH_EQUATORIAL_RADIUS_M + 800_000.0, 0.0, 0.0)
    sun_direction = (1.0, 0.0, 0.0)

    assert not sunlit_pass_exists((night, night), sun_direction)
    assert sunlit_pass_exists((night, day), sun_direction)
