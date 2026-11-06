"""Load curve and dataset settings from INI files."""

from __future__ import annotations

import configparser
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path

from . import MIN_ROTATION_PERIOD_S, ROTATION_PERIOD_CUTOFF_S
from .orbit import MAX_ORBIT_ALTITUDE_M, MIN_ORBIT_ALTITUDE_M


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
    initial_phase_mode: str
    initial_phase_rad: float
    precession_angle_deg: float
    precession_period_s: float
    precession_phase_deg: float
    precession_angle_min_deg: float
    precession_angle_max_deg: float
    precession_period_min_s: float
    precession_period_max_s: float
    sun_mode: str
    sun_direction: tuple[float, float, float]
    sun_energy: float
    max_eclipse_fraction: float
    resolution: int
    samples: int
    exposure: float
    script_output: Path | None
    scene_meters_per_unit: float
    satellite_size_m: float


def load_config(path: Path, kind: str) -> SynthConfig:
    if kind not in {"curve", "dataset"}:
        raise ValueError("kind must be 'curve' or 'dataset'")
    config_path = path.expanduser().resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    parser = configparser.ConfigParser(inline_comment_prefixes=("#", ";"))
    parser.read(config_path, encoding="utf-8")
    required = {"blender", "paths", "run", "observer", "orbit", "pass", "attitude", "sun", "render"}
    if kind == "dataset":
        required.add("dataset")
    missing = sorted(section for section in required if not parser.has_section(section))
    if missing:
        raise ValueError(f"{config_path} is missing sections: {', '.join(missing)}")

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
    satellite_size_m = getfloat("render", "satellite_size_m", 4.0)
    max_eclipse_fraction = getfloat("sun", "max_eclipse_fraction", 0.15)
    if scene_meters_per_unit <= 0.0:
        raise ValueError("render.scene_meters_per_unit must be positive")
    if satellite_size_m <= 0.0:
        raise ValueError("render.satellite_size_m must be positive")
    if not 0.0 <= max_eclipse_fraction < 1.0:
        raise ValueError("sun.max_eclipse_fraction must be in [0, 1)")
    selected_models = _split_list(get("paths", "models", fallback=""))
    skip_models = tuple(
        _split_list(get("paths", "skip_models", fallback=",".join(DEFAULT_SKIP_MODELS)))
    )

    spin_period_min_s = getfloat("attitude", "spin_period_min_s", MIN_ROTATION_PERIOD_S)
    spin_period_max_s = getfloat("attitude", "spin_period_max_s", ROTATION_PERIOD_CUTOFF_S)
    if spin_period_min_s <= 0.0 or spin_period_max_s < spin_period_min_s:
        raise ValueError("spin_period_min_s must be positive and not exceed spin_period_max_s")

    precession_angle_deg = getfloat("attitude", "precession_angle_deg", 0.0)
    precession_period_s = getfloat("attitude", "precession_period_s", 0.0)
    precession_phase_deg = getfloat("attitude", "precession_phase_deg", 0.0)
    precession_angle_min_deg = (
        parser.getfloat("dataset", "precession_angle_min_deg", fallback=precession_angle_deg)
        if kind == "dataset"
        else precession_angle_deg
    )
    precession_angle_max_deg = (
        parser.getfloat("dataset", "precession_angle_max_deg", fallback=precession_angle_deg)
        if kind == "dataset"
        else precession_angle_deg
    )
    precession_period_min_s = (
        parser.getfloat("dataset", "precession_period_min_s", fallback=precession_period_s)
        if kind == "dataset"
        else precession_period_s
    )
    precession_period_max_s = (
        parser.getfloat("dataset", "precession_period_max_s", fallback=precession_period_s)
        if kind == "dataset"
        else precession_period_s
    )
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
    attitude_mode = get("attitude", "mode", "rotating").strip().lower()
    initial_phase_mode = get("attitude", "initial_phase_mode", "fixed").strip().lower()
    sun_mode = get("sun", "mode", "random").strip().lower()
    for name, value, allowed in (
        ("observer.mode", observer_mode, {"fixed", "random"}),
        ("orbit.mode", orbit_mode, {"fixed", "random"}),
        ("attitude.mode", attitude_mode, {"static", "rotating", "random"}),
        ("attitude.initial_phase_mode", initial_phase_mode, {"fixed", "random"}),
        ("sun.mode", sun_mode, {"random", "vector"}),
    ):
        if value not in allowed:
            raise ValueError(f"{name} must be one of {', '.join(sorted(allowed))}")

    count = 1
    rotating_fraction = getfloat("attitude", "rotating_fraction", 0.5)
    if kind == "dataset":
        count = parser.getint("dataset", "curves_per_model", fallback=2)
        rotating_fraction = parser.getfloat("dataset", "rotating_fraction", fallback=rotating_fraction)
    if count < 1:
        raise ValueError("count/curves_per_model must be at least 1")
    if not 0.0 <= rotating_fraction <= 1.0:
        raise ValueError("rotating_fraction must be in [0, 1]")

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
        minimum_elevation_deg=getfloat("pass", "minimum_elevation_deg", 10.0),
        max_pass_attempts=getint("pass", "max_attempts", 1000),
        attitude_mode=attitude_mode,
        spin_period_s=getfloat("attitude", "spin_period_s", 20.0),
        spin_period_min_s=spin_period_min_s,
        spin_period_max_s=spin_period_max_s,
        rotating_fraction=rotating_fraction,
        initial_phase_mode=initial_phase_mode,
        initial_phase_rad=getfloat("attitude", "initial_phase_rad", 0.0),
        precession_angle_deg=precession_angle_deg,
        precession_period_s=precession_period_s,
        precession_phase_deg=precession_phase_deg,
        precession_angle_min_deg=precession_angle_min_deg,
        precession_angle_max_deg=precession_angle_max_deg,
        precession_period_min_s=precession_period_min_s,
        precession_period_max_s=precession_period_max_s,
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
        satellite_size_m=satellite_size_m,
    )
    if kind == "curve" and config.model is None:
        raise ValueError("curve config requires paths.model")
    return config


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
