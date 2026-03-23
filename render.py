import argparse
import math
import sys
from pathlib import Path


DEFAULT_ANGLES = (90, 180, 270, 360)
DEFAULT_IMAGE_SIZE = 480
MANIFEST_NAME = ".render.tsv"
MANIFEST_VERSION = "2"
FIT_CHECK_VERSION = "1"
FIT_BOX_MM = (220.0, 220.0, 250.0)
FIT_BOX_MM_SORTED = tuple(sorted(FIT_BOX_MM))
FIT_NUMERIC_TOLERANCE_MM = 0.1
FIT_DIRECTION_TOLERANCE_DEGREES = 0.35
FIT_REFINEMENT_STEPS_DEGREES = (5.0, 1.0, 0.25, 0.05)
FIT_MANIFEST_KEYS = (
    "fit_check_version",
    "fit_box_mm",
    "fit_status",
    "fit_measured_mm",
    "fit_note",
)


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


def format_number(value, places=6):
    return f"{value:.{places}f}".rstrip("0").rstrip(".") or "0"


def format_triplet(values, places=6):
    return " ".join(format_number(value, places) for value in values)


def build_render_manifest(stl_path, angles, image_size):
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
    expected_render_manifest = build_render_manifest(stl_path, angles, image_size)
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
        return output_folder, list(angles), "forced", expected_render_manifest, current_manifest

    if not current_manifest:
        if missing_or_stale:
            return output_folder, missing_or_stale, "missing-or-stale", expected_render_manifest, current_manifest
        return output_folder, [], "existing-output", expected_render_manifest, current_manifest

    current_render_manifest = {
        key: current_manifest.get(key)
        for key in expected_render_manifest
    }
    if current_render_manifest != expected_render_manifest:
        return output_folder, list(angles), "stale-manifest", expected_render_manifest, current_manifest

    if missing_or_stale:
        return output_folder, missing_or_stale, "missing-or-stale", expected_render_manifest, current_manifest

    return output_folder, [], "up-to-date", expected_render_manifest, current_manifest


def fit_check_needs_update(current_manifest, expected_render_manifest):
    if not current_manifest:
        return True

    for key in ("stl_name", "stl_size", "stl_mtime_ns"):
        if current_manifest.get(key) != expected_render_manifest[key]:
            return True

    if current_manifest.get("fit_check_version") != FIT_CHECK_VERSION:
        return True

    if current_manifest.get("fit_box_mm") != format_triplet(FIT_BOX_MM, places=3):
        return True

    return current_manifest.get("fit_status") not in {"fits", "oversized", "unknown"}


def load_part_object(bpy, stl_path):
    clear_mesh_objects(bpy)
    bpy.ops.wm.stl_import(filepath=str(stl_path))
    selected_objects = list(bpy.context.selected_objects)
    if not selected_objects:
        raise SystemExit(f"STL import produced no objects: {stl_path}")
    return selected_objects[0]


def canonicalize_direction(vector, epsilon=1e-9):
    if vector.length <= epsilon:
        return None

    direction = vector.normalized()
    x_value, y_value, z_value = direction
    if (
        x_value < -epsilon
        or (abs(x_value) <= epsilon and y_value < -epsilon)
        or (abs(x_value) <= epsilon and abs(y_value) <= epsilon and z_value < -epsilon)
    ):
        direction = -direction
    return direction


def build_perpendicular_basis(primary_axis):
    helper_axes = (
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
        (0.0, 0.0, 1.0),
    )
    z_axis = canonicalize_direction(primary_axis)
    if z_axis is None:
        return None

    for helper_values in helper_axes:
        helper = z_axis.__class__(helper_values)
        x_axis = helper.cross(z_axis)
        if x_axis.length > 1e-9:
            x_axis.normalize()
            y_axis = z_axis.cross(x_axis)
            y_axis.normalize()
            return (x_axis, y_axis, z_axis)
    return None


def build_basis_from_normal_and_edge(normal, edge_direction):
    z_axis = canonicalize_direction(normal)
    if z_axis is None:
        return None

    projected_edge = edge_direction - (z_axis * edge_direction.dot(z_axis))
    if projected_edge.length <= 1e-9:
        return None

    x_axis = projected_edge.normalized()
    y_axis = z_axis.cross(x_axis)
    if y_axis.length <= 1e-9:
        return None
    y_axis.normalize()
    return (x_axis, y_axis, z_axis)


def basis_is_similar(left_basis, right_basis, cosine_tolerance):
    return all(
        abs(left_axis.dot(right_axis)) >= cosine_tolerance
        for left_axis, right_axis in zip(left_basis, right_basis)
    )


def dedupe_bases(bases, angle_tolerance_degrees):
    cosine_tolerance = math.cos(math.radians(angle_tolerance_degrees))
    unique_bases = []
    for basis in bases:
        if basis is None:
            continue
        if any(basis_is_similar(basis, existing_basis, cosine_tolerance) for existing_basis in unique_bases):
            continue
        unique_bases.append(basis)
    return unique_bases


def score_extents(extents, limits):
    sorted_extents = tuple(sorted(extents))
    ratios = tuple(sorted_extents[index] / limits[index] for index in range(3))
    overflow = tuple(max(0.0, ratio - 1.0) for ratio in ratios)
    return overflow + ratios


def measure_extents(points, basis):
    extents = []
    for axis in basis:
        minimum = None
        maximum = None
        for point in points:
            projection = axis.dot(point)
            if minimum is None or projection < minimum:
                minimum = projection
            if maximum is None or projection > maximum:
                maximum = projection
        extents.append(0.0 if minimum is None else maximum - minimum)
    return tuple(extents)


def rotate_basis(basis, axis_index, angle_radians):
    from mathutils import Matrix

    rotation = Matrix.Rotation(angle_radians, 3, basis[axis_index])
    return tuple((rotation @ axis).normalized() for axis in basis)


def refine_basis(points, basis):
    best_basis = basis
    best_extents = measure_extents(points, best_basis)
    best_score = score_extents(best_extents, FIT_BOX_MM_SORTED)

    for step_degrees in FIT_REFINEMENT_STEPS_DEGREES:
        step_radians = math.radians(step_degrees)
        improved = True
        while improved:
            improved = False
            candidate_basis = best_basis
            candidate_extents = best_extents
            candidate_score = best_score
            for axis_index in range(3):
                for direction in (-1, 1):
                    rotated_basis = rotate_basis(best_basis, axis_index, direction * step_radians)
                    rotated_extents = measure_extents(points, rotated_basis)
                    rotated_score = score_extents(rotated_extents, FIT_BOX_MM_SORTED)
                    if rotated_score < candidate_score:
                        candidate_basis = rotated_basis
                        candidate_extents = rotated_extents
                        candidate_score = rotated_score

            if candidate_score < best_score:
                best_basis = candidate_basis
                best_extents = candidate_extents
                best_score = candidate_score
                improved = True

    return best_basis, best_extents, best_score


def collect_hull_data(obj):
    import bmesh

    bm = bmesh.new()
    try:
        bm.from_mesh(obj.data)
        bm.verts.ensure_lookup_table()
        if not bm.verts:
            return [], [], []

        result = bmesh.ops.convex_hull(bm, input=list(bm.verts), use_existing_faces=False)
        bm.normal_update()

        geom = result.get("geom") or []
        hull_verts = []
        hull_faces = []
        hull_edges = []
        seen = set()
        for element in geom:
            marker = id(element)
            if marker in seen:
                continue
            seen.add(marker)
            if isinstance(element, bmesh.types.BMVert):
                hull_verts.append(element)
            elif isinstance(element, bmesh.types.BMFace):
                hull_faces.append(element)
            elif isinstance(element, bmesh.types.BMEdge):
                hull_edges.append(element)

        if not hull_verts:
            hull_verts = list(bm.verts)
        if not hull_faces:
            hull_faces = list(bm.faces)
        if not hull_edges:
            hull_edges = list(bm.edges)

        points = [vertex.co.copy() for vertex in hull_verts]
        face_records = []
        for face in hull_faces:
            if face.normal.length <= 1e-9:
                continue
            edge_directions = []
            for edge in face.edges:
                edge_vector = edge.verts[1].co - edge.verts[0].co
                direction = canonicalize_direction(edge_vector)
                if direction is not None:
                    edge_directions.append(direction)
            face_records.append(
                {
                    "normal": face.normal.copy(),
                    "edge_directions": edge_directions,
                }
            )

        global_edge_directions = []
        for edge in hull_edges:
            edge_vector = edge.verts[1].co - edge.verts[0].co
            direction = canonicalize_direction(edge_vector)
            if direction is not None:
                global_edge_directions.append(direction)

        return points, face_records, global_edge_directions
    finally:
        bm.free()


def assess_part_fit(obj):
    points, face_records, global_edge_directions = collect_hull_data(obj)
    if not points:
        return {
            "status": "unknown",
            "sorted_extents_mm": None,
            "message": "mesh contained no vertices",
        }

    seed_bases = []
    world_basis = build_perpendicular_basis(points[0].__class__((0.0, 0.0, 1.0)))
    if world_basis is not None:
        seed_bases.append(world_basis)

    for face_record in face_records:
        face_basis = build_perpendicular_basis(face_record["normal"])
        if face_basis is not None:
            seed_bases.append(face_basis)
        for edge_direction in face_record["edge_directions"]:
            edge_basis = build_basis_from_normal_and_edge(face_record["normal"], edge_direction)
            if edge_basis is not None:
                seed_bases.append(edge_basis)

    for edge_direction in global_edge_directions:
        edge_basis = build_perpendicular_basis(edge_direction)
        if edge_basis is not None:
            seed_bases.append(edge_basis)

    seed_bases = dedupe_bases(seed_bases, FIT_DIRECTION_TOLERANCE_DEGREES)
    if not seed_bases:
        return {
            "status": "unknown",
            "sorted_extents_mm": None,
            "message": "no candidate orientations were generated",
        }

    scored_seeds = []
    for basis in seed_bases:
        extents = measure_extents(points, basis)
        scored_seeds.append((score_extents(extents, FIT_BOX_MM_SORTED), extents, basis))
    scored_seeds.sort(key=lambda item: item[0])

    best_basis = None
    best_extents = None
    best_score = None
    for _, _, basis in scored_seeds[:12]:
        refined_basis, refined_extents, refined_score = refine_basis(points, basis)
        if best_score is None or refined_score < best_score:
            best_basis = refined_basis
            best_extents = refined_extents
            best_score = refined_score

    if best_basis is None or best_extents is None:
        return {
            "status": "unknown",
            "sorted_extents_mm": None,
            "message": "fit check did not converge",
        }

    sorted_extents = tuple(sorted(best_extents))
    fits = all(
        measured <= limit + FIT_NUMERIC_TOLERANCE_MM
        for measured, limit in zip(sorted_extents, FIT_BOX_MM_SORTED)
    )
    return {
        "status": "fits" if fits else "oversized",
        "sorted_extents_mm": sorted_extents,
        "message": None,
    }


def build_fit_manifest(fit_result):
    manifest = {
        "fit_check_version": FIT_CHECK_VERSION,
        "fit_box_mm": format_triplet(FIT_BOX_MM, places=3),
        "fit_status": fit_result["status"],
    }
    if fit_result["sorted_extents_mm"] is not None:
        manifest["fit_measured_mm"] = format_triplet(fit_result["sorted_extents_mm"])
    if fit_result["message"]:
        manifest["fit_note"] = fit_result["message"]
    return manifest


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


def render_loaded_part(bpy, scene, obj, output_folder, angles):
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
        output_folder, angles_to_render, reason, expected_render_manifest, current_manifest = determine_render_plan(
            stl_path,
            output_base,
            args.angles,
            args.image_size,
            args.force,
        )
        needs_fit_check = fit_check_needs_update(current_manifest, expected_render_manifest)

        if not angles_to_render and not needs_fit_check:
            print(f"skip\t{stl_path}\t{reason}")
            continue

        if args.dry_run:
            if angles_to_render:
                joined_angles = " ".join(str(angle) for angle in angles_to_render)
                print(f"would_render\t{stl_path}\t{joined_angles}\t{reason}")
            else:
                print(f"would_validate\t{stl_path}\tfit-check-update")
            continue

        plans.append(
            (
                stl_path,
                output_folder,
                angles_to_render,
                expected_render_manifest,
                current_manifest,
                needs_fit_check,
                reason,
            )
        )

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

    for (
        stl_path,
        output_folder,
        angles_to_render,
        expected_render_manifest,
        current_manifest,
        needs_fit_check,
        reason,
    ) in plans:
        obj = load_part_object(bpy, stl_path)

        try:
            fit_result = assess_part_fit(obj)
        except Exception as exc:
            fit_result = {
                "status": "unknown",
                "sorted_extents_mm": None,
                "message": f"fit check failed: {exc}",
            }
            print(f"warning\t{stl_path}\tfit-check-failed\t{exc}", file=sys.stderr)

        if angles_to_render:
            render_loaded_part(bpy, scene, obj, output_folder, angles_to_render)
            joined_angles = " ".join(str(angle) for angle in angles_to_render)
            print(f"rendered\t{stl_path}\t{joined_angles}\t{reason}")
        elif needs_fit_check:
            output_folder.mkdir(parents=True, exist_ok=True)
            print(f"validated\t{stl_path}\tfit-check-update")

        manifest = dict(current_manifest)
        for key in FIT_MANIFEST_KEYS:
            manifest.pop(key, None)
        manifest.update(expected_render_manifest)
        manifest.update(build_fit_manifest(fit_result))
        write_manifest(output_folder / MANIFEST_NAME, manifest)

        if fit_result["status"] == "oversized":
            print(
                f"oversized\t{stl_path}\t{format_triplet(fit_result['sorted_extents_mm'])}\tbox={format_triplet(FIT_BOX_MM, places=3)}"
            )


if __name__ == "__main__":
    main()
