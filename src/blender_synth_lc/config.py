"""Load curve and dataset settings from INI files."""

from __future__ import annotations

import configparser
import json
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
import warnings

from . import MIN_ROTATION_PERIOD_S, ROTATION_PERIOD_CUTOFF_S
from .orbit import (
    DEFAULT_MINIMUM_ELEVATION_DEG,
    MAX_ORBIT_ALTITUDE_M,
    MINIMUM_ELEVATION_FLOOR_DEG,
    MIN_ORBIT_ALTITUDE_M,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BLENDER = "/home/vkudak/software/blender-4.5.15-linux-x64/blender"
DEVICES = ("auto", "cpu", "cuda", "optix")
DEFAULT_SKIP_MODELS = ("Topex_g.blend", "Topex_g3.blend")


@dataclass(frozen=True)
class SynthConfig:
    kind: str
    config_path: Path
    blender: Path
    model: Path | None
    models_dir: Path
    selected_models: tuple[str, ...]
    skip_models: tuple[str, ...]
    output: Path | None
    output_dir: Path
    seed: int
    device: str
    count: int
    workers: int
    observer_mode: str
    latitude_deg: float
    longitude_deg: float
    observer_altitude_m: float
    orbit_mode: str
    altitude_min_m: float
    altitude_max_m: float
    altitude_m: float
    inclination_min_deg: float
    inclination_max_deg: float
    inclination_deg: float
    raan_deg: float
    phase_deg: float
    align_for_pass: bool
    duration_s: float
    cadence_s: float
    minimum_elevation_deg: float
    max_pass_attempts: int
    attitude_mode: str
    spin_period_s: float
    spin_period_min_s: float
    spin_period_max_s: float
    rotating_fraction: float
    tumbling_fraction: float
    initial_phase_mode: str
    initial_phase_rad: float
    precession_angle_deg: float
    precession_period_s: float
    precession_phase_deg: float
    precession_fraction: float
    precession_angle_min_deg: float
    precession_angle_max_deg: float
    precession_period_min_s: float
    precession_period_max_s: float
    model_scale_min: float
    model_scale_max: float
    reference_snr: float
    bias_level: float
    readout_noise_std: float
    correlated_noise_std: float
    correlation_time_s: float
    saturation_level: float
    adc_bits: int
    sun_mode: str
    sun_direction: tuple[float, float, float]
    sun_energy: float
    max_eclipse_fraction: float
    resolution: int
    samples: int
    exposure: float
    script_output: Path | None
    scene_meters_per_unit: float


def load_config(path: Path, kind: str) -> SynthConfig:
    if kind not in {"curve", "dataset"}:
        raise ValueError("kind must be 'curve' or 'dataset'")
    config_path = path.expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    parser.read(config_path, encoding="utf-8")
    required = {"blender", "paths", "run", "observer", "orbit", "pass", "sun", "render"}
    if kind == "dataset":
        required.update(
            {"dataset", "dataset.period", "dataset.precession", "dataset.scale"}
        )
    else:
        required.add("attitude")
    missing = sorted(section for section in required if not parser.has_section(section))
    if missing:
        raise ValueError(f"{config_path} is missing sections: {', '.join(missing)}")
    if kind == "dataset" and parser.has_section("attitude"):
        raise ValueError("dataset config must use [dataset.period], not [attitude]")

    def get(section, option, fallback=None):
        if fallback is None:
            return parser.get(section, option)
        return parser.get(section, option, fallback=fallback)

    def getint(section, option, fallback):
        return parser.getint(section, option, fallback=fallback)

    def getfloat(section, option, fallback):
        return parser.getfloat(section, option, fallback=fallback)

    def getbool(section, option, fallback):
        return parser.getboolean(section, option, fallback=fallback)

    blender = _resolve_path(get("blender", "executable", DEFAULT_BLENDER), config_path)
    models_dir = _resolve_path(get("paths", "models_dir", "models"), config_path)
    model_value = get("paths", "model", fallback="").strip()
    model = _resolve_path(model_value, config_path) if model_value else None
    output_value = get("paths", "output", fallback="").strip()
    output = _resolve_path(output_value, config_path) if output_value else None
    output_dir = _resolve_path(
        get("paths", "output_dir", "reports/dataset" if kind == "dataset" else "reports"),
        config_path,
    )
    script_output_value = get("render", "script_output", fallback="").strip()
    script_output = (
        _resolve_path(script_output_value, config_path) if script_output_value else None
    )
    scene_meters_per_unit = getfloat("render", "scene_meters_per_unit", 1.0)
    reference_snr = getfloat("noise", "reference_snr", 50.0)
    bias_level = getfloat("noise", "bias_level", 0.0)
    readout_noise_std = getfloat("noise", "readout_noise_std", 0.0)
    correlated_noise_std = getfloat("noise", "correlated_noise_std", 0.0)
    correlation_time_s = getfloat("noise", "correlation_time_s", 0.0)
    saturation_level = getfloat("noise", "saturation_level", 0.0)
    adc_bits = getint("noise", "adc_bits", 0)
    max_eclipse_fraction = getfloat("sun", "max_eclipse_fraction", 0.15)
    if scene_meters_per_unit <= 0.0:
        raise ValueError("render.scene_meters_per_unit must be positive")
    if not isfinite(reference_snr) or reference_snr <= 0.0:
        raise ValueError("noise.reference_snr must be finite and positive")
    if not isfinite(bias_level) or not 0.0 <= bias_level <= 1.0:
        raise ValueError("noise.bias_level must be finite and in [0, 1]")
    if not isfinite(readout_noise_std) or readout_noise_std < 0.0:
        raise ValueError("noise.readout_noise_std must be finite and non-negative")
    if not isfinite(correlated_noise_std) or correlated_noise_std < 0.0:
        raise ValueError("noise.correlated_noise_std must be finite and non-negative")
    if not isfinite(correlation_time_s) or correlation_time_s < 0.0:
        raise ValueError("noise.correlation_time_s must be finite and non-negative")
    if correlated_noise_std > 0.0 and correlation_time_s <= 0.0:
        raise ValueError(
            "noise.correlation_time_s must be positive when correlated_noise_std > 0"
        )
    if not isfinite(saturation_level) or saturation_level < 0.0:
        raise ValueError("noise.saturation_level must be finite and non-negative")
    if adc_bits != 0 and not 2 <= adc_bits <= 24:
        raise ValueError("noise.adc_bits must be 0 (disabled) or in [2, 24]")
    if not 0.0 <= max_eclipse_fraction < 1.0:
        raise ValueError("sun.max_eclipse_fraction must be in [0, 1)")
    selected_models = _split_list(get("paths", "models", fallback=""))
    skip_models = tuple(
        _split_list(get("paths", "skip_models", fallback=",".join(DEFAULT_SKIP_MODELS)))
    )

    period_section = "dataset.period" if kind == "dataset" else "attitude"
    spin_period_s = getfloat(period_section, "spin_period_s", 20.0)
    spin_period_min_s = getfloat(period_section, "spin_period_min_s", MIN_ROTATION_PERIOD_S)
    spin_period_max_s = getfloat(period_section, "spin_period_max_s", ROTATION_PERIOD_CUTOFF_S)
    rotating_fraction = getfloat(period_section, "rotating_fraction", 0.5)
    tumbling_fraction = (
        getfloat("dataset.tumbling", "fraction", 0.01) if kind == "dataset" else 0.0
    )
    initial_phase_mode = get(period_section, "initial_phase_mode", "fixed").strip().lower()
    initial_phase_rad = getfloat(period_section, "initial_phase_rad", 0.0)
    if (
        not isfinite(spin_period_min_s)
        or not isfinite(spin_period_max_s)
        or spin_period_min_s <= 0.0
        or spin_period_max_s < spin_period_min_s
    ):
        raise ValueError("spin period bounds must be finite, positive, and ordered")

    precession_angle_deg = 0.0
    precession_period_s = 0.0
    precession_phase_deg = 0.0
    precession_fraction = 1.0
    if kind == "dataset":
        legacy_dataset_options = {
            "precession_fraction",
            "precession_angle_min_deg",
            "precession_angle_max_deg",
            "precession_period_min_s",
            "precession_period_max_s",
            "model_scale_min",
            "model_scale_max",
            "rotating_fraction",
        } & set(parser.options("dataset"))
        if legacy_dataset_options:
            names = ", ".join(sorted(f"dataset.{name}" for name in legacy_dataset_options))
            raise ValueError(
                f"dataset settings moved to [dataset.period], [dataset.precession], "
                f"or [dataset.scale]: {names}"
            )

        def read_fixed_or_random(
            section, mode_option, fixed_option, minimum_option, maximum_option
        ):
            mode = parser.get(section, mode_option).strip().lower()
            if mode == "fixed":
                expected = {mode_option, fixed_option}
                missing = expected - set(parser.options(section))
                if missing:
                    raise ValueError(f"{section} is missing options: {', '.join(sorted(missing))}")
                value = parser.getfloat(section, fixed_option)
                return value, value, expected
            if mode == "random":
                expected = {mode_option, minimum_option, maximum_option}
                missing = expected - set(parser.options(section))
                if missing:
                    raise ValueError(f"{section} is missing options: {', '.join(sorted(missing))}")
                minimum = parser.getfloat(section, minimum_option)
                maximum = parser.getfloat(section, maximum_option)
                return minimum, maximum, expected
            raise ValueError(
                f"{section}.{mode_option} must be 'fixed' or 'random' (got {mode!r})"
            )

        precession_angle_min_deg, precession_angle_max_deg, angle_options = read_fixed_or_random(
            "dataset.precession", "angle_mode", "angle_deg", "angle_min_deg", "angle_max_deg"
        )
        precession_period_min_s, precession_period_max_s, period_options = read_fixed_or_random(
            "dataset.precession", "period_mode", "period_s", "period_min_s", "period_max_s"
        )
        model_scale_min, model_scale_max, scale_options = read_fixed_or_random(
            "dataset.scale", "mode", "factor", "min_factor", "max_factor"
        )

        expected_precession_options = angle_options | period_options | {"fraction"}
        actual_precession_options = set(parser.options("dataset.precession"))
        expected_scale_options = scale_options
        actual_scale_options = set(parser.options("dataset.scale"))
        for section, actual, expected in (
            ("dataset.precession", actual_precession_options, expected_precession_options),
            ("dataset.scale", actual_scale_options, expected_scale_options),
        ):
            missing_options = expected - actual
            unused_options = actual - expected
            if missing_options or unused_options:
                details = []
                if missing_options:
                    details.append(f"missing: {', '.join(sorted(missing_options))}")
                if unused_options:
                    details.append(f"unused for selected mode: {', '.join(sorted(unused_options))}")
                raise ValueError(f"{section} options are invalid ({'; '.join(details)})")

        precession_fraction = parser.getfloat("dataset.precession", "fraction")
        precession_angle_deg = precession_angle_min_deg
        precession_period_s = precession_period_min_s
        precession_phase_deg = 0.0
    else:
        precession_angle_deg = getfloat("attitude", "precession_angle_deg", 0.0)
        precession_period_s = getfloat("attitude", "precession_period_s", 0.0)
        precession_phase_deg = getfloat("attitude", "precession_phase_deg", 0.0)
        precession_angle_min_deg = precession_angle_deg
        precession_angle_max_deg = precession_angle_deg
        precession_period_min_s = precession_period_s
        precession_period_max_s = precession_period_s
        model_scale_min = 1.0
        model_scale_max = 1.0
    if not all(isfinite(value) for value in (
        precession_angle_deg,
        precession_period_s,
        precession_phase_deg,
        precession_angle_min_deg,
        precession_angle_max_deg,
        precession_period_min_s,
        precession_period_max_s,
    )):
        raise ValueError("precession settings must be finite")
    if kind == "curve":
        if not 0.0 <= precession_angle_deg <= 180.0:
            raise ValueError("attitude.precession_angle_deg must be in [0, 180]")
        if precession_period_s < 0.0 or (
            precession_angle_deg > 0.0 and precession_period_s <= 0.0
        ):
            raise ValueError(
                "attitude.precession_period_s must be positive when precession is enabled"
            )
    if not 0.0 <= precession_angle_min_deg <= precession_angle_max_deg <= 180.0:
        raise ValueError("dataset precession angle range must be within [0, 180]")
    if precession_period_min_s <= 0.0 or precession_period_max_s < precession_period_min_s:
        raise ValueError("dataset precession period range must be positive and ordered")
    if (
        not isfinite(model_scale_min)
        or not isfinite(model_scale_max)
        or model_scale_min <= 0.0
        or model_scale_max < model_scale_min
    ):
        raise ValueError("dataset model scale range must be finite, positive, and ordered")

    altitude_min_m = getfloat("orbit", "altitude_min_km", MIN_ORBIT_ALTITUDE_M / 1000.0) * 1000.0
    altitude_max_m = getfloat("orbit", "altitude_max_km", MAX_ORBIT_ALTITUDE_M / 1000.0) * 1000.0
    altitude_m = getfloat("orbit", "altitude_km", 800.0) * 1000.0
    if not MIN_ORBIT_ALTITUDE_M <= altitude_min_m <= altitude_max_m <= MAX_ORBIT_ALTITUDE_M:
        raise ValueError("orbit altitude range must stay within 300-3000 km")
    if not MIN_ORBIT_ALTITUDE_M <= altitude_m <= MAX_ORBIT_ALTITUDE_M:
        raise ValueError("orbit altitude_km must stay within 300-3000 km")

    device = get("run", "device", "auto").strip().lower()
    if device not in DEVICES:
        raise ValueError(f"device must be one of {', '.join(DEVICES)}")

    observer_mode = get("observer", "mode", "fixed").strip().lower()
    orbit_mode = get("orbit", "mode", "random").strip().lower()
    attitude_mode = get(period_section, "mode", "rotating").strip().lower()
    sun_mode = get("sun", "mode", "random").strip().lower()
    for name, value, allowed in (
        ("observer.mode", observer_mode, {"fixed", "random"}),
        ("orbit.mode", orbit_mode, {"fixed", "random"}),
        (f"{period_section}.mode", attitude_mode, {"static", "rotating", "random"}),
        (f"{period_section}.initial_phase_mode", initial_phase_mode, {"fixed", "random"}),
        ("sun.mode", sun_mode, {"random", "vector"}),
    ):
        if value not in allowed:
            raise ValueError(f"{name} must be one of {', '.join(sorted(allowed))}")

    count = 1
    if kind == "dataset":
        if parser.has_option("dataset", "curves_per_model"):
            raise ValueError(
                "dataset.curves_per_model is no longer supported; "
                "use dataset.total_curves"
            )
        count = parser.getint("dataset", "total_curves", fallback=10_000)
    if count < 1:
        raise ValueError("count/total_curves must be at least 1")
    if not 0.0 <= rotating_fraction <= 1.0:
        raise ValueError("rotating_fraction must be in [0, 1]")
    if not 0.0 <= tumbling_fraction <= 1.0:
        raise ValueError("dataset.tumbling.fraction must be in [0, 1]")
    if not 0.0 <= precession_fraction <= 1.0:
        raise ValueError("dataset.precession.fraction must be in [0, 1]")

    minimum_elevation_deg = getfloat(
        "pass", "minimum_elevation_deg", DEFAULT_MINIMUM_ELEVATION_DEG
    )
    if not isfinite(minimum_elevation_deg) or minimum_elevation_deg >= 90.0:
        raise ValueError("pass.minimum_elevation_deg must be finite and in [0, 90)")
    if minimum_elevation_deg < MINIMUM_ELEVATION_FLOOR_DEG:
        warnings.warn(
            f"pass.minimum_elevation_deg={minimum_elevation_deg:g} is below "
            f"{MINIMUM_ELEVATION_FLOOR_DEG:g} degrees; using "
            f"{MINIMUM_ELEVATION_FLOOR_DEG:g} degrees",
            UserWarning,
            stacklevel=2,
        )
        minimum_elevation_deg = MINIMUM_ELEVATION_FLOOR_DEG

    workers = 1
    if kind == "dataset":
        workers = getint("dataset", "workers", 1)
        if workers < 1:
            raise ValueError("dataset.workers must be at least 1")

    config = SynthConfig(
        kind=kind,
        config_path=config_path,
        blender=blender,
        model=model,
        models_dir=models_dir,
        selected_models=selected_models,
        skip_models=skip_models,
        output=output,
        output_dir=output_dir,
        seed=getint("run", "seed", 42),
        device=device,
        count=count,
        workers=workers,
        observer_mode=observer_mode,
        latitude_deg=getfloat("observer", "latitude_deg", 48.633),
        longitude_deg=getfloat("observer", "longitude_deg", 22.33),
        observer_altitude_m=getfloat("observer", "altitude_m", 0.0),
        orbit_mode=orbit_mode,
        altitude_min_m=altitude_min_m,
        altitude_max_m=altitude_max_m,
        altitude_m=altitude_m,
        inclination_min_deg=getfloat("orbit", "inclination_min_deg", 0.0),
        inclination_max_deg=getfloat("orbit", "inclination_max_deg", 180.0),
        inclination_deg=getfloat("orbit", "inclination_deg", 51.6),
        raan_deg=getfloat("orbit", "raan_deg", 0.0),
        phase_deg=getfloat("orbit", "phase_deg", 0.0),
        align_for_pass=getbool("orbit", "align_for_pass", True),
        duration_s=getfloat("pass", "duration_s", 60.0),
        cadence_s=getfloat("pass", "cadence_s", 10.0),
        minimum_elevation_deg=minimum_elevation_deg,
        max_pass_attempts=getint("pass", "max_attempts", 1000),
        attitude_mode=attitude_mode,
        spin_period_s=spin_period_s,
        spin_period_min_s=spin_period_min_s,
        spin_period_max_s=spin_period_max_s,
        rotating_fraction=rotating_fraction,
        tumbling_fraction=tumbling_fraction,
        initial_phase_mode=initial_phase_mode,
        initial_phase_rad=initial_phase_rad,
        precession_angle_deg=precession_angle_deg,
        precession_period_s=precession_period_s,
        precession_phase_deg=precession_phase_deg,
        precession_fraction=precession_fraction,
        precession_angle_min_deg=precession_angle_min_deg,
        precession_angle_max_deg=precession_angle_max_deg,
        precession_period_min_s=precession_period_min_s,
        precession_period_max_s=precession_period_max_s,
        model_scale_min=model_scale_min,
        model_scale_max=model_scale_max,
        reference_snr=reference_snr,
        bias_level=bias_level,
        readout_noise_std=readout_noise_std,
        correlated_noise_std=correlated_noise_std,
        correlation_time_s=correlation_time_s,
        saturation_level=saturation_level,
        adc_bits=adc_bits,
        sun_mode=sun_mode,
        sun_direction=(
            getfloat("sun", "x", 0.71),
            getfloat("sun", "y", -0.42),
            getfloat("sun", "z", 0.56),
        ),
        sun_energy=getfloat("sun", "energy", 3.0),
        max_eclipse_fraction=max_eclipse_fraction,
        resolution=getint("render", "resolution", 128),
        samples=getint("render", "samples", 8),
        exposure=getfloat("render", "exposure", -8.8),
        script_output=script_output,
        scene_meters_per_unit=scene_meters_per_unit,
    )
    if kind == "curve" and config.model is None:
        raise ValueError("curve config requires paths.model")
    return config


@dataclass(frozen=True)
class ModelShape:
    body_shape: tuple[str, ...]
    solar_panel_count: int
    dimensions_m: tuple[float, float, float] | None = None


def _parse_dimensions_m(model_name: str, dimensions) -> tuple[float, float, float]:
    if not isinstance(dimensions, dict) or set(dimensions) != {"x", "y", "z"}:
        raise ValueError(
            f"dimensions_m for {model_name!r} must define exactly x, y, and z"
        )
    values = tuple(dimensions[axis] for axis in ("x", "y", "z"))
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value <= 0.0
        for value in values
    ):
        raise ValueError(
            f"dimensions_m for {model_name!r} must contain positive finite meters"
        )
    return tuple(float(value) for value in values)


def load_model_shapes(path: Path) -> dict[str, ModelShape]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("model shapes config must be a JSON object")

    shapes = {}
    for model_name, model_config in data.items():
        if not isinstance(model_config, dict):
            raise ValueError(f"shape config for {model_name!r} must be an object")
        body_shape = model_config.get("body_shape")
        if (
            not isinstance(body_shape, list)
            or not body_shape
            or any(not isinstance(item, str) or not item.strip() for item in body_shape)
        ):
            raise ValueError(
                f"body_shape for {model_name!r} must be a non-empty list of strings"
            )
        panel_count = model_config.get("solar_panel_count")
        if (
            isinstance(panel_count, bool)
            or not isinstance(panel_count, int)
            or panel_count < 0
        ):
            raise ValueError(
                f"solar_panel_count for {model_name!r} must be a non-negative integer"
            )
        dimensions = model_config.get("dimensions_m")
        shapes[model_name] = ModelShape(
            body_shape=tuple(item.strip() for item in body_shape),
            solar_panel_count=panel_count,
            dimensions_m=(
                None
                if dimensions is None
                else _parse_dimensions_m(model_name, dimensions)
            ),
        )
    return shapes


def require_model_shape(
    model_name: str, model_shapes: dict[str, ModelShape]
) -> ModelShape:
    shape = model_shapes.get(model_name)
    if shape is None:
        raise ValueError(
            f"{model_name!r} has no entry in models/model_shapes.json; "
            "body_shape and solar_panel_count are required for every model"
        )
    return shape


def model_axis_scale_factors(
    source_dimensions: tuple[float, float, float],
    target_dimensions_m: tuple[float, float, float],
    scene_meters_per_unit: float,
) -> tuple[float, float, float]:
    if not isfinite(scene_meters_per_unit) or scene_meters_per_unit <= 0.0:
        raise ValueError("scene_meters_per_unit must be finite and positive")
    if any(not isfinite(value) or value <= 0.0 for value in source_dimensions):
        raise ValueError("source model dimensions must be finite and positive on all axes")
    if any(not isfinite(value) or value <= 0.0 for value in target_dimensions_m):
        raise ValueError("target model dimensions must be finite and positive on all axes")
    return tuple(
        target_m / (source_units * scene_meters_per_unit)
        for source_units, target_m in zip(source_dimensions, target_dimensions_m)
    )


def resolve_model_dimensions(
    model_name: str,
    source_dimensions: tuple[float, float, float],
    model_shapes: dict[str, ModelShape],
    scene_meters_per_unit: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float], bool]:
    if not isfinite(scene_meters_per_unit) or scene_meters_per_unit <= 0.0:
        raise ValueError("scene_meters_per_unit must be finite and positive")
    if any(not isfinite(value) or value < 0.0 for value in source_dimensions):
        raise ValueError("source model dimensions must be finite and non-negative")

    target_dimensions_m = require_model_shape(model_name, model_shapes).dimensions_m
    if target_dimensions_m is None:
        return (
            (1.0, 1.0, 1.0),
            tuple(value * scene_meters_per_unit for value in source_dimensions),
            False,
        )
    scale_factors = model_axis_scale_factors(
        source_dimensions,
        target_dimensions_m,
        scene_meters_per_unit,
    )
    return scale_factors, target_dimensions_m, True


def apply_overrides(config: SynthConfig, **overrides) -> SynthConfig:
    filtered = {key: value for key, value in overrides.items() if value is not None}
    if not filtered:
        return config
    return replace(config, **filtered)


def usable_models(config: SynthConfig) -> tuple[Path, ...]:
    if config.selected_models:
        models = tuple(_resolve_model(name, config.models_dir) for name in config.selected_models)
    elif config.kind == "curve" and config.model is not None:
        models = (config.model,)
    else:
        models = tuple(
            path
            for path in sorted(config.models_dir.glob("*.blend"))
            if path.name not in config.skip_models
        )
    missing = [str(path) for path in models if not path.is_file()]
    if missing:
        raise FileNotFoundError("Model file not found: " + ", ".join(missing))
    if not models:
        raise FileNotFoundError(f"No usable .blend models found in {config.models_dir}")
    return models


def _split_list(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _resolve_path(value: str, config_path: Path) -> Path:
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def _resolve_model(name: str, models_dir: Path) -> Path:
    path = Path(name).expanduser()
    if path.is_absolute():
        return path
    if path.suffix:
        return (models_dir / path).resolve()
    return (models_dir / f"{path}.blend").resolve()
