import argparse
import math
import sys
from pathlib import Path


DEFAULT_ANGLES = (90, 180, 270, 360)
DEFAULT_IMAGE_SIZE = 480
MANIFEST_NAME = ".render.tsv"
MANIFEST_VERSION = "1"


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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be rendered without writing PNGs.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Render requested angles even when cached outputs look current.",
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
    scene.render.use_file_extension = True


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


def load_manifest(manifest_path):
    if not manifest_path.is_file():
        return {}

    manifest = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition("\t")
        if not sep:
            continue
        manifest[key] = value
    return manifest


def write_manifest(manifest_path, manifest):
    temp_path = manifest_path.with_name(f"{manifest_path.name}.tmp")
    lines = [f"{key}\t{value}\n" for key, value in manifest.items()]
    temp_path.write_text("".join(lines), encoding="utf-8")
    temp_path.replace(manifest_path)


def build_manifest(stl_path, angles, image_size):
    stat_result = stl_path.stat()
    return {
        "manifest_version": MANIFEST_VERSION,
        "stl_name": stl_path.name,
        "stl_size": str(stat_result.st_size),
        "stl_mtime_ns": str(stat_result.st_mtime_ns),
        "image_size": str(image_size),
        "angles": " ".join(str(angle) for angle in angles),
    }


def determine_render_plan(stl_path, output_base, angles, image_size, force):
    output_folder = output_base / stl_path.stem
    manifest_path = output_folder / MANIFEST_NAME
    expected_manifest = build_manifest(stl_path, angles, image_size)
    current_manifest = load_manifest(manifest_path)
    stl_mtime_ns = stl_path.stat().st_mtime_ns

    requested_outputs = {angle: output_folder / f"{angle}.png" for angle in angles}
    missing_or_stale = []
    for angle, image_path in requested_outputs.items():
        if not image_path.is_file():
            missing_or_stale.append(angle)
            continue
        if image_path.stat().st_mtime_ns < stl_mtime_ns:
            missing_or_stale.append(angle)

    if force:
        return output_folder, list(angles), "forced", expected_manifest

    if not current_manifest:
        if missing_or_stale:
            return output_folder, missing_or_stale, "missing-or-stale", expected_manifest
        return output_folder, [], "existing-output", expected_manifest

    if current_manifest != expected_manifest:
        return output_folder, list(angles), "stale-manifest", expected_manifest

    if missing_or_stale:
        return output_folder, missing_or_stale, "missing-or-stale", expected_manifest

    return output_folder, [], "up-to-date", expected_manifest


def render_angle(bpy, scene, obj, output_folder, angle):
    final_path = output_folder / f"{angle}.png"
    temp_path = output_folder / f".{angle}.tmp.png"

    obj.rotation_euler = (0, 0, math.radians(angle))
    scene.render.filepath = str(temp_path)
    bpy.ops.render.render(write_still=True)

    rendered_path = temp_path
    alternate_path = Path(f"{temp_path}.png")
    if not rendered_path.is_file() and alternate_path.is_file():
        rendered_path = alternate_path

    if not rendered_path.is_file():
        raise SystemExit(f"Render did not produce output: {temp_path}")

    rendered_path.replace(final_path)


def render_part(bpy, scene, stl_path, output_folder, angles):
    clear_mesh_objects(bpy)

    bpy.ops.wm.stl_import(filepath=str(stl_path))
    obj = bpy.context.selected_objects[0]
    center_and_scale(bpy, obj)

    output_folder.mkdir(parents=True, exist_ok=True)

    for angle in angles:
        render_angle(bpy, scene, obj, output_folder, angle)


def main():
    args = parse_args(get_script_argv())

    input_folder = args.input_folder.expanduser().resolve()
    output_base = (args.output_base or input_folder).expanduser().resolve()

    if not input_folder.is_dir():
        raise SystemExit(f"Input folder does not exist: {input_folder}")

    stl_files = sorted(input_folder.glob("*.stl"))
    if not stl_files:
        raise SystemExit(f"No STL files found in {input_folder}")

    plans = []
    for stl_path in stl_files:
        output_folder, angles_to_render, reason, expected_manifest = determine_render_plan(
            stl_path,
            output_base,
            args.angles,
            args.image_size,
            args.force,
        )

        if not angles_to_render:
            print(f"skip\t{stl_path}\t{reason}")
            continue

        if args.dry_run:
            joined_angles = " ".join(str(angle) for angle in angles_to_render)
            print(f"would_render\t{stl_path}\t{joined_angles}\t{reason}")
            continue

        plans.append((stl_path, output_folder, angles_to_render, expected_manifest, reason))

    if args.dry_run or not plans:
        return

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

    for stl_path, output_folder, angles_to_render, expected_manifest, reason in plans:
        render_part(bpy, scene, stl_path, output_folder, angles_to_render)
        write_manifest(output_folder / MANIFEST_NAME, expected_manifest)
        joined_angles = " ".join(str(angle) for angle in angles_to_render)
        print(f"rendered\t{stl_path}\t{joined_angles}\t{reason}")


if __name__ == "__main__":
    main()
