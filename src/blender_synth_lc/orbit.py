from dataclasses import dataclass
from math import acos, atan2, cos, degrees, hypot, isfinite, radians, sin, sqrt
from random import Random


EARTH_MU_M3_S2 = 3.986004418e14
EARTH_EQUATORIAL_RADIUS_M = 6_378_137.0
EARTH_FLATTENING = 1.0 / 298.257223563
EARTH_ECCENTRICITY_SQUARED = EARTH_FLATTENING * (2.0 - EARTH_FLATTENING)
MIN_ORBIT_ALTITUDE_M = 300_000.0
MAX_ORBIT_ALTITUDE_M = 3_000_000.0

Vector3 = tuple[float, float, float]


@dataclass(frozen=True)
class GroundObserver:
    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0

    def __post_init__(self):
        if not -90.0 <= self.latitude_deg <= 90.0:
            raise ValueError("latitude_deg must be between -90 and 90")
        if not -180.0 <= self.longitude_deg <= 180.0:
            raise ValueError("longitude_deg must be between -180 and 180")
        if not isfinite(self.altitude_m) or self.altitude_m < -1000.0:
            raise ValueError("altitude_m must be finite and at least -1000")


@dataclass(frozen=True)
class CircularOrbit:
    altitude_m: float
    inclination_deg: float
    raan_deg: float
    phase_deg: float

    def __post_init__(self):
        if not MIN_ORBIT_ALTITUDE_M <= self.altitude_m <= MAX_ORBIT_ALTITUDE_M:
            raise ValueError("altitude_m must be between 300 and 3000 km")
        if not 0.0 <= self.inclination_deg <= 180.0:
            raise ValueError("inclination_deg must be between 0 and 180")
        if not 0.0 <= self.raan_deg < 360.0:
            raise ValueError("raan_deg must be in [0, 360)")
        if not 0.0 <= self.phase_deg < 360.0:
            raise ValueError("phase_deg must be in [0, 360)")

    @property
    def radius_m(self) -> float:
        return EARTH_EQUATORIAL_RADIUS_M + self.altitude_m

    @property
    def mean_motion_rad_s(self) -> float:
        return sqrt(EARTH_MU_M3_S2 / self.radius_m**3)

    @property
    def period_s(self) -> float:
        from math import tau

        return tau / self.mean_motion_rad_s

    def position_velocity_eci(self, time_s: float) -> tuple[Vector3, Vector3]:
        """Return inertial position (m) and velocity (m/s) from the orbit epoch."""
        phase = radians(self.phase_deg) + self.mean_motion_rad_s * time_s
        inclination = radians(self.inclination_deg)
        raan = radians(self.raan_deg)
        cos_phase = cos(phase)
        sin_phase = sin(phase)
        cos_inclination = cos(inclination)
        sin_inclination = sin(inclination)
        cos_raan = cos(raan)
        sin_raan = sin(raan)

        position_orbit = (
            self.radius_m * cos_phase,
            self.radius_m * sin_phase,
            0.0,
        )
        speed = sqrt(EARTH_MU_M3_S2 / self.radius_m)
        velocity_orbit = (-speed * sin_phase, speed * cos_phase, 0.0)

        def rotate_to_eci(vector: Vector3) -> Vector3:
            x_orbit, y_orbit, z_orbit = vector
            x_inclined = x_orbit
            y_inclined = cos_inclination * y_orbit - sin_inclination * z_orbit
            z_inclined = sin_inclination * y_orbit + cos_inclination * z_orbit
            return (
                cos_raan * x_inclined - sin_raan * y_inclined,
                sin_raan * x_inclined + cos_raan * y_inclined,
                z_inclined,
            )

        return rotate_to_eci(position_orbit), rotate_to_eci(velocity_orbit)


@dataclass(frozen=True)
class VisiblePass:
    orbit: CircularOrbit
    closest_elevation_deg: float
    closest_range_m: float
    minimum_elevation_deg: float


@dataclass(frozen=True)
class PassSample:
    time_from_closest_approach_s: float
    position_m: Vector3
    velocity_m_s: Vector3
    azimuth_deg: float
    elevation_deg: float
    range_m: float
    visible: bool


def sample_ground_observer(rng: Random, altitude_m: float = 0.0) -> GroundObserver:
    """Sample a point uniformly by area on a spherical latitude/longitude grid."""
    latitude = degrees(asin_clamped(2.0 * rng.random() - 1.0))
    longitude = rng.uniform(-180.0, 180.0)
    return GroundObserver(latitude, longitude, altitude_m)


def asin_clamped(value: float) -> float:
    from math import asin

    return asin(max(-1.0, min(1.0, value)))


def observer_position_ecef(observer: GroundObserver) -> Vector3:
    """Convert WGS-84 geodetic coordinates to Earth-fixed Cartesian meters."""
    latitude = radians(observer.latitude_deg)
    longitude = radians(observer.longitude_deg)
    sin_latitude = sin(latitude)
    cos_latitude = cos(latitude)
    prime_vertical_radius = EARTH_EQUATORIAL_RADIUS_M / sqrt(
        1.0 - EARTH_ECCENTRICITY_SQUARED * sin_latitude**2
    )

    return (
        (prime_vertical_radius + observer.altitude_m)
        * cos_latitude
        * cos(longitude),
        (prime_vertical_radius + observer.altitude_m)
        * cos_latitude
        * sin(longitude),
        (prime_vertical_radius * (1.0 - EARTH_ECCENTRICITY_SQUARED)
         + observer.altitude_m)
        * sin_latitude,
    )


def observer_position_fixed_frame(observer: GroundObserver) -> Vector3:
    """Return the stationary ground site in the simplified Earth-fixed frame."""
    return observer_position_ecef(observer)


def look_angles(
    orbit: CircularOrbit,
    observer: GroundObserver,
    time_s: float,
) -> tuple[float, float, float]:
    """Return azimuth, elevation, and range while Earth rotation is ignored."""
    satellite, _ = orbit.position_velocity_eci(time_s)
    observer_position = observer_position_fixed_frame(observer)
    line_of_sight = tuple(
        satellite[axis] - observer_position[axis] for axis in range(3)
    )
    range_m = sqrt(sum(component**2 for component in line_of_sight))
    if range_m == 0.0:
        raise ValueError("observer and satellite positions cannot coincide")

    latitude = radians(observer.latitude_deg)
    longitude = radians(observer.longitude_deg)
    east_ecef = (-sin(longitude), cos(longitude), 0.0)
    north_ecef = (
        -sin(latitude) * cos(longitude),
        -sin(latitude) * sin(longitude),
        cos(latitude),
    )
    up_ecef = (
        cos(latitude) * cos(longitude),
        cos(latitude) * sin(longitude),
        sin(latitude),
    )
    east_component = sum(line_of_sight[i] * east_ecef[i] for i in range(3))
    north_component = sum(line_of_sight[i] * north_ecef[i] for i in range(3))
    up_component = sum(line_of_sight[i] * up_ecef[i] for i in range(3))
    azimuth_deg = degrees(atan2(east_component, north_component)) % 360.0
    elevation_deg = degrees(atan2(up_component, hypot(east_component, north_component)))
    return azimuth_deg, elevation_deg, range_m


def sample_circular_orbit(
    rng: Random,
    altitude_min_m: float = MIN_ORBIT_ALTITUDE_M,
    altitude_max_m: float = MAX_ORBIT_ALTITUDE_M,
    inclination_min_deg: float = 0.0,
    inclination_max_deg: float = 180.0,
) -> CircularOrbit:
    """Sample orbit altitude uniformly and orientation within the given bounds."""
    if not MIN_ORBIT_ALTITUDE_M <= altitude_min_m <= altitude_max_m <= MAX_ORBIT_ALTITUDE_M:
        raise ValueError("orbit altitude range must stay within 300-3000 km")
    if not 0.0 <= inclination_min_deg <= inclination_max_deg <= 180.0:
        raise ValueError("inclination range must stay within 0-180 deg")
    if inclination_min_deg == 0.0 and inclination_max_deg == 180.0:
        inclination = degrees(acos(rng.uniform(-1.0, 1.0)))
    else:
        inclination = rng.uniform(inclination_min_deg, inclination_max_deg)
    return CircularOrbit(
        altitude_m=rng.uniform(altitude_min_m, altitude_max_m),
        inclination_deg=inclination,
        raan_deg=rng.uniform(0.0, 360.0),
        phase_deg=rng.uniform(0.0, 360.0),
    )


def align_orbit_for_pass(
    orbit: CircularOrbit,
    observer: GroundObserver,
    minimum_elevation_deg: float = 10.0,
) -> VisiblePass | None:
    """Set phase so the orbit reaches its closest point to a fixed ground site."""
    if not isfinite(minimum_elevation_deg) or not 0.0 <= minimum_elevation_deg < 90.0:
        raise ValueError("minimum_elevation_deg must be finite and in [0, 90)")

    inclination = radians(orbit.inclination_deg)
    raan = radians(orbit.raan_deg)
    plane_normal = (
        sin(raan) * sin(inclination),
        -cos(raan) * sin(inclination),
        cos(inclination),
    )
    site_position = observer_position_fixed_frame(observer)
    normal_projection = sum(
        site_position[axis] * plane_normal[axis] for axis in range(3)
    )
    site_projection = tuple(
        site_position[axis] - normal_projection * plane_normal[axis]
        for axis in range(3)
    )

    if sqrt(sum(component**2 for component in site_projection)) < 1e-9:
        return None

    first_axis = (cos(raan), sin(raan), 0.0)
    second_axis = (
        -sin(raan) * cos(inclination),
        cos(raan) * cos(inclination),
        sin(inclination),
    )
    phase = atan2(
        sum(site_projection[i] * second_axis[i] for i in range(3)),
        sum(site_projection[i] * first_axis[i] for i in range(3)),
    )
    aligned_orbit = CircularOrbit(
        altitude_m=orbit.altitude_m,
        inclination_deg=orbit.inclination_deg,
        raan_deg=orbit.raan_deg,
        phase_deg=degrees(phase) % 360.0,
    )
    _, elevation, range_m = look_angles(aligned_orbit, observer, 0.0)
    if elevation < minimum_elevation_deg:
        return None

    return VisiblePass(
        orbit=aligned_orbit,
        closest_elevation_deg=elevation,
        closest_range_m=range_m,
        minimum_elevation_deg=minimum_elevation_deg,
    )


def sample_visible_pass(
    rng: Random,
    observer: GroundObserver,
    minimum_elevation_deg: float = 10.0,
    max_attempts: int = 100,
    altitude_min_m: float = MIN_ORBIT_ALTITUDE_M,
    altitude_max_m: float = MAX_ORBIT_ALTITUDE_M,
    inclination_min_deg: float = 0.0,
    inclination_max_deg: float = 180.0,
) -> VisiblePass:
    """Sample a circular orbit whose closest approach clears the elevation mask."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")

    for _ in range(max_attempts):
        candidate = align_orbit_for_pass(
            sample_circular_orbit(
                rng,
                altitude_min_m=altitude_min_m,
                altitude_max_m=altitude_max_m,
                inclination_min_deg=inclination_min_deg,
                inclination_max_deg=inclination_max_deg,
            ),
            observer,
            minimum_elevation_deg,
        )
        if candidate is not None:
            return candidate

    raise RuntimeError(
        f"No visible pass found after {max_attempts} orbit samples; "
        "lower the elevation mask or increase max_attempts"
    )


def sample_pass_window(
    visible_pass: VisiblePass,
    observer: GroundObserver,
    duration_s: float = 300.0,
    cadence_s: float = 1.0,
) -> tuple[PassSample, ...]:
    """Sample satellite motion symmetrically around closest approach at t=0."""
    if not isfinite(duration_s) or duration_s <= 0.0:
        raise ValueError("duration_s must be a finite positive value")
    if not isfinite(cadence_s) or cadence_s <= 0.0:
        raise ValueError("cadence_s must be a finite positive value")

    intervals_float = duration_s / cadence_s
    intervals = round(intervals_float)
    if intervals < 1 or abs(intervals_float - intervals) > 1e-9:
        raise ValueError("duration_s must be an integer multiple of cadence_s")

    start_time_s = -duration_s / 2.0
    samples = []
    for sample_index in range(intervals + 1):
        time_s = start_time_s + sample_index * cadence_s
        position, velocity = visible_pass.orbit.position_velocity_eci(time_s)
        azimuth, elevation, range_m = look_angles(
            visible_pass.orbit,
            observer,
            time_s,
        )
        samples.append(
            PassSample(
                time_from_closest_approach_s=time_s,
                position_m=position,
                velocity_m_s=velocity,
                azimuth_deg=azimuth,
                elevation_deg=elevation,
                range_m=range_m,
                visible=elevation >= visible_pass.minimum_elevation_deg,
            )
        )
    return tuple(samples)