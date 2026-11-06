import math
import unittest
from random import Random

from blender_synth_lc.orbit import (
    EARTH_EQUATORIAL_RADIUS_M,
    CircularOrbit,
    GroundObserver,
    PassSample,
    align_orbit_for_pass,
    longest_visible_window,
    look_angles,
    observer_position_ecef,
    sample_circular_orbit,
    sample_ground_observer,
    sample_pass_window,
    sample_visible_pass,
)


class GroundObserverTests(unittest.TestCase):
    def test_equator_and_prime_meridian_is_wgs84_equatorial_radius(self):
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)

        position = observer_position_ecef(observer)

        self.assertAlmostEqual(position[0], EARTH_EQUATORIAL_RADIUS_M)
        self.assertAlmostEqual(position[1], 0.0)
        self.assertAlmostEqual(position[2], 0.0)

    def test_invalid_latitude_is_rejected(self):
        with self.assertRaises(ValueError):
            GroundObserver(latitude_deg=91.0, longitude_deg=0.0)

    def test_random_observer_sampling_is_seeded(self):
        first = sample_ground_observer(Random(12))
        second = sample_ground_observer(Random(12))

        self.assertEqual(first, second)
        self.assertTrue(-90.0 <= first.latitude_deg <= 90.0)
        self.assertTrue(-180.0 <= first.longitude_deg <= 180.0)


class CircularOrbitTests(unittest.TestCase):
    def test_position_and_velocity_have_expected_circular_orbit_magnitudes(self):
        orbit = CircularOrbit(
            altitude_m=500_000.0,
            inclination_deg=0.0,
            raan_deg=0.0,
            phase_deg=0.0,
        )

        position, velocity = orbit.position_velocity_eci(0.0)

        self.assertAlmostEqual(math.sqrt(sum(value**2 for value in position)), orbit.radius_m)
        self.assertAlmostEqual(math.sqrt(sum(value**2 for value in velocity)), math.sqrt(orbit.mean_motion_rad_s**2 * orbit.radius_m**2))
        self.assertAlmostEqual(position[0], orbit.radius_m)
        self.assertAlmostEqual(position[1], 0.0)
        self.assertAlmostEqual(position[2], 0.0)

    def test_position_repeats_after_one_orbital_period(self):
        orbit = CircularOrbit(
            altitude_m=1_000_000.0,
            inclination_deg=56.0,
            raan_deg=129.0,
            phase_deg=87.0,
        )

        initial, _ = orbit.position_velocity_eci(0.0)
        after_period, _ = orbit.position_velocity_eci(orbit.period_s)

        for actual, expected in zip(after_period, initial):
            self.assertAlmostEqual(actual, expected, places=5)

    def test_altitude_outside_requested_range_is_rejected(self):
        with self.assertRaises(ValueError):
            CircularOrbit(altitude_m=299_999.0, inclination_deg=0.0, raan_deg=0.0, phase_deg=0.0)

    def test_seeded_orbit_is_reproducible_and_within_altitude_limits(self):
        first = sample_circular_orbit(Random(91))
        second = sample_circular_orbit(Random(91))

        self.assertEqual(first, second)
        self.assertTrue(300_000.0 <= first.altitude_m <= 3_000_000.0)

    def test_satellite_directly_over_observer_has_90_degree_elevation(self):
        orbit = CircularOrbit(
            altitude_m=500_000.0,
            inclination_deg=0.0,
            raan_deg=0.0,
            phase_deg=0.0,
        )
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)

        azimuth, elevation, range_m = look_angles(orbit, observer, 0.0)

        self.assertAlmostEqual(azimuth, 0.0)
        self.assertAlmostEqual(elevation, 90.0)
        self.assertAlmostEqual(range_m, 500_000.0)

    def test_pass_alignment_finds_overhead_equatorial_pass(self):
        orbit = CircularOrbit(
            altitude_m=500_000.0,
            inclination_deg=0.0,
            raan_deg=0.0,
            phase_deg=120.0,
        )
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)

        visible_pass = align_orbit_for_pass(orbit, observer)

        self.assertIsNotNone(visible_pass)
        self.assertAlmostEqual(visible_pass.closest_elevation_deg, 90.0)
        self.assertAlmostEqual(visible_pass.closest_range_m, 500_000.0)

    def test_orbit_plane_through_observer_has_no_unique_closest_phase(self):
        orbit = CircularOrbit(
            altitude_m=500_000.0,
            inclination_deg=90.0,
            raan_deg=90.0,
            phase_deg=0.0,
        )
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)

        self.assertIsNone(align_orbit_for_pass(orbit, observer))

    def test_visible_pass_sampler_obeys_elevation_mask_and_seed(self):
        observer = GroundObserver(latitude_deg=48.633, longitude_deg=22.33)

        first = sample_visible_pass(Random(33), observer, max_attempts=100)
        second = sample_visible_pass(Random(33), observer, max_attempts=100)

        self.assertEqual(first, second)
        self.assertGreaterEqual(first.closest_elevation_deg, 10.0)

    def test_pass_window_contains_moving_satellite_positions(self):
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)
        orbit = CircularOrbit(
            altitude_m=500_000.0,
            inclination_deg=0.0,
            raan_deg=0.0,
            phase_deg=0.0,
        )
        visible_pass = align_orbit_for_pass(orbit, observer)

        samples = sample_pass_window(
            visible_pass,
            observer,
            duration_s=120.0,
            cadence_s=30.0,
        )

        self.assertEqual(len(samples), 5)
        self.assertEqual(samples[2].time_from_closest_approach_s, 0.0)
        self.assertAlmostEqual(samples[2].elevation_deg, 90.0)
        self.assertNotEqual(samples[0].position_m, samples[-1].position_m)
        self.assertTrue(all(sample.range_m > 0.0 for sample in samples))

    def test_pass_window_requires_integer_cadence_count(self):
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)
        visible_pass = align_orbit_for_pass(
            CircularOrbit(500_000.0, 0.0, 0.0, 0.0),
            observer,
        )

        with self.assertRaises(ValueError):
            sample_pass_window(visible_pass, observer, duration_s=10.0, cadence_s=3.0)

    def test_longest_visible_window_selects_contiguous_samples(self):
        samples = tuple(
            PassSample(
                time_from_closest_approach_s=float(index - 3),
                position_m=(0.0, 0.0, 0.0),
                velocity_m_s=(0.0, 0.0, 0.0),
                azimuth_deg=0.0,
                elevation_deg=20.0 if visible else 0.0,
                range_m=1.0,
                visible=visible,
            )
            for index, visible in enumerate((True, False, True, True, True, False, True))
        )

        window = longest_visible_window(samples)

        self.assertEqual(
            tuple(sample.time_from_closest_approach_s for sample in window),
            (-1.0, 0.0, 1.0),
        )


if __name__ == "__main__":
    unittest.main()