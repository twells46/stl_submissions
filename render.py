import argparse
import math
import sys
from pathlib import Path


DEFAULT_ANGLES = (90, 180, 270, 360)
DEFAULT_IMAGE_SIZE = 480


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description=(
            "Render all STL files in a team directory into per-part image folders. "
            "When running through Blender, pass script arguments after '--'."
        )
    )
    parser.add_argument(
        "input_folder",
        type=Path,
        help="Directory containing STL files for a single team submission.",
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        help="Base directory for rendered images. Defaults to the input folder.",
    )
    parser.add_argument(
        "--angles",
        nargs="+",
        type=int,
        default=list(DEFAULT_ANGLES),
        help="Angles to render for each part. Defaults to 90 180 270 360.",
    )
    parser.add_argument(
        "--image-size",
        type=int,
        default=DEFAULT_IMAGE_SIZE,
        help="Width and height of each rendered PNG in pixels. Defaults to 480.",
    )
    return parser.parse_args(argv)


def get_script_argv():
    if "--" in sys.argv:
        return sys.argv[sys.argv.index("--") + 1 :]
    return sys.argv[1:]


def clear_scene(bpy):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)


def configure_camera_and_light(bpy):
    camera_data = bpy.data.cameras.new(name="Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.location = (2, -2, 2)
    camera.rotation_euler = (math.radians(55), 0, math.radians(47))

    light_data = bpy.data.lights.new(name="Light", type="AREA")
    light_data.energy = 900
    light = bpy.data.objects.new(name="Light", object_data=light_data)
    light.location = (5, -5, 10)
    bpy.context.collection.objects.link(light)


def configure_scene_rendering(scene, image_size):
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.compression = 100
    scene.render.resolution_x = image_size
    scene.render.resolution_y = image_size


def center_and_scale(bpy, obj):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY", center="BOUNDS")
    obj.location = (0, 0, 0)
    obj.rotation_euler = (0, 0, math.radians(-80))

    max_dim = max(obj.dimensions)
    if max_dim > 0:
        scale = 1.5 / max_dim
        obj.scale = (scale, scale, scale)
        bpy.ops.object.transform_apply(scale=True)


def clear_mesh_objects(bpy):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.select_set(True)
    bpy.ops.object.delete()


def render_part(bpy, scene, stl_path, output_base, angles):
    clear_mesh_objects(bpy)

    bpy.ops.wm.stl_import(filepath=str(stl_path))
    obj = bpy.context.selected_objects[0]
    center_and_scale(bpy, obj)

    output_folder = output_base / stl_path.stem
    output_folder.mkdir(parents=True, exist_ok=True)

    for angle in angles:
        obj.rotation_euler = (0, 0, math.radians(angle))
        scene.render.filepath = str(output_folder / f"{angle}.png")
        bpy.ops.render.render(write_still=True)


def main():
    args = parse_args(get_script_argv())

    input_folder = args.input_folder.expanduser().resolve()
    output_base = (args.output_base or input_folder).expanduser().resolve()

    if not input_folder.is_dir():
        raise SystemExit(f"Input folder does not exist: {input_folder}")

    stl_files = sorted(input_folder.glob("*.stl"))
    if not stl_files:
        raise SystemExit(f"No STL files found in {input_folder}")

    try:
        import bpy
    except ImportError as exc:
        raise SystemExit(
            "render.py must be run with Blender's Python environment "
            "(for example: blender --background --python render.py -- <team-dir>)."
        ) from exc

    clear_scene(bpy)
    configure_camera_and_light(bpy)

    scene = bpy.context.scene
    configure_scene_rendering(scene, args.image_size)

    for stl_path in stl_files:
        render_part(bpy, scene, stl_path, output_base, args.angles)


if __name__ == "__main__":
    main()
