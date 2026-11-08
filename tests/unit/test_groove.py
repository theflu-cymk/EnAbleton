"""Unit tests for the ported groove helpers; pure math, no Live and no user media."""

import unittest

from enableton import groove


class GridOffsetTests(unittest.TestCase):
    def test_report_matches_the_delay(self):
        report = groove.groove_offset_report([0.0, 1.0, 2.0], [0.02, 1.02, 2.02], bpm=120)
        self.assertAlmostEqual(report["drum_grid_offset_ms"], 10.0, places=1)
        self.assertAlmostEqual(report["recommended_shift_beats"], 0.02, places=3)
        self.assertEqual(report["vocal_onsets_used"], 3)
        self.assertEqual(report["drum_hits_used"], 3)

    def test_off_grid_events_are_ignored(self):
        report = groove.groove_offset_report([0.0, 0.5], [1.0], bpm=120, tolerance_beats=0.25)
        self.assertEqual(report["vocal_onsets_used"], 1)
        self.assertEqual(report["drum_hits_used"], 1)

    def test_rejects_bad_bounds(self):
        with self.assertRaises(ValueError):
            groove.groove_offset_report([], [1.0])
        with self.assertRaises(ValueError):
            groove.groove_offset_report([0.0], [1.0], bpm=0)
        with self.assertRaises(ValueError):
            groove.groove_offset_report([0.0], [1.0], grid_beats=0.0)


class AlignmentTests(unittest.TestCase):
    def test_offsets_and_statistics(self):
        source = [{"pitch": 38, "start_time": 0.1}, {"pitch": 38, "start_time": 1.1}]
        target = [{"pitch": 38, "start_time": 0.0}, {"pitch": 38, "start_time": 1.0}]
        result = groove.groove_alignment(source, target, bpm=120)
        self.assertEqual([row["offset_beats"] for row in result["alignments"]], [0.1, 0.1])
        self.assertAlmostEqual(result["statistics"]["mean_offset_beats"], 0.1, places=4)
        self.assertAlmostEqual(result["statistics"]["std_offset_beats"], 0.0, places=4)

    def test_pitch_mismatch_falls_back_to_all_events(self):
        result = groove.groove_alignment(
            [{"pitch": 60, "start_time": 0.0}], [{"pitch": 38, "start_time": 0.5}], bpm=120
        )
        self.assertEqual(result["alignments"][0]["target_beat"], 0.5)

    def test_rejects_bad_pitch(self):
        with self.assertRaises(ValueError):
            groove.groove_alignment([{"pitch": 128, "start_time": 0.0}], [{"pitch": 38}], bpm=120)


class MarkerPlanTests(unittest.TestCase):
    def setUp(self):
        self.source = [{"pitch": 38, "start_time": t} for t in (0.1, 0.6, 1.1, 2.1)]
        self.target = [{"pitch": 38, "start_time": t} for t in (0.0, 0.5, 1.0, 2.0)]

    def test_minimum_offset_filters(self):
        self.assertEqual(
            groove.groove_marker_plan(self.source, self.target, min_offset_ms=25)["count"], 4
        )
        self.assertEqual(
            groove.groove_marker_plan(self.source, self.target, min_offset_ms=120)["count"], 0
        )

    def test_spacing_and_density(self):
        spaced = groove.groove_marker_plan(
            self.source, self.target, min_offset_ms=10, min_spacing_beats=1.0
        )
        self.assertEqual(spaced["count"], 3)
        per_bar = groove.groove_marker_plan(
            self.source, self.target, min_offset_ms=10, markers_per_bar=1.0
        )
        self.assertEqual(per_bar["count"], 1)

    def test_marker_cap(self):
        plan = groove.groove_marker_plan(self.source, self.target, min_offset_ms=0, max_markers=2)
        self.assertEqual(plan["count"], 2)
        self.assertEqual(plan["candidates_before_spacing"], 2)

    def test_target_quantization(self):
        target = [{"pitch": 38, "start_time": 0.4}]
        source = [{"pitch": 38, "start_time": 0.0}]
        plan = groove.groove_marker_plan(source, target, min_offset_ms=0, quantize_targets_to=0.5)
        self.assertEqual(plan["markers"][0]["target_beat"], 0.5)

    def test_pitch_filter(self):
        source = [
            {"pitch": 38, "start_time": 0.0},
            {"pitch": 60, "start_time": 1.0},
        ]
        target = [
            {"pitch": 38, "start_time": 0.1},
            {"pitch": 60, "start_time": 1.1},
        ]
        plan = groove.groove_marker_plan(source, target, min_offset_ms=0, pitch_filter=[60])
        self.assertEqual([row["pitch"] for row in plan["markers"]], [60])

    def test_rejects_bad_limits(self):
        with self.assertRaises(ValueError):
            groove.groove_marker_plan(self.source, self.target, max_markers=1000)
        with self.assertRaises(ValueError):
            groove.groove_marker_plan(self.source, self.target, min_offset_ms=-1)


class OnsetToNoteTests(unittest.TestCase):
    def test_converts_seconds_to_beats(self):
        grid = groove.onsets_to_note_grid(
            [{"time": 0.0, "strength": 1.0}, {"time": 0.5, "strength": 0.0}], bpm=120
        )
        self.assertEqual(grid["notes"][0]["start_time"], 0.0)
        self.assertEqual(grid["notes"][1]["start_time"], 1.0)
        self.assertEqual(grid["notes"][0]["velocity"], 127)
        self.assertEqual(grid["notes"][1]["velocity"], 30)

    def test_strength_filter_and_empty(self):
        grid = groove.onsets_to_note_grid(
            [{"time": 0.0, "strength": 0.9}, {"time": 1.0, "strength": 0.1}],
            bpm=120,
            min_strength=0.5,
        )
        self.assertEqual(grid["count"], 1)
        with self.assertRaises(ValueError):
            groove.onsets_to_note_grid([{"time": 0.0, "strength": 0.1}], bpm=120, min_strength=0.5)


class QuantizeTests(unittest.TestCase):
    def test_snaps_near_and_keeps_far(self):
        source = [{"pitch": 38, "start_time": 0.1}, {"pitch": 38, "start_time": 5.0}]
        target = [{"pitch": 38, "start_time": 0.0}, {"pitch": 38, "start_time": 1.0}]
        result = groove.quantize_notes_to_groove(source, target, max_snap_beats=0.5)
        self.assertEqual(result["notes"][0]["start_time"], 0.0)
        self.assertEqual(result["notes"][1]["start_time"], 5.0)
        self.assertEqual(result["snapped"], 1)


if __name__ == "__main__":
    unittest.main()
