"""Render a low-cost synthetic light curve from a Blender spacecraft model."""

import argparse
import csv
import json
import random
import sys
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

import bpy
from mathutils import Vector


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from blender_synth_lc.attitude import is_rotating, spin_phase_rad
from blender_synth_lc.orbit import (
    GroundObserver,
    observer_position_fixed_frame,
    sample_pass_window,
    sample_visible_pass,
)


def parse_args():
    blender_args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, default=REPO_ROOT / "models/Lotos_model.blend")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "reports/lotos_lightcurve.csv")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--duration-s", type=float, default=60.0)
    parser.add_argument("--cadence-s", type=float, default=10.0)
    parser.add_argument("--spin-period-s", type=float, default=20.0)
    parser.add_argument("--initial-phase-rad", type=float, default=0.0)
    parser.add_argument("--minimum-elevation-deg", type=float, default=10.0)
    parser.add_argument("--resolution", type=int, default=128)
    parser.add_argument("--samples", type=int, default=8)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda", "optix"), default="auto")
    parser.add_argument("--observer-latitude-deg", type=float, default=48.633)
    parser.add_argument("--observer-longitude-deg", type=float, default=22.33)
    args = parser.parse_args(blender_args)
    is_rotating(args.spin_period_s)
    if args.resolution < 16 or args.samples < 1:
        parser.error("resolution must be at least 16 and samples must be positive")
    return args


def configure_device(scene, requested_device):
    scene.render.engine = "CYCLES"
    cycles_addon = bpy.context.preferences.addons.get("cycles")
    preferences = cycles_addon.preferences if cycles_addon else None
    gpu_types = ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL")
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
                return {
                    "requested": requested_device,
                    "backend": preferences.compute_device_type,
                    "mode": "GPU",
                    "devices": [device.name for device in gpu_devices],
                }

    if requested_device not in ("auto", "cpu"):
        raise RuntimeError(f"Requested {requested_device.upper()} device is not available in Blender")
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


def add_camera_and_sun(scene, target, observer_direction, camera_distance, sun_direction):
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
    light_data.energy = 3.0
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


def write_diagnostic_svg(samples, relative_flux, output_path):
    namespace = "http://www.w3.org/2000/svg"
    ET.register_namespace("", namespace)
    width, height = 900, 520
    left, top, right, bottom = 82, 48, 34, 68
    plot_width = width - left - right
    plot_height = height - top - bottom
    times = [sample.time_from_closest_approach_s for sample in samples]
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
    }).text = "Lotos model | normalized flux"

    for tick in range(5):
        flux = tick / 4.0
        y = y_position(flux)
        add(root, "line", x1=str(left), y1=f"{y:.2f}",
            x2=str(width - right), y2=f"{y:.2f}", stroke="#d8e0e3", **{"stroke-width": "1"})
        add(root, "text", x=str(left - 12), y=f"{y + 4:.2f}", fill="#42545b",
            **{"font-family": "sans-serif", "font-size": "12", "text-anchor": "end"}).text = f"{flux:.2f}"

    for time_s in sorted(set((minimum_time, 0.0, maximum_time))):
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
        **{"font-family": "sans-serif", "font-size": "13", "text-anchor": "middle"}).text = "Time from closest approach (s)"
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


def main():
    args = parse_args()
    if not args.model.is_file():
        raise FileNotFoundError(args.model)
    if Path(bpy.data.filepath).resolve() != args.model.resolve():
        bpy.ops.wm.open_mainfile(filepath=str(args.model.resolve()))

    scene = bpy.context.scene
    spacecraft = [obj for obj in scene.objects if obj.type == "MESH" and len(obj.data.vertices)]
    if len(spacecraft) != 1:
        raise RuntimeError(f"Expected one non-empty mesh object, found {len(spacecraft)}")
    satellite = spacecraft[0]
    device = configure_device(scene, args.device)
    scene.cycles.samples = args.samples
    scene.cycles.max_bounces = 2
    scene.cycles.use_denoising = False
    scene.render.resolution_x = args.resolution
    scene.render.resolution_y = args.resolution
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.render.image_settings.file_format = "PNG"

    observer = GroundObserver(
        latitude_deg=args.observer_latitude_deg,
        longitude_deg=args.observer_longitude_deg,
    )
    rng = random.Random(args.seed)
    visible_pass = sample_visible_pass(
        rng,
        observer,
        minimum_elevation_deg=args.minimum_elevation_deg,
        max_attempts=1000,
    )
    samples = sample_pass_window(
        visible_pass,
        observer,
        duration_s=args.duration_s,
        cadence_s=args.cadence_s,
    )

    local_bounds = [Vector(corner) for corner in satellite.bound_box]
    local_center = sum(local_bounds, Vector()) / len(local_bounds)
    world_bounds = [satellite.matrix_world @ corner for corner in local_bounds]
    model_radius = max((point - sum(world_bounds, Vector()) / len(world_bounds)).length
                       for point in world_bounds)
    camera_distance = max(model_radius * 4.0, 4.0)
    sun_direction = Vector((0.71, -0.42, 0.56)).normalized()

    initial_orbit_position = Vector(samples[0].position_m)
    observer_position = Vector(observer_position_fixed_frame(observer))
    original_location = satellite.location.copy()
    original_rotation = satellite.rotation_euler.copy()
    satellite.rotation_mode = "XYZ"

    target = satellite.matrix_world @ local_center
    initial_view = (observer_position - Vector(samples[0].position_m)).normalized()
    camera, light = add_camera_and_sun(
        scene, target, initial_view, camera_distance, sun_direction
    )

    raw_fluxes = []
    corrected_fluxes = []
    reference_range_m = samples[0].range_m
    scene_scale_per_m = 1e-6
    with tempfile.TemporaryDirectory(prefix="blender-synth-lc-") as temp_dir:
        frame_path = Path(temp_dir) / "frame.exr"
        for sample in samples:
            time_s = sample.time_from_closest_approach_s
            satellite.location = original_location + (
                Vector(sample.position_m) - initial_orbit_position
            ) * scene_scale_per_m
            satellite.rotation_euler = original_rotation
            satellite.rotation_euler.rotate_axis(
                "Z", spin_phase_rad(args.spin_period_s, time_s, args.initial_phase_rad)
            )
            target = satellite.matrix_world @ local_center
            view_direction = (
                observer_position - Vector(sample.position_m)
            ).normalized()
            camera.location = target + view_direction * camera_distance
            camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
            raw_flux = render_flux(scene, frame_path)
            corrected_flux = raw_flux * (reference_range_m / sample.range_m) ** 2
            raw_fluxes.append(raw_flux)
            corrected_fluxes.append(corrected_flux)

    maximum_flux = max(corrected_fluxes)
    if maximum_flux <= 0.0:
        raise RuntimeError("Rendered flux is zero for every sample; inspect the model materials and lighting")

    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.writer(output_file)
        writer.writerow((
            "time_from_closest_approach_s",
            "range_m",
            "azimuth_deg",
            "elevation_deg",
            "visible",
            "render_flux_linear_rgb",
            "flux_with_range_correction",
            "relative_flux",
        ))
        for sample, raw_flux, corrected_flux in zip(samples, raw_fluxes, corrected_fluxes):
            writer.writerow((
                sample.time_from_closest_approach_s,
                sample.range_m,
                sample.azimuth_deg,
                sample.elevation_deg,
                int(sample.visible),
                raw_flux,
                corrected_flux,
                corrected_flux / maximum_flux,
            ))
    relative_flux = [flux / maximum_flux for flux in corrected_fluxes]
    plot_path = output_path.with_suffix(".svg")
    write_diagnostic_svg(samples, relative_flux, plot_path)

    metadata = {
        "model": str(args.model.resolve()),
        "mesh_object": satellite.name,
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
            "spin_period_s": args.spin_period_s,
            "rotating": is_rotating(args.spin_period_s),
            "initial_phase_rad": args.initial_phase_rad,
        },
        "render": {
            "blender_version": bpy.app.version_string,
            "engine": scene.render.engine,
            "device": device,
            "resolution": args.resolution,
            "samples": args.samples,
            "sun_direction_eci": list(sun_direction),
        },
        "photometry": {
            "flux_definition": "sum of linear RGB render pixels, multiplied by reference_range^2/range^2",
            "normalized_to_maximum": True,
            "limitations": [
                "model bounds are not calibrated to physical spacecraft dimensions",
                "fixed synthetic sun direction; no Earth shadow, atmosphere, or calibrated surface photometry",
                "relative flux is a rendering proxy, not an absolute magnitude",
            ],
        },
        "diagnostic_plot": str(plot_path),
    }
    output_path.with_suffix(".json").write_text(
        json.dumps(metadata, indent=2) + "\n", encoding="utf-8"
    )

    satellite.location = original_location
    satellite.rotation_euler = original_rotation
    bpy.data.objects.remove(camera, do_unlink=True)
    bpy.data.objects.remove(light, do_unlink=True)
    print(f"Wrote {len(samples)} samples to {output_path}")
    print(f"Render device: {device['mode']} ({device['backend']})")
    print(f"Relative flux range: {min(corrected_fluxes) / maximum_flux:.6g}..1")


if __name__ == "__main__":
    main()