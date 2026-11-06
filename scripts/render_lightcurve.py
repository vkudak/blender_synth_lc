"""Render a low-cost synthetic light curve from a Blender spacecraft model."""

import argparse
from math import ceil
import csv
from datetime import datetime
import json
import random
import secrets
import sys
import tempfile
from math import degrees, radians, tau
from pathlib import Path
from xml.etree import ElementTree as ET

import bmesh
import bpy
from mathutils import Quaternion, Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
EARTH_RADIUS_M = 6_371_000.0
SUN_DISTANCE_M = 149_597_870_700.0
sys.path.insert(0, str(REPO_ROOT / "src"))
for module_name in tuple(sys.modules):
    if module_name == "blender_synth_lc" or module_name.startswith("blender_synth_lc."):
        del sys.modules[module_name]

from blender_synth_lc.attitude import (
    is_rotating,
    load_model_spin_axes,
    precession_phase_rad,
    sample_precession_parameters,
    sample_spin_axis,
    sample_spin_period_s,
    spin_phase_rad,
)
from blender_synth_lc.illumination import (
    eclipse_fraction,
    is_eclipsed,
    sample_sun_direction,
)
from blender_synth_lc.orbit import (
    CircularOrbit,
    GroundObserver,
    align_orbit_for_pass,
    longest_visible_window,
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
        if obj.type == "MESH"
        and obj.name != "SyntheticEarth"
        and obj.data is not None
        and len(obj.data.vertices)
    ]


def combined_world_bounds(meshes):
    points = []
    for mesh in meshes:
        points.extend(mesh.matrix_world @ Vector(corner) for corner in mesh.bound_box)
    center = sum(points, Vector()) / len(points)
    radius = max((point - center).length for point in points)
    size = max(
        max(point[axis] for point in points) - min(point[axis] for point in points)
        for axis in range(3)
    )
    return center, radius, size


def parent_meshes_to_root(scene, meshes, center, model_scale):
    root = bpy.data.objects.new("SyntheticSatelliteRoot", None)
    scene.collection.objects.link(root)
    root.location = center
    bpy.context.view_layer.update()
    for mesh in meshes:
        world_matrix = mesh.matrix_world.copy()
        mesh.parent = root
        mesh.matrix_world = world_matrix
    root.scale = (model_scale,) * 3
    root.location = (0.0, 0.0, 0.0)
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


def add_spatial_references(scene, meters_per_unit):
    earth_radius = EARTH_RADIUS_M / meters_per_unit
    earth_mesh = bpy.data.meshes.new("SyntheticEarthMesh")
    sphere = bmesh.new()
    bmesh.ops.create_uvsphere(
        sphere,
        u_segments=32,
        v_segments=16,
        radius=earth_radius,
    )
    sphere.to_mesh(earth_mesh)
    sphere.free()
    earth = bpy.data.objects.new("SyntheticEarth", earth_mesh)
    scene.collection.objects.link(earth)
    for polygon in earth.data.polygons:
        polygon.use_smooth = True

    material = bpy.data.materials.new("SyntheticEarthMaterial")
    material.diffuse_color = (0.035, 0.16, 0.34, 1.0)
    material.use_nodes = True
    material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
        0.035, 0.16, 0.34, 1.0
    )
    earth.data.materials.append(material)

    observer = bpy.data.objects.new("SyntheticObserver", None)
    scene.collection.objects.link(observer)
    observer.empty_display_type = "SPHERE"
    observer.empty_display_size = earth_radius * 0.01
    return observer


def add_camera_and_sun(
    scene,
    target,
    target_object,
    observer_direction,
    camera_distance,
    sun_direction,
    sun_energy,
):
    camera_data = bpy.data.cameras.new("SyntheticObserverCamera")
    camera = bpy.data.objects.new("SyntheticObserverCamera", camera_data)
    scene.collection.objects.link(camera)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = camera_distance * 1.3
    camera_data.clip_start = max(camera_distance * 1e-3, 1e-9)
    camera.location = target + observer_direction * camera_distance
    track_constraint = camera.constraints.new(type="TRACK_TO")
    track_constraint.target = target_object
    track_constraint.track_axis = "TRACK_NEGATIVE_Z"
    track_constraint.up_axis = "UP_Y"
    scene.camera = camera

    light_data = bpy.data.lights.new("SyntheticSun", type="SUN")
    light = bpy.data.objects.new("SyntheticSun", light_data)
    scene.collection.objects.link(light)
    light_data.energy = sun_energy
    light.rotation_euler = (-sun_direction).to_track_quat("-Z", "Y").to_euler()
    return camera, light


def show_camera_in_viewports():
    screen = bpy.context.screen
    if screen is None:
        return
    for area in screen.areas:
        if area.type == "VIEW_3D":
            area.spaces.active.region_3d.view_perspective = "CAMERA"


def add_playback_animation(
    scene,
    scenario,
    satellite_root,
    camera,
    earth,
    observer_marker,
    light,
    observer_position,
    camera_distance,
    scene_units_per_m,
    original_rotation,
):
    samples = scenario["samples"]
    start_time_s = samples[0].time_from_closest_approach_s
    end_time_s = samples[-1].time_from_closest_approach_s
    frames_per_second = scene.render.fps / scene.render.fps_base
    frame_start = 1
    frame_count = ceil((end_time_s - start_time_s) * frames_per_second) + 1
    satellite_root.animation_data_clear()
    camera.animation_data_clear()
    scene.frame_start = frame_start
    scene.frame_end = frame_start + frame_count - 1
    sun_position = (
        Vector(scenario["sun_direction"]).normalized()
        * (SUN_DISTANCE_M * scene_units_per_m)
    )

    for frame_offset in range(frame_count):
        frame = frame_start + frame_offset
        time_s = min(start_time_s + frame_offset / frames_per_second, end_time_s)
        position_m, _ = scenario["visible_pass"].orbit.position_velocity_eci(time_s)
        satellite_position = Vector(position_m) * scene_units_per_m
        satellite_root.location = (0.0, 0.0, 0.0)
        satellite_root.rotation_quaternion = satellite_rotation(
            scenario, original_rotation, time_s
        )
        camera.location = satellite_root.location + (
            observer_position - satellite_position
        ).normalized() * camera_distance
        earth.location = -satellite_position
        observer_marker.location = observer_position - satellite_position
        light.location = sun_position - satellite_position
        satellite_root.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        camera.keyframe_insert(data_path="location", frame=frame)
        earth.keyframe_insert(data_path="location", frame=frame)
        observer_marker.keyframe_insert(data_path="location", frame=frame)
        light.keyframe_insert(data_path="location", frame=frame)

    closest_approach_frame = frame_start + round(
        -start_time_s * frames_per_second
    )
    scene.frame_set(min(closest_approach_frame, scene.frame_end))


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


def satellite_rotation(scenario, original_rotation, time_s):
    spin_axis = Vector(scenario["spin_axis"]).normalized()
    spin_rotation = Quaternion(
        spin_axis,
        spin_phase_rad(
            scenario["spin_period_s"], time_s, scenario["initial_phase_rad"]
        ),
    )
    rotation = original_rotation.copy()
    if scenario["precession_active"]:
        precession_phase = precession_phase_rad(
            scenario["precession_period_s"],
            time_s,
            scenario["precession_phase_rad"],
        )
        reference_axis = min(
            (Vector((1.0, 0.0, 0.0)), Vector((0.0, 1.0, 0.0)), Vector((0.0, 0.0, 1.0))),
            key=lambda axis: abs(spin_axis.dot(axis)),
        )
        precession_axis = spin_axis.cross(reference_axis).normalized()
        precession_rotation = (
            Quaternion(spin_axis, precession_phase)
            @ Quaternion(precession_axis, radians(scenario["precession_angle_deg"]))
            @ Quaternion(spin_axis, -precession_phase)
        )
        rotation @= precession_rotation
    return rotation @ spin_rotation


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
        fraction = eclipse_fraction(positions, config.sun_direction)
        if fraction > config.max_eclipse_fraction:
            raise ValueError(
                f"Configured Sun direction eclipses {fraction:.1%} of the visible pass; "
                f"maximum allowed is {config.max_eclipse_fraction:.1%}"
            )
        return config.sun_direction
    for _ in range(256):
        sun_direction = sample_sun_direction(rng)
        if eclipse_fraction(positions, sun_direction) <= config.max_eclipse_fraction:
            return sun_direction
    raise RuntimeError(
        "Could not sample a Sun direction within the configured maximum eclipse fraction"
    )


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
    samples = longest_visible_window(samples)
    if len(samples) < 2:
        raise RuntimeError("Visible pass has fewer than two consecutive samples")
    sun_direction = build_sun_direction(
        config, rng, tuple(sample.position_m for sample in samples)
    )
    precession_angle_deg = config.precession_angle_deg
    precession_period_s = config.precession_period_s
    precession_phase_rad_value = radians(config.precession_phase_deg)
    if config.kind == "dataset":
        (
            precession_angle_deg,
            precession_period_s,
            precession_phase_rad_value,
        ) = sample_precession_parameters(
            rng,
            rotating=spin_period_s > 0.0,
            angle_min_deg=config.precession_angle_min_deg,
            angle_max_deg=config.precession_angle_max_deg,
            period_min_s=config.precession_period_min_s,
            period_max_s=config.precession_period_max_s,
        )
    return {
        "observer": observer,
        "visible_pass": visible_pass,
        "samples": samples,
        "spin_period_s": spin_period_s,
        "initial_phase_rad": initial_phase_rad,
        "spin_axis": spin_axis,
        "precession_angle_deg": precession_angle_deg,
        "precession_period_s": precession_period_s,
        "precession_phase_rad": precession_phase_rad_value,
        "precession_active": spin_period_s > 0.0 and precession_angle_deg > 0.0,
        "sun_direction": sun_direction,
    }


def write_curve_files(args, curve_index, scenario, satellite_root, meshes, device, scene, camera, light):
    samples = scenario["samples"]
    if any(not sample.visible for sample in samples):
        raise RuntimeError("Selected pass contains samples below the observer elevation mask")
    observer = scenario["observer"]
    visible_pass = scenario["visible_pass"]
    spin_period_s = scenario["spin_period_s"]
    sun_direction = Vector(scenario["sun_direction"]).normalized()
    scene_units_per_m = 1.0 / args.scene_meters_per_unit
    observer_position = Vector(observer_position_fixed_frame(observer)) * scene_units_per_m
    satellite_root.location = (0.0, 0.0, 0.0)
    original_location = satellite_root.location.copy()
    satellite_root.rotation_mode = "QUATERNION"
    original_rotation = satellite_root.rotation_quaternion.copy()
    camera_distance = max(
        scenario["model_radius"] * 1.8,
        args.satellite_size_m * scene_units_per_m * 1.2,
    )
    camera.data.clip_start = max(camera_distance * 1e-3, 1e-9)
    light.rotation_euler = (-sun_direction).to_track_quat("-Z", "Y").to_euler()
    earth = bpy.data.objects["SyntheticEarth"]
    observer_marker = bpy.data.objects["SyntheticObserver"]
    initial_satellite_position = Vector(samples[0].position_m) * scene_units_per_m
    sun_position = sun_direction * (SUN_DISTANCE_M * scene_units_per_m)
    earth.location = -initial_satellite_position
    observer_marker.location = observer_position - initial_satellite_position
    light.location = sun_position - initial_satellite_position

    raw_fluxes = []
    corrected_fluxes = []
    eclipsed_flags = [
        is_eclipsed(sample.position_m, tuple(sun_direction)) for sample in samples
    ]
    actual_eclipse_fraction = sum(eclipsed_flags) / len(eclipsed_flags)
    if actual_eclipse_fraction > args.max_eclipse_fraction:
        raise RuntimeError(
            f"Selected pass has {actual_eclipse_fraction:.1%} eclipsed samples; "
            f"maximum allowed is {args.max_eclipse_fraction:.1%}"
        )
    reference_range_m = samples[0].range_m
    with tempfile.TemporaryDirectory(prefix="blender-synth-lc-") as temp_dir:
        frame_path = Path(temp_dir) / "frame.exr"
        for sample, eclipsed in zip(samples, eclipsed_flags):
            if eclipsed:
                raw_fluxes.append(0.0)
                corrected_fluxes.append(0.0)
                continue

            time_s = sample.time_from_closest_approach_s
            sample_position = Vector(sample.position_m) * scene_units_per_m
            satellite_root.rotation_quaternion = satellite_rotation(
                scenario, original_rotation, time_s
            )
            bpy.context.view_layer.update()
            target = satellite_root.location.copy()
            view_direction = (observer_position - sample_position).normalized()
            camera.location = target + view_direction * camera_distance
            earth.location = -sample_position
            observer_marker.location = observer_position - sample_position
            light.location = sun_position - sample_position
            raw_flux = render_flux(scene, frame_path)
            corrected_flux = raw_flux * (reference_range_m / sample.range_m) ** 2
            raw_fluxes.append(raw_flux)
            corrected_fluxes.append(corrected_flux)

    satellite_root.location = original_location
    satellite_root.rotation_quaternion = original_rotation
    initial_view_direction = (observer_position - initial_satellite_position).normalized()
    camera.location = initial_view_direction * camera_distance
    earth.location = -initial_satellite_position
    observer_marker.location = observer_position - initial_satellite_position
    light.location = sun_position - initial_satellite_position
    bpy.context.view_layer.update()
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
            "duration_s": (
                samples[-1].time_from_closest_approach_s
                - samples[0].time_from_closest_approach_s
            ),
            "requested_duration_s": args.duration_s,
            "cadence_s": args.cadence_s,
            "minimum_elevation_deg": args.minimum_elevation_deg,
            "sample_count": len(samples),
            "visible_sample_count": sum(sample.visible for sample in samples),
        },
        "attitude": {
            "spin_period_s": spin_period_s,
            "rotating": is_rotating(spin_period_s),
            "initial_phase_rad": scenario["initial_phase_rad"],
            "spin_axis": list(scenario["spin_axis"]),
            "precession_angle_deg": scenario["precession_angle_deg"],
            "precession_period_s": scenario["precession_period_s"],
            "precession_phase_deg": degrees(scenario["precession_phase_rad"]),
            "precession_active": scenario["precession_active"],
        },
        "render": {
            "blender_version": bpy.app.version_string,
            "engine": scene.render.engine,
            "device": device,
            "resolution": args.resolution,
            "samples": args.samples,
            "denoising": scene.cycles.use_denoising,
            "exposure_ev": args.exposure,
            "sun_irradiance_w_m2": args.sun_energy,
            "eclipse_fraction": actual_eclipse_fraction,
            "max_eclipse_fraction": args.max_eclipse_fraction,
            "camera_ortho_scale_m": camera.data.ortho_scale * args.scene_meters_per_unit,
            "scene_meters_per_unit": args.scene_meters_per_unit,
            "satellite_max_extent_m": args.satellite_size_m,
            "sun_distance_m": SUN_DISTANCE_M,
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
    if args.script_output is not None and not bpy.app.background:
        add_playback_animation(
            scene,
            scenario,
            satellite_root,
            camera,
            earth,
            observer_marker,
            light,
            observer_position,
            camera_distance,
            scene_units_per_m,
            original_rotation,
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
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = args.scene_meters_per_unit
    model_center, model_radius, model_size = combined_world_bounds(meshes)
    if model_size <= 0.0:
        raise RuntimeError("Cannot scale a model with zero-size mesh bounds")
    scene_units_per_m = 1.0 / args.scene_meters_per_unit
    model_scale = args.satellite_size_m * scene_units_per_m / model_size
    satellite_root = parent_meshes_to_root(scene, meshes, model_center, model_scale)
    device = configure_device(scene, args.device)
    scene.cycles.samples = args.samples
    scene.cycles.max_bounces = 2
    scene.cycles.use_denoising = True
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    if hasattr(scene.render, "use_persistent_data"):
        scene.render.use_persistent_data = True
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = args.exposure
    scene.view_settings.gamma = 1.0

    observer_marker = add_spatial_references(scene, args.scene_meters_per_unit)
    dummy_sun = Vector((0.0, 0.0, 1.0))
    camera, light = add_camera_and_sun(
        scene, satellite_root.location, satellite_root, Vector((0.0, -1.0, 0.0)),
        max(
            model_radius * model_scale * 1.8,
            args.satellite_size_m * scene_units_per_m * 1.2,
        ),
        dummy_sun,
        args.sun_energy,
    )

    for curve_index in range(args.count):
        scenario = build_scenario(args, curve_index, model_spin_axes)
        scenario["model_radius"] = model_radius * model_scale
        write_curve_files(
            args, curve_index, scenario, satellite_root, meshes, device, scene, camera, light
        )

    if args.script_output is None:
        bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.objects.remove(light, do_unlink=True)
    else:
        show_camera_in_viewports()


if __name__ == "__main__":
    main()
