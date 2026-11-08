"""Arrangement clip geometry used by the guarded move and split commands."""

import unittest

from enableton import clip_geometry


class OverlapTests(unittest.TestCase):
    def test_touching_edges_do_not_overlap(self):
        self.assertFalse(clip_geometry.overlaps(0, 4, 4, 8))
        self.assertFalse(clip_geometry.overlaps(4, 8, 0, 4))

    def test_shared_interior_overlaps(self):
        self.assertTrue(clip_geometry.overlaps(0, 8, 4, 12))
        self.assertTrue(clip_geometry.overlaps(4, 12, 0, 8))

    def test_inverted_span_is_rejected(self):
        with self.assertRaises(ValueError):
            clip_geometry.overlaps(8, 4, 0, 4)


class MoveTests(unittest.TestCase):
    def test_move_keeps_length(self):
        start, end, length = clip_geometry.plan_move(100.0, 104.5, 108.0)
        self.assertEqual((start, end, length), (108.0, 112.5, 4.5))

    def test_negative_destination_rejected(self):
        with self.assertRaises(ValueError):
            clip_geometry.plan_move(0, 4, -1)

    def test_zero_length_rejected(self):
        with self.assertRaises(ValueError):
            clip_geometry.plan_move(4, 4, 0)

    def test_conflicts_report_which_clip_would_be_overwritten(self):
        spans = [(0, 4), (4, 8), (8, 12)]
        self.assertEqual(clip_geometry.conflicts(4, 8, spans, ignore_index=0), [1])
        self.assertEqual(clip_geometry.conflicts(12, 16, spans, ignore_index=0), [])


class SplitTests(unittest.TestCase):
    def test_split_returns_abutting_spans(self):
        left, right = clip_geometry.plan_split(0, 16, 6)
        self.assertEqual(left, (0, 6))
        self.assertEqual(right, (6, 16))

    def test_split_outside_the_clip_rejected(self):
        for point in (0, 16, 20, -1):
            with self.assertRaises(ValueError):
                clip_geometry.plan_split(0, 16, point)


if __name__ == "__main__":
    unittest.main()
