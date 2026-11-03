"""Render a low-cost synthetic light curve from a Blender spacecraft model."""

import argparse
import csv
from datetime import datetime
import json
import random
import secrets
import sys
import tempfile
from math import tau
from pathlib import Path
from xml.etree import ElementTree as ET

import bpy
from mathutils import Quaternion, Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from blender_synth_lc.attitude import (
    is_rotating,
    load_model_spin_axes,
    sample_spin_axis,
    sample_spin_period_s,
    spin_phase_rad,
)
from blender_synth_lc.illumination import (
    is_eclipsed,
    sample_sun_direction,
    sunlit_pass_exists,
)
from blender_synth_lc.orbit import (
    CircularOrbit,
    GroundObserver,
    align_orbit_for_pass,
    observer_position_fixed_frame,
    sample_ground_observer,
    sample_pass_window,
    sample_visible_pass,
)
from blender_synth_lc.config import apply_overrides, load_config


def parse_args():
    blender_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--kind", choices=("curve", "dataset"), required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--count", type=int, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "optix"), required=True)
    cli_args = parser.parse_args(blender_args)
    if cli_args.count < 1:
        parser.error("count must be at least 1")

    config = load_config(cli_args.config, kind=cli_args.kind)
    return apply_overrides(
        config,
        model=cli_args.model.resolve(),
        output=cli_args.output.resolve() if cli_args.output is not None else None,
        output_dir=cli_args.output_dir.resolve() if cli_args.output_dir is not None else None,
        count=cli_args.count,
        seed=cli_args.seed,
        device=cli_args.device,
    )


def configure_device(scene, requested_device):
    scene.render.engine = "CYCLES"
    cycles_addon = bpy.context.preferences.addons.get("cycles")
    preferences = cycles_addon.preferences if cycles_addon else None
    gpu_types = ("CUDA", "OPTIX", "HIP", "ONEAPI", "METAL")
    candidates = gpu_types if requested_device == "auto" else (requested_device.upper(),)
    if requested_device != "cpu" and preferences:
        for device_type in candidates:
            try:
                preferences.compute_device_type = device_type
                preferences.get_devices()
            except Exception:
                continue
            devices = list(preferences.devices)
            gpu_devices = [device for device in devices if device.type != "CPU"]
            if gpu_devices:
                for device in devices:
                    device.use = device.type != "CPU"
                scene.cycles.device = "GPU"
                device_names = list(dict.fromkeys(device.name for device in gpu_devices))
                return {
                    "requested": requested_device,
                    "backend": preferences.compute_device_type,
                    "mode": "GPU",
                    "devices": device_names,
                }

    if requested_device not in ("auto", "cpu"):
        raise RuntimeError(
            f"Requested {requested_device.upper()} device is not available in Blender"
        )
    scene.cycles.device = "CPU"
    if preferences:
        try:
            preferences.compute_device_type = "NONE"
            preferences.get_devices()
        except Exception:
            pass
    return {
        "requested": requested_device,
        "backend": "CPU",
        "mode": "CPU",
        "devices": [],
    }


def usable_meshes(scene):
    return [
        obj
        for obj in scene.objects
        if obj.type == "MESH" and obj.data is not None and len(obj.data.vertices)
    ]


def combined_world_bounds(meshes):
    points = []
    for mesh in meshes:
        points.extend(mesh.matrix_world @ Vector(corner) for corner in mesh.bound_box)
    center = sum(points, Vector()) / len(points)
    radius = max((point - center).length for point in points)
    return center, radius


def parent_meshes_to_root(scene, meshes, center):
    root = bpy.data.objects.new("SyntheticSatelliteRoot", None)
    scene.collection.objects.link(root)
    root.location = center
    bpy.context.view_layer.update()
    for mesh in meshes:
        world_matrix = mesh.matrix_world.copy()
        mesh.parent = root
        mesh.matrix_world = world_matrix
    bpy.context.view_layer.update()
    return root


def hide_existing_lights_and_cameras(scene):
    for obj in scene.objects:
        if obj.type in {"LIGHT", "CAMERA"}:
            obj.hide_render = True
            obj.hide_viewport = True


def configure_black_world(scene):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("SyntheticSpaceWorld")
        scene.world = world
    world.use_nodes = True
    background = next(
        (node for node in world.node_tree.nodes if node.type == "BACKGROUND"),
        None,
    )
    if background is not None:
        background.inputs[0].default_value = (0.0, 0.0, 0.0, 1.0)
        background.inputs[1].default_value = 0.0


def add_camera_and_sun(scene, target, observer_direction, camera_distance, sun_direction, sun_energy):
    camera_data = bpy.data.cameras.new("SyntheticObserverCamera")
    camera = bpy.data.objects.new("SyntheticObserverCamera", camera_data)
    scene.collection.objects.link(camera)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = camera_distance * 1.4
    camera.location = target + observer_direction * camera_distance
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera

    light_data = bpy.data.lights.new("SyntheticSun", type="SUN")
    light = bpy.data.objects.new("SyntheticSun", light_data)
    scene.collection.objects.link(light)
    light_data.energy = sun_energy
    light.rotation_euler = (-sun_direction).to_track_quat("-Z", "Y").to_euler()
    return camera, light


def render_flux(scene, frame_path):
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "32"
    scene.render.filepath = str(frame_path)
    bpy.ops.render.render(write_still=True)
    image = bpy.data.images.load(str(frame_path), check_existing=False)
    try:
        pixels = image.pixels[:]
        channels = image.channels
        if not pixels or channels < 3:
            raise RuntimeError(f"Blender produced an empty image buffer for {frame_path}")
        return sum(
            pixels[index] + pixels[index + 1] + pixels[index + 2]
            for index in range(0, len(pixels), channels)
        )
    finally:
        bpy.data.images.remove(image)


def write_diagnostic_svg(times, relative_flux, output_path, title):
    namespace = "http://www.w3.org/2000/svg"
    ET.register_namespace("", namespace)
    width, height = 900, 520
    left, top, right, bottom = 82, 48, 34, 68
    plot_width = width - left - right
    plot_height = height - top - bottom
    minimum_time, maximum_time = min(times), max(times)

    def tag(name):
        return f"{{{namespace}}}{name}"

    def add(parent, name, **attributes):
        return ET.SubElement(parent, tag(name), attributes)

    def x_position(time_s):
        return left + (time_s - minimum_time) / (maximum_time - minimum_time) * plot_width

    def y_position(flux):
        return top + (1.0 - flux) * plot_height

    root = ET.Element(tag("svg"), {
        "viewBox": f"0 0 {width} {height}",
        "width": str(width),
        "height": str(height),
        "role": "img",
        "aria-labelledby": "plot-title plot-description",
    })
    add(root, "title", id="plot-title").text = "Synthetic spacecraft light curve"
    add(root, "desc", id="plot-description").text = (
        "Normalized linear RGB flux through a synthetic satellite pass."
    )
    add(root, "rect", x="0", y="0", width=str(width), height=str(height), fill="#ffffff")
    add(root, "text", x=str(left), y="28", fill="#18313c", **{
        "font-family": "sans-serif", "font-size": "18", "font-weight": "600"
    }).text = title

    for tick in range(5):
        flux = tick / 4.0
        y = y_position(flux)
        add(root, "line", x1=str(left), y1=f"{y:.2f}",
            x2=str(width - right), y2=f"{y:.2f}", stroke="#d8e0e3", **{"stroke-width": "1"})
        add(root, "text", x=str(left - 12), y=f"{y + 4:.2f}", fill="#42545b",
            **{"font-family": "sans-serif", "font-size": "12", "text-anchor": "end"}).text = f"{flux:.2f}"

    midpoint_time = (minimum_time + maximum_time) / 2.0
    for time_s in sorted(set((minimum_time, midpoint_time, maximum_time))):
        x = x_position(time_s)
        add(root, "line", x1=f"{x:.2f}", y1=str(top),
            x2=f"{x:.2f}", y2=str(height - bottom), stroke="#edf0f1", **{"stroke-width": "1"})
        add(root, "text", x=f"{x:.2f}", y=str(height - bottom + 22), fill="#42545b",
            **{"font-family": "sans-serif", "font-size": "12", "text-anchor": "middle"}).text = f"{time_s:g}"

    add(root, "line", x1=str(left), y1=str(top), x2=str(left), y2=str(height - bottom),
        stroke="#344a53", **{"stroke-width": "1.5"})
    add(root, "line", x1=str(left), y1=str(height - bottom), x2=str(width - right),
        y2=str(height - bottom), stroke="#344a53", **{"stroke-width": "1.5"})
    add(root, "text", x=str(left + plot_width / 2), y=str(height - 18), fill="#18313c",
        **{"font-family": "sans-serif", "font-size": "13", "text-anchor": "middle"}).text = "Time from start (s)"
    add(root, "text", x="20", y=str(top + plot_height / 2), fill="#18313c",
        transform=f"rotate(-90 20 {top + plot_height / 2})",
        **{"font-family": "sans-serif", "font-size": "13", "text-anchor": "middle"}).text = "Relative flux"

    points = " ".join(
        f"{x_position(time_s):.2f},{y_position(flux):.2f}"
        for time_s, flux in zip(times, relative_flux)
    )
    add(root, "polyline", points=points, fill="none", stroke="#13847f",
        **{"stroke-width": "2.5", "stroke-linecap": "round", "stroke-linejoin": "round"})
    for time_s, flux in zip(times, relative_flux):
        add(root, "circle", cx=f"{x_position(time_s):.2f}", cy=f"{y_position(flux):.2f}",
            r="4", fill="#d56f43", stroke="#ffffff", **{"stroke-width": "1.5"})

    ET.ElementTree(root).write(output_path, encoding="utf-8", xml_declaration=True)


def output_path_for_curve(config, curve_index):
    model_stem = config.model.stem
    if config.kind == "dataset" or config.output is None:
        directory = config.output_dir.resolve()
        directory.mkdir(parents=True, exist_ok=True)
        while True:
            token = secrets.token_hex(6)
            output_path = directory / (
                f"{model_stem}_seed{config.seed}_n{curve_index:04d}_{token}.csv"
            )
            if not output_files_exist(output_path):
                return output_path
    output_path = config.output.resolve()
    timestamp = datetime.now().strftime("%H%M%S")
    candidate = output_path.with_name(
        f"{output_path.stem}_{timestamp}{output_path.suffix}"
    )
    collision_index = 1
    while output_files_exist(candidate):
        candidate = output_path.with_name(
            f"{output_path.stem}_{timestamp}_{collision_index:02d}{output_path.suffix}"
        )
        collision_index += 1
    return candidate


def output_files_exist(output_path):
    return any(
        path.exists()
        for path in (
            output_path,
            output_path.with_suffix(".svg"),
            output_path.with_suffix(".json"),
        )
    )


def build_observer(config, rng):
    if config.observer_mode == "random":
        return sample_ground_observer(rng, altitude_m=config.observer_altitude_m)
    return GroundObserver(
        latitude_deg=config.latitude_deg,
        longitude_deg=config.longitude_deg,
        altitude_m=config.observer_altitude_m,
    )


def build_attitude(config, rng, curve_index, model_spin_axes):
    if config.attitude_mode == "static":
        spin_period_s = 0.0
    elif config.attitude_mode == "rotating":
        spin_period_s = config.spin_period_s
        is_rotating(spin_period_s, config.spin_period_min_s, config.spin_period_max_s)
    else:
        if abs(config.rotating_fraction - 0.5) < 1e-12:
            rotating = curve_index % 2 == 0
        else:
            rotating = rng.random() < config.rotating_fraction
        spin_period_s = sample_spin_period_s(
            rng,
            rotating=rotating,
            min_period_s=config.spin_period_min_s,
            max_period_s=config.spin_period_max_s,
        )

    if config.initial_phase_mode == "random":
        initial_phase_rad = rng.uniform(0.0, tau)
    else:
        initial_phase_rad = config.initial_phase_rad

    spin_axis = sample_spin_axis(rng, config.model.name, model_spin_axes)
    return spin_period_s, initial_phase_rad, spin_axis


def build_visible_pass(config, rng, observer):
    if config.orbit_mode == "random":
        return sample_visible_pass(
            rng,
            observer,
            minimum_elevation_deg=config.minimum_elevation_deg,
            max_attempts=config.max_pass_attempts,
            altitude_min_m=config.altitude_min_m,
            altitude_max_m=config.altitude_max_m,
            inclination_min_deg=config.inclination_min_deg,
            inclination_max_deg=config.inclination_max_deg,
        )

    orbit = CircularOrbit(
        altitude_m=config.altitude_m,
        inclination_deg=config.inclination_deg,
        raan_deg=config.raan_deg,
        phase_deg=config.phase_deg,
    )
    if config.align_for_pass:
        visible_pass = align_orbit_for_pass(
            orbit, observer, minimum_elevation_deg=config.minimum_elevation_deg
        )
        if visible_pass is None:
            raise RuntimeError("Fixed orbit does not clear the elevation mask")
        return visible_pass
    from blender_synth_lc.orbit import look_angles, VisiblePass

    _, elevation, range_m = look_angles(orbit, observer, 0.0)
    return VisiblePass(
        orbit=orbit,
        closest_elevation_deg=elevation,
        closest_range_m=range_m,
        minimum_elevation_deg=config.minimum_elevation_deg,
    )


def build_sun_direction(config, rng, positions):
    if config.sun_mode == "vector":
        return config.sun_direction
    sun_direction = sample_sun_direction(rng)
    for _ in range(24):
        if sunlit_pass_exists(positions, sun_direction):
            return sun_direction
        sun_direction = sample_sun_direction(rng)
    raise RuntimeError("Could not sample a sun direction with any sunlit pass samples")


def build_scenario(config, curve_index, model_spin_axes):
    rng = random.Random(config.seed + curve_index)
    observer = build_observer(config, rng)
    spin_period_s, initial_phase_rad, spin_axis = build_attitude(
        config, rng, curve_index, model_spin_axes
    )
    visible_pass = build_visible_pass(config, rng, observer)
    samples = sample_pass_window(
        visible_pass,
        observer,
        duration_s=config.duration_s,
        cadence_s=config.cadence_s,
    )
    sun_direction = build_sun_direction(
        config, rng, tuple(sample.position_m for sample in samples)
    )
    return {
        "observer": observer,
        "visible_pass": visible_pass,
        "samples": samples,
        "spin_period_s": spin_period_s,
        "initial_phase_rad": initial_phase_rad,
        "spin_axis": spin_axis,
        "sun_direction": sun_direction,
    }


def write_curve_files(args, curve_index, scenario, satellite_root, meshes, device, scene, camera, light):
    samples = scenario["samples"]
    observer = scenario["observer"]
    visible_pass = scenario["visible_pass"]
    spin_period_s = scenario["spin_period_s"]
    spin_axis = Vector(scenario["spin_axis"]).normalized()
    sun_direction = Vector(scenario["sun_direction"]).normalized()
    observer_position = Vector(observer_position_fixed_frame(observer))
    original_location = satellite_root.location.copy()
    satellite_root.rotation_mode = "QUATERNION"
    original_rotation = satellite_root.rotation_quaternion.copy()
    initial_orbit_position = Vector(samples[0].position_m)
    scene_scale_per_m = 1e-6
    camera_distance = max(scenario["model_radius"] * 4.0, 4.0)
    light.rotation_euler = (-sun_direction).to_track_quat("-Z", "Y").to_euler()

    raw_fluxes = []
    corrected_fluxes = []
    eclipsed_flags = []
    reference_range_m = samples[0].range_m
    with tempfile.TemporaryDirectory(prefix="blender-synth-lc-") as temp_dir:
        frame_path = Path(temp_dir) / "frame.exr"
        for sample in samples:
            eclipsed = is_eclipsed(sample.position_m, tuple(sun_direction))
            eclipsed_flags.append(eclipsed)
            if eclipsed:
                raw_fluxes.append(0.0)
                corrected_fluxes.append(0.0)
                continue

            time_s = sample.time_from_closest_approach_s
            satellite_root.location = original_location + (
                Vector(sample.position_m) - initial_orbit_position
            ) * scene_scale_per_m
            phase = spin_phase_rad(
                spin_period_s, time_s, scenario["initial_phase_rad"]
            )
            satellite_root.rotation_quaternion = original_rotation @ Quaternion(
                spin_axis, phase
            )
            bpy.context.view_layer.update()
            target = satellite_root.location.copy()
            view_direction = (
                observer_position - Vector(sample.position_m)
            ).normalized()
            camera.location = target + view_direction * camera_distance
            camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
            raw_flux = render_flux(scene, frame_path)
            corrected_flux = raw_flux * (reference_range_m / sample.range_m) ** 2
            raw_fluxes.append(raw_flux)
            corrected_fluxes.append(corrected_flux)

    satellite_root.location = original_location
    satellite_root.rotation_quaternion = original_rotation
    maximum_flux = max(corrected_fluxes)
    if maximum_flux <= 0.0:
        raise RuntimeError(
            "Rendered flux is zero for every sample; inspect the model materials, lighting, and eclipse geometry"
        )

    output_path = output_path_for_curve(args, curve_index)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    relative_flux = [flux / maximum_flux for flux in corrected_fluxes]
    time_from_start_s = [
        sample.time_from_closest_approach_s - samples[0].time_from_closest_approach_s
        for sample in samples
    ]
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow((
            "time_from_start_s",
            "range_m",
            "azimuth_deg",
            "elevation_deg",
            "visible",
            "eclipsed",
            "render_flux_linear_rgb",
            "flux_with_range_correction",
            "relative_flux",
        ))
        for sample, time_s, raw_flux, corrected_flux, eclipsed in zip(
            samples, time_from_start_s, raw_fluxes, corrected_fluxes, eclipsed_flags
        ):
            writer.writerow((
                time_s,
                sample.range_m,
                sample.azimuth_deg,
                sample.elevation_deg,
                int(sample.visible),
                int(eclipsed),
                raw_flux,
                corrected_flux,
                corrected_flux / maximum_flux,
            ))

    plot_path = output_path.with_suffix(".svg")
    write_diagnostic_svg(
        time_from_start_s,
        relative_flux,
        plot_path,
        f"{args.model.stem} | normalized flux | spin {spin_period_s:.3g}s",
    )
    metadata = {
        "model": str(args.model.resolve()),
        "mesh_objects": [mesh.name for mesh in meshes],
        "curve_index": curve_index,
        "seed": args.seed,
        "observer": {
            "latitude_deg": observer.latitude_deg,
            "longitude_deg": observer.longitude_deg,
            "earth_rotation_ignored": True,
        },
        "orbit": {
            "altitude_m": visible_pass.orbit.altitude_m,
            "inclination_deg": visible_pass.orbit.inclination_deg,
            "raan_deg": visible_pass.orbit.raan_deg,
            "phase_deg": visible_pass.orbit.phase_deg,
            "closest_elevation_deg": visible_pass.closest_elevation_deg,
            "closest_range_m": visible_pass.closest_range_m,
        },
        "pass": {
            "duration_s": args.duration_s,
            "cadence_s": args.cadence_s,
            "minimum_elevation_deg": args.minimum_elevation_deg,
            "sample_count": len(samples),
        },
        "attitude": {
            "spin_period_s": spin_period_s,
            "rotating": is_rotating(spin_period_s),
            "initial_phase_rad": scenario["initial_phase_rad"],
            "spin_axis": list(scenario["spin_axis"]),
        },
        "render": {
            "blender_version": bpy.app.version_string,
            "engine": scene.render.engine,
            "device": device,
            "resolution": args.resolution,
            "samples": args.samples,
            "sun_direction_to_sun": list(sun_direction),
        },
        "photometry": {
            "flux_definition": "sum of linear RGB render pixels, multiplied by reference_range^2/range^2",
            "normalized_to_maximum": True,
            "eclipse_model": "cylindrical Earth shadow",
            "limitations": [
                "model bounds are not calibrated to physical spacecraft dimensions",
                "no atmosphere or calibrated surface photometry",
                "relative flux is a rendering proxy, not an absolute magnitude",
            ],
        },
        "diagnostic_plot": str(plot_path),
        "eclipsed_sample_count": int(sum(eclipsed_flags)),
    }
    output_path.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(samples)} samples to {output_path}")
    print(f"Render device: {device['mode']} ({device['backend']})")
    print(f"Relative flux range: {min(relative_flux):.6g}..1")
    return output_path


def main():
    args = parse_args()
    model_spin_axes = load_model_spin_axes(REPO_ROOT / "models" / "spin_axes.json")
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    if Path(bpy.data.filepath).resolve() != args.model.resolve():
        bpy.ops.wm.open_mainfile(filepath=str(args.model.resolve()))

    scene = bpy.context.scene
    meshes = usable_meshes(scene)
    if not meshes:
        raise RuntimeError("No mesh objects with geometry found in the scene")
    hide_existing_lights_and_cameras(scene)
    configure_black_world(scene)
    model_center, model_radius = combined_world_bounds(meshes)
    satellite_root = parent_meshes_to_root(scene, meshes, model_center)
    device = configure_device(scene, args.device)
    scene.cycles.samples = args.samples
    scene.cycles.max_bounces = 2
    scene.cycles.use_denoising = False
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    if hasattr(scene.render, "use_persistent_data"):
        scene.render.use_persistent_data = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0

    dummy_sun = Vector((0.0, 0.0, 1.0))
    camera, light = add_camera_and_sun(
        scene, satellite_root.location, Vector((0.0, -1.0, 0.0)),
        max(model_radius * 4.0, 4.0), dummy_sun, args.sun_energy,
    )

    for curve_index in range(args.count):
        scenario = build_scenario(args, curve_index, model_spin_axes)
        scenario["model_radius"] = model_radius
        write_curve_files(
            args, curve_index, scenario, satellite_root, meshes, device, scene, camera, light
        )

    bpy.data.objects.remove(camera, do_unlink=True)
    bpy.data.objects.remove(light, do_unlink=True)


if __name__ == "__main__":
    main()
