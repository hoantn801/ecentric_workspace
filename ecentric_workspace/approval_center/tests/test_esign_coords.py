# Copyright (c) 2026, eCentric and contributors
"""Deterministic geometry/unit tests for the placement coordinate system (Phase 1). These
are frappe-free (pure math) and run in any Python; they also run under bench run-tests."""
import unittest

from ecentric_workspace.approval_center.esign import coords as C

PAGE = (612.0, 792.0)  # US Letter, unrotated mediabox


class TestCoords(unittest.TestCase):
    def test_round_trip_all_rotations_scales(self):
        rect = {"x": 100.0, "y": 150.0, "width": 120.0, "height": 40.0}
        for rot in (0, 90, 180, 270):
            for s in (0.75, 1.0, 1.5, 2.0):
                vp = C.canonical_rect_to_viewport(rect, PAGE, s, rot)
                back = C.viewport_rect_to_canonical(vp, PAGE, s, rot)
                for k in rect:
                    self.assertAlmostEqual(back[k], rect[k], places=2,
                                           msg="rot=%s scale=%s key=%s" % (rot, s, k))

    def test_rotation_point_maps(self):
        self.assertEqual(C.canonical_point_to_rendered(0, 0, PAGE, 0), (0, 0))
        self.assertEqual(C.canonical_point_to_rendered(0, 0, PAGE, 90), (792.0, 0))
        self.assertEqual(C.canonical_point_to_rendered(0, 0, PAGE, 180), (612.0, 792.0))
        self.assertEqual(C.canonical_point_to_rendered(0, 0, PAGE, 270), (0, 612.0))

    def test_rendered_size_swaps_on_quarter_turns(self):
        self.assertEqual(C.rendered_page_size(PAGE, 0), (612.0, 792.0))
        self.assertEqual(C.rendered_page_size(PAGE, 90), (792.0, 612.0))
        self.assertEqual(C.rendered_page_size(PAGE, 270), (792.0, 612.0))

    def test_bounds_and_zero_area(self):
        self.assertTrue(C.is_within_page({"x": 100, "y": 100, "width": 50, "height": 20}, PAGE))
        self.assertFalse(C.is_within_page({"x": 10, "y": 10, "width": 0, "height": 5}, PAGE))
        self.assertFalse(C.is_within_page({"x": 600, "y": 10, "width": 100, "height": 10}, PAGE))
        self.assertFalse(C.is_within_page({"x": -5, "y": 10, "width": 20, "height": 10}, PAGE))

    def test_rotation_normalization_fail_closed(self):
        self.assertEqual(C.normalize_rotation(45), 0)
        self.assertEqual(C.normalize_rotation(450), 90)
        self.assertEqual(C.normalize_rotation(None), 0)
        self.assertEqual(C.normalize_rotation("junk"), 0)

    def test_scale_zero_raises(self):
        with self.assertRaises(ValueError):
            C.viewport_rect_to_canonical({"x": 1, "y": 1, "width": 1, "height": 1}, PAGE, 0, 0)

    def test_determinism_rounding(self):
        r = C.viewport_rect_to_canonical({"x": 33.333, "y": 10, "width": 40, "height": 20},
                                         PAGE, 1.5, 0)
        r2 = C.viewport_rect_to_canonical({"x": 33.333, "y": 10, "width": 40, "height": 20},
                                          PAGE, 1.5, 0)
        self.assertEqual(r, r2)


if __name__ == "__main__":
    unittest.main()
