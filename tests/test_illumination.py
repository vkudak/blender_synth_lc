from random import Random

from blender_synth_lc.illumination import (
    eclipse_fraction,
    is_eclipsed,
    sample_sun_direction,
    shadow_state,
    solar_illumination_fraction,
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


def test_penumbra_has_partial_solar_illumination_and_counts_as_eclipsed():
    position = (
        -7_000_000.0,
        EARTH_EQUATORIAL_RADIUS_M + 20_000.0,
        0.0,
    )
    sun_direction = (1.0, 0.0, 0.0)

    fraction = solar_illumination_fraction(position, sun_direction)

    assert 0.0 < fraction < 1.0
    assert shadow_state(position, sun_direction) == "penumbra"
    assert is_eclipsed(position, sun_direction)


def test_umbra_and_sunlight_have_expected_illumination_fractions():
    night = (-EARTH_EQUATORIAL_RADIUS_M - 800_000.0, 0.0, 0.0)
    day = (EARTH_EQUATORIAL_RADIUS_M + 800_000.0, 0.0, 0.0)

    assert solar_illumination_fraction(night, (1.0, 0.0, 0.0)) == 0.0
    assert shadow_state(night, (1.0, 0.0, 0.0)) == "umbra"
    assert solar_illumination_fraction(day, (1.0, 0.0, 0.0)) == 1.0
    assert shadow_state(day, (1.0, 0.0, 0.0)) == "sunlit"


def test_sun_direction_sampling_is_seeded():
    assert sample_sun_direction(Random(7)) == sample_sun_direction(Random(7))


def test_sunlit_pass_requires_at_least_one_visible_sample():
    night = (-EARTH_EQUATORIAL_RADIUS_M - 800_000.0, 0.0, 0.0)
    day = (EARTH_EQUATORIAL_RADIUS_M + 800_000.0, 0.0, 0.0)
    sun_direction = (1.0, 0.0, 0.0)

    assert not sunlit_pass_exists((night, night), sun_direction)
    assert sunlit_pass_exists((night, day), sun_direction)


def test_eclipse_fraction_counts_shadowed_samples():
    night = (-EARTH_EQUATORIAL_RADIUS_M - 800_000.0, 0.0, 0.0)
    penumbra = (-7_000_000.0, EARTH_EQUATORIAL_RADIUS_M + 20_000.0, 0.0)
    day = (EARTH_EQUATORIAL_RADIUS_M + 800_000.0, 0.0, 0.0)

    assert eclipse_fraction((night, day, day, day, day, day, day), (1.0, 0.0, 0.0)) == 1 / 7
    assert eclipse_fraction((penumbra, day, day, day, day, day, day), (1.0, 0.0, 0.0)) == 1 / 7
