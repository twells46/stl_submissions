"""Fall game dimension boundaries, oriented Blender boxes, and receipt warnings."""

import math
import itertools
from pathlib import Path
import tempfile
import unittest

import compose
import render
from part_sizes import (
    SIZE_GROUPS, rounded_extents_mm, size_group_for_extents,
)


class SizeTests(unittest.TestCase):
    def test_round_each_dimension_up(self):
        self.assertEqual(rounded_extents_mm((59.1, 59.1, 19.1)), (60, 60, 20))
        self.assertEqual(size_group_for_extents((60.001, 60, 20)), "mid-size")
        self.assertIsNone(size_group_for_extents((220, 220, 250.001)))

    def test_projection_noise_at_integer_boundary(self):
        self.assertEqual(rounded_extents_mm((60.00001, 59.99999, 20.00001)), (60, 60, 20))

    def test_group_boundaries_are_inclusive(self):
        for name, dimensions, _ in SIZE_GROUPS:
            for permutation in itertools.permutations(dimensions):
                with self.subTest(name=name, dimensions=permutation):
                    self.assertEqual(size_group_for_extents(permutation), name)

    def test_every_dimension_must_fit(self):
        for dimensions, expected in [((61, 10, 10), "mid-size"),
                                     ((30, 30, 30), "mid-size"),
                                     ((81, 81, 81), "large"),
                                     ((221, 221, 1), None),
                                     ((251, 1, 1), None),
                                     ((300, 10, 10), None)]:
            with self.subTest(dimensions=dimensions):
                self.assertEqual(size_group_for_extents(dimensions), expected)

    def test_search_minimizes_unrounded_box_before_classification(self):
        # Rounded volume would favor the second, geometrically larger box.
        self.assertLess(render.score_extents((60.001, 10, 10)),
                        render.score_extents((60, 10.01, 10)))

    def test_manifest_records_rounded_dimensions_and_group(self):
        manifest = render.build_fit_manifest({
            "status": "fits", "sorted_extents_mm": (19.1, 59.1, 59.1), "message": None,
        })
        self.assertEqual(manifest["fit_measured_mm"], "20 60 60")
        self.assertNotIn("fit_volume_mm3", manifest)
        self.assertEqual(manifest["fit_size_group"], "small")
        expected = {"stl_name": "test.stl", "stl_size": "1", "stl_mtime_ns": "2"}
        manifest.update(expected)
        self.assertFalse(render.fit_check_needs_update(manifest, expected))
        for old_version in ("1", "2"):
            manifest["fit_check_version"] = old_version
            self.assertTrue(render.fit_check_needs_update(manifest, expected))

    def test_unknown_does_not_get_a_size_group(self):
        manifest = render.build_fit_manifest({
            "status": "unknown", "sorted_extents_mm": None, "message": "timed out",
        })
        self.assertNotIn("fit_size_group", manifest)


class ReceiptTests(unittest.TestCase):
    def parts(self, small=0, mid=0, large=0, oversized=0):
        groups = ["small"] * small + ["mid-size"] * mid + ["large"] * large + [None] * oversized
        return [dict(name=str(i), display_name=f"Part {i}", cid=str(i),
                     size_group=group, oversized=group is None)
                for i, group in enumerate(groups)]

    def test_no_warning_at_each_allowance(self):
        self.assertIsNone(compose.build_tournament_limit_notice(self.parts(6, 2, 1)))

    def test_each_group_over_limit_warns_in_both_formats(self):
        parts = self.parts(7, 3, 2, 1)
        for builder in (compose.build_plain_text, compose.build_html):
            body = builder("123", "Test", 2026, parts)
            for text in ("7 small parts", "3 mid-size parts", "2 large parts",
                         "220 × 220 × 250 mm", "Teams may submit as many parts as they like",
                         "fielded during a run"):
                self.assertIn(text, body)
            self.assertNotIn("may only use", body)
            self.assertNotIn("mm³", body)
            self.assertNotIn("volume", body)

    def test_nine_small_parts_get_an_advisory(self):
        notice = compose.build_tournament_limit_notice(self.parts(small=9))
        self.assertIn("9 small parts", notice)
        self.assertIn("may need review", notice)

    def test_collection_ignores_old_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            team = Path(directory)
            (team / "part.stl").touch()
            folder = team / "part"
            folder.mkdir()
            (folder / "270.png").touch()
            manifest_path = folder / ".render.tsv"
            for old_version in ("1", "2"):
                render.write_manifest(manifest_path, {
                    "fit_check_version": old_version, "fit_status": "fits",
                    "fit_size_group": "small",
                })
                part = compose.collect_parts(team, "123", 270)[0]
                self.assertFalse(part["oversized"])
                self.assertIsNone(part["size_group"])
            render.write_manifest(manifest_path, render.build_fit_manifest({
                "status": "oversized", "sorted_extents_mm": (10, 10, 300), "message": None,
            }))
            part = compose.collect_parts(team, "123", 270)[0]
            self.assertEqual(part["size_group"], "oversized")
            self.assertTrue(part["oversized"])


class BlenderTests(unittest.TestCase):
    def check_box(self, dimensions, expected, angles=(0, 0, 0)):
        import bpy

        bpy.ops.mesh.primitive_cube_add(size=1)
        obj = bpy.context.object
        obj.dimensions = dimensions
        obj.rotation_euler = tuple(math.radians(angle) for angle in angles)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        try:
            result = render.run_fit_check(obj)
            self.assertEqual(result["status"], "oversized" if expected is None else "fits")
            self.assertEqual(result["sorted_extents_mm"], tuple(sorted(rounded_extents_mm(dimensions))))
            manifest = render.build_fit_manifest(result)
            self.assertEqual(manifest["fit_size_group"], expected or "oversized")
        finally:
            bpy.data.objects.remove(obj, do_unlink=True)

    def test_actual_mesh_bounding_boxes(self):
        for dimensions, expected in [((60, 60, 20), "small"),
                                     ((61, 60, 20), "mid-size"),
                                     ((61, 10, 10), "mid-size"),
                                     ((30, 30, 30), "mid-size"),
                                     ((220, 220, 80), "mid-size"),
                                     ((220, 220, 250), "large"),
                                     ((221, 220, 250), None),
                                     ((300, 10, 10), None)]:
            with self.subTest(dimensions=dimensions):
                self.check_box(dimensions, expected)

    def test_rotated_mesh_uses_smallest_box(self):
        for dimensions, expected in [((60, 60, 20), "small"),
                                     ((61, 10, 10), "mid-size"),
                                     ((220, 220, 80), "mid-size"),
                                     ((220, 220, 250), "large"),
                                     ((300, 10, 10), None)]:
            with self.subTest(dimensions=dimensions):
                self.check_box(dimensions, expected, angles=(17, 31, 43))


if __name__ == "__main__":
    unittest.main()
