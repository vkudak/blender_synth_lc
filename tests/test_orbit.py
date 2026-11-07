import math
import unittest
from random import Random
from unittest.mock import patch

from blender_synth_lc.orbit import (
    EARTH_EQUATORIAL_RADIUS_M,
    CircularOrbit,
    GroundObserver,
    PassSample,
    VisiblePass,
    align_orbit_for_pass,
    longest_visible_window,
    look_angles,
    observer_position_ecef,
    observer_position_eci,
    sample_circular_orbit,
    sample_ground_observer,
    sample_pass_window,
    sample_visible_pass,
    select_visible_window,
)


class GroundObserverTests(unittest.TestCase):
    def test_inertial_site_rotates_once_per_sidereal_day(self):
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)

        quarter_day = observer_position_eci(observer, 86164.0905 / 4.0)
        full_day = observer_position_eci(observer, 86164.0905)

        self.assertAlmostEqual(quarter_day[0], 0.0, places=6)
        self.assertAlmostEqual(quarter_day[1], EARTH_EQUATORIAL_RADIUS_M)
        self.assertAlmostEqual(full_day[0], EARTH_EQUATORIAL_RADIUS_M)
        self.assertAlmostEqual(full_day[1], 0.0, places=6)

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
    def test_look_angles_account_for_rotating_observer_and_horizon(self):
        orbit = CircularOrbit(800_000.0, 0.0, 0.0, 0.0)
        observer = GroundObserver(0.0, 0.0)
        time_s = 90.0
        relative_angle = (orbit.mean_motion_rad_s - 2.0 * math.pi / 86164.0905) * time_s
        east = orbit.radius_m * math.sin(relative_angle)
        up = orbit.radius_m * math.cos(relative_angle) - EARTH_EQUATORIAL_RADIUS_M

        azimuth, elevation, range_m = look_angles(orbit, observer, time_s)

        self.assertAlmostEqual(azimuth, 90.0)
        self.assertAlmostEqual(elevation, math.degrees(math.atan2(up, east)))
        self.assertAlmostEqual(range_m, math.hypot(east, up))

    def test_alignment_minimizes_range_for_moving_observer(self):
        observer = GroundObserver(20.0, 0.0)
        orbit = CircularOrbit(800_000.0, 55.0, 0.0, 0.0)
        visible_pass = align_orbit_for_pass(orbit, observer, minimum_elevation_deg=0.0)

        self.assertIsNotNone(visible_pass)
        earlier_range = look_angles(visible_pass.orbit, observer, -0.1)[2]
        later_range = look_angles(visible_pass.orbit, observer, 0.1)[2]
        self.assertAlmostEqual(earlier_range, later_range, places=3)
        self.assertLess(visible_pass.closest_range_m, earlier_range)

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
        self.assertGreaterEqual(first.closest_elevation_deg, 20.0)

    def test_visible_pass_sampler_retries_when_trim_exceeds_fifteen_percent(self):
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)
        orbit = CircularOrbit(500_000.0, 0.0, 0.0, 0.0)
        visible_pass = VisiblePass(orbit, 90.0, 500_000.0, 20.0)
        all_visible = self._samples_with_visibility((True,) * 20)
        too_much_trim = self._samples_with_visibility((False,) * 4 + (True,) * 16)

        with (
            patch("blender_synth_lc.orbit.sample_circular_orbit", return_value=orbit),
            patch("blender_synth_lc.orbit.align_orbit_for_pass", return_value=visible_pass),
            patch(
                "blender_synth_lc.orbit.sample_pass_window",
                side_effect=(too_much_trim, all_visible),
            ) as sample_window,
        ):
            result = sample_visible_pass(
                Random(5),
                observer,
                max_attempts=2,
                duration_s=20.0,
                cadence_s=1.0,
            )

        self.assertEqual(result, visible_pass)
        self.assertEqual(sample_window.call_count, 2)

    def test_visible_pass_sampler_reports_trim_limit_exhaustion(self):
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)
        orbit = CircularOrbit(500_000.0, 0.0, 0.0, 0.0)
        visible_pass = VisiblePass(orbit, 90.0, 500_000.0, 20.0)
        too_much_trim = self._samples_with_visibility((False,) * 4 + (True,) * 16)

        with (
            patch("blender_synth_lc.orbit.sample_circular_orbit", return_value=orbit),
            patch("blender_synth_lc.orbit.align_orbit_for_pass", return_value=visible_pass),
            patch("blender_synth_lc.orbit.sample_pass_window", return_value=too_much_trim),
        ):
            with self.assertRaisesRegex(RuntimeError, "at least 85%"):
                sample_visible_pass(
                    Random(5),
                    observer,
                    max_attempts=2,
                    duration_s=20.0,
                    cadence_s=1.0,
                )

    def test_visible_window_accepts_exactly_fifteen_percent_trim(self):
        samples = self._samples_with_visibility((False,) * 3 + (True,) * 17)

        selected = select_visible_window(samples)

        self.assertEqual(len(selected), 17)

    def test_visible_window_rejects_trim_over_fifteen_percent(self):
        samples = self._samples_with_visibility((False,) * 4 + (True,) * 16)

        self.assertIsNone(select_visible_window(samples))

    @staticmethod
    def _samples_with_visibility(visibility):
        return tuple(
            PassSample(
                time_from_closest_approach_s=float(index),
                position_m=(0.0, 0.0, 0.0),
                velocity_m_s=(0.0, 0.0, 0.0),
                azimuth_deg=0.0,
                elevation_deg=20.0 if visible else 19.0,
                range_m=1.0,
                visible=visible,
            )
            for index, visible in enumerate(visibility)
        )

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

    def test_three_minute_window_uses_rotating_observer_at_each_sample(self):
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)
        orbit = CircularOrbit(800_000.0, 0.0, 0.0, 0.0)
        visible_pass = align_orbit_for_pass(orbit, observer)

        samples = sample_pass_window(visible_pass, observer, duration_s=180.0, cadence_s=30.0)

        self.assertEqual(len(samples), 7)
        for sample in samples:
            angle = (orbit.mean_motion_rad_s - 2.0 * math.pi / 86164.0905) * (
                sample.time_from_closest_approach_s
            )
            east = orbit.radius_m * math.sin(angle)
            up = orbit.radius_m * math.cos(angle) - EARTH_EQUATORIAL_RADIUS_M
            self.assertAlmostEqual(sample.range_m, math.hypot(east, up))
            self.assertAlmostEqual(sample.elevation_deg, math.degrees(math.atan2(up, abs(east))))
            self.assertEqual(sample.visible, sample.elevation_deg >= 20.0)

    def test_pass_window_includes_samples_exactly_at_elevation_mask(self):
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)
        visible_pass = VisiblePass(
            CircularOrbit(500_000.0, 0.0, 0.0, 0.0),
            closest_elevation_deg=20.0,
            closest_range_m=500_000.0,
            minimum_elevation_deg=20.0,
        )

        with patch(
            "blender_synth_lc.orbit.look_angles",
            return_value=(0.0, 20.0, 500_000.0),
        ):
            samples = sample_pass_window(
                visible_pass, observer, duration_s=2.0, cadence_s=1.0
            )

        self.assertTrue(all(sample.visible for sample in samples))

    def test_pass_window_excludes_samples_just_below_elevation_mask(self):
        observer = GroundObserver(latitude_deg=0.0, longitude_deg=0.0)
        visible_pass = VisiblePass(
            CircularOrbit(500_000.0, 0.0, 0.0, 0.0),
            closest_elevation_deg=20.0,
            closest_range_m=500_000.0,
            minimum_elevation_deg=20.0,
        )

        with patch(
            "blender_synth_lc.orbit.look_angles",
            return_value=(0.0, 19.999, 500_000.0),
        ):
            samples = sample_pass_window(
                visible_pass, observer, duration_s=2.0, cadence_s=1.0
            )

        self.assertTrue(all(not sample.visible for sample in samples))

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