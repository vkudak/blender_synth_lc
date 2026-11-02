import argparse
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector


SUPPORTED_BLENDER = (4, 5)


def parse_arguments():
    arguments = sys.argv
    if "--" not in arguments:
        return argparse.Namespace(output=None)

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    return parser.parse_args(arguments[arguments.index("--") + 1 :])


def bounds_report(obj, matrix_world):
    if obj.type != "MESH" or len(obj.data.vertices) == 0:
        return None

    points = [matrix_world @ Vector(corner) for corner in obj.bound_box]
    minimum = [min(point[axis] for point in points) for axis in range(3)]
    maximum = [max(point[axis] for point in points) for axis in range(3)]
    return {
        "min": minimum,
        "max": maximum,
        "size": [maximum[axis] - minimum[axis] for axis in range(3)],
    }


def object_report(obj, depsgraph):
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.data if evaluated.type == "MESH" else None
    return {
        "name": obj.name,
        "type": obj.type,
        "parent": obj.parent.name if obj.parent else None,
        "origin_world": list(evaluated.matrix_world.translation),
        "scale": list(obj.scale),
        "hide_render": obj.hide_render,
        "mesh_vertices": len(mesh.vertices) if mesh is not None else None,
        "mesh_polygons": len(mesh.polygons) if mesh is not None else None,
        "materials": [
            slot.material.name if slot.material else None
            for slot in obj.material_slots
        ],
        "world_bounds": bounds_report(evaluated, evaluated.matrix_world),
    }


def combined_mesh_bounds(depsgraph):
    minimum = [float("inf")] * 3
    maximum = [float("-inf")] * 3
    found_mesh = False

    for instance in depsgraph.object_instances:
        obj = instance.object
        if obj.type != "MESH" or len(obj.data.vertices) == 0:
            continue

        found_mesh = True
        for corner in obj.bound_box:
            point = instance.matrix_world @ Vector(corner)
            for axis in range(3):
                minimum[axis] = min(minimum[axis], point[axis])
                maximum[axis] = max(maximum[axis], point[axis])

    if not found_mesh:
        return None

    return {
        "min": minimum,
        "max": maximum,
        "size": [maximum[axis] - minimum[axis] for axis in range(3)],
    }


def image_report(image):
    path = bpy.path.abspath(image.filepath) if image.filepath else ""
    return {
        "name": image.name,
        "source": image.source,
        "filepath": image.filepath,
        "resolved_path": path,
        "packed": image.packed_file is not None,
        "path_exists": Path(path).is_file() if path else None,
    }


def build_report():
    if bpy.app.version[:2] != SUPPORTED_BLENDER:
        required = ".".join(str(part) for part in SUPPORTED_BLENDER)
        raise RuntimeError(
            f"This inventory targets Blender {required}.x; "
            f"running {bpy.app.version_string}"
        )

    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return {
        "blender_version": bpy.app.version_string,
        "blend_file": bpy.data.filepath,
        "scene": {
            "name": scene.name,
            "unit_system": scene.unit_settings.system,
            "length_unit": scene.unit_settings.length_unit,
            "scale_length": scene.unit_settings.scale_length,
            "frame_start": scene.frame_start,
            "frame_end": scene.frame_end,
            "render_engine": scene.render.engine,
        },
        "scene_names": [item.name for item in bpy.data.scenes],
        "objects": [object_report(obj, depsgraph) for obj in scene.objects],
        "combined_mesh_world_bounds": combined_mesh_bounds(depsgraph),
        "images": [
            image_report(image)
            for image in bpy.data.images
            if image.source != "GENERATED"
        ],
        "libraries": [
            {
                "filepath": library.filepath,
                "resolved_path": bpy.path.abspath(library.filepath),
                "path_exists": Path(bpy.path.abspath(library.filepath)).is_file(),
            }
            for library in bpy.data.libraries
        ],
    }


def main():
    args = parse_arguments()
    report = build_report()
    encoded = json.dumps(report, indent=2, sort_keys=True)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    else:
        print(encoded)


if __name__ == "__main__":
    main()