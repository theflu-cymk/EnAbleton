import array
import copy
import importlib
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace as NS
import unittest
from unittest.mock import patch
import wave
from enableton.warp_analysis import (
    analyze_file,
    audit_timing,
    beat_to_source,
    compare_reference,
    plan_moves,
    source_to_beat,
    tempo_candidates,
    timing_fingerprint,
    validate_markers,
)
from test_access import Access, Sound
from enableton import warp_tools


def timing(path="source.wav"):
    return {
        "track_name": "Drums",
        "clip_name": "Loop",
        "file_path": str(path),
        "warping": True,
        "warp_mode": 0,
        "looping": True,
        "loop_start": 0.0,
        "loop_end": 8.0,
        "start_marker": 0.0,
        "end_marker": 8.0,
        "pitch_coarse": 0,
        "pitch_fine": 0,
        "sample_rate": 48000,
        "sample_length": 192000,
        "warp_markers": [
            {"beat_time": b, "sample_time": b * 0.5} for b in (0.0, 4.0, 8.0, 8.03125)
        ],
        "available_warp_modes": [0, 4, 6],
        "marker_api": {"move_warp_marker": True},
        "clip_identity": "stable",
    }


def pulse_file(path, tempo=120, seconds=8, silent=False, channels=1):
    sr = 8000
    values = array.array("h", [0]) * int(sr * seconds) * channels
    if not silent:
        for b in range(int(seconds * tempo / 60)):
            pos = round(b * sr * 60 / tempo)
            for k in range(80):
                if pos + k >= sr * seconds:
                    break
                for ch in range(channels):
                    values[(pos + k) * channels + ch] = int(24000 * (1 - k / 80)) * (
                        -1 if ch == 1 else 1
                    )
    with wave.open(str(path), "wb") as f:
        f.setnchannels(channels)
        f.setsampwidth(2)
        f.setframerate(sr)
        f.writeframes(values.tobytes())


class WarpAnalysisTests(unittest.TestCase):
    def test_coordinates_and_hidden_terminal(self):
        t = timing()
        self.assertAlmostEqual(source_to_beat(1.25, t["warp_markers"]), 2.5)
        self.assertAlmostEqual(beat_to_source(2.5, t["warp_markers"]), 1.25)
        report = audit_timing(t)
        self.assertEqual(report["issues"], [])
        self.assertTrue(report["segments"][-1]["hidden_terminal_segment"])

    def test_invalid_markers(self):
        for rows in (
            [],
            [{"beat_time": 0, "sample_time": 0}] * 2,
            [{"beat_time": 0, "sample_time": 0}, {"beat_time": 4, "sample_time": -1}],
            [{"beat_time": 0, "sample_time": 0}, {"beat_time": float("nan"), "sample_time": 1}],
        ):
            with self.assertRaises(ValueError):
                validate_markers(rows)

    def test_unwarped_not_falsely_flagged(self):
        report = audit_timing(dict(timing(), warping=False))
        self.assertFalse(report["musical_alignment_verified"])
        self.assertTrue(report["review"])
        self.assertEqual(report["issues"], [])

    def test_triplet_preservation(self):
        t = timing()
        audio = {"onsets": [{"time": i / 6, "strength": 1} for i in range(12)], "tempo": {}}
        trip = audit_timing(t, audio, grid_beats=0.5, groove="triplet", project_bpm=120)
        straight = audit_timing(t, audio, grid_beats=0.5, groove="straight", project_bpm=120)
        self.assertEqual(trip["transient_alignment"]["outside_tolerance"], 0)
        self.assertGreater(straight["transient_alignment"]["outside_tolerance"], 0)

    def test_reference_offset(self):
        result = compare_reference([0.125, 1.125, 2.125], [0, 1, 2])
        self.assertAlmostEqual(result["suggested_offset_beats"], -0.125)

    def test_marker_plan_guards(self):
        t = timing()
        plan = plan_moves(t, [{"beat_time": 4.0, "new_beat_time": 4.125}])
        self.assertEqual(plan["after_markers"][1]["sample_time"], 2.0)
        self.assertEqual(t["warp_markers"][1]["beat_time"], 4.0)
        for moves in (
            [{"beat_time": 0, "new_beat_time": 0.1}],
            [{"beat_time": 4, "new_beat_time": 5}],
            [{"beat_time": 7, "new_beat_time": 7.1}],
        ):
            with self.assertRaises(ValueError):
                plan_moves(t, moves)

    def test_stale_fingerprint(self):
        t = timing()
        before = timing_fingerprint(t)
        t["warp_markers"][1]["beat_time"] += 0.01
        self.assertNotEqual(before, timing_fingerprint(t))

    def test_audio_tempo_and_antiphase_stereo(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pulse.wav"
            pulse_file(path, 140, 12, channels=2)
            report = analyze_file(path, max_seconds=12, tempo_hint=140)
            self.assertLess(abs(report["tempo"]["bpm"] - 140), 2)
            self.assertGreater(len(report["onsets"]), 20)
            self.assertTrue(report["downbeat_candidates"])

    def test_silence_and_truncated_window(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "silent.wav"
            pulse_file(path, seconds=5, silent=True)
            report = analyze_file(path, max_seconds=2)
            self.assertIsNone(report["tempo"]["bpm"])
            self.assertTrue(report["audio"]["partial"])

    def test_half_time_hint_is_explicitly_ambiguous(self):
        onsets = [{"time": i * 0.8, "strength": 1.0} for i in range(16)]
        report = tempo_candidates(onsets, hint=150)
        self.assertTrue(report["half_double_ambiguous"])
        self.assertEqual(report["tempo_hint_relation"], "hint_is_double_time")

    def test_bad_audio_inputs(self):
        for limit in (0, 121, float("nan")):
            with self.assertRaises(ValueError):
                analyze_file("/missing.wav", max_seconds=limit)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "fake.mp3"
            path.write_bytes(b"not audio")
            with self.assertRaisesRegex(ValueError, "PCM WAV"):
                analyze_file(path)


Warp = importlib.import_module("access_test_pkg.warp_support").WarpSupportMixin


class Bridge(Warp, Access, Sound):
    pass


class Clip:
    def move_warp_marker(self, beat, distance):
        next(m for m in self.warp_markers if m.beat_time == beat).beat_time += distance


class WarpBridgeTests(unittest.TestCase):
    def setUp(self):
        self.original = Clip()
        for k, v in timing().items():
            if k == "warp_markers":
                v = [NS(**m) for m in v]
            setattr(self.original, k, v)
        self.original.name = "Loop"
        self.original.is_audio_clip = True
        self.original.is_recording = False
        self.original.start_time = 0.0
        self.original.end_time = 8.0
        self.original.length = 8.0
        self.track = NS(name="Drums", arrangement_clips=[self.original], is_frozen=False)

        def duplicate(clip, destination):
            clone = copy.deepcopy(clip)
            clone.start_time = destination
            clone.end_time = destination + 8
            self.track.arrangement_clips.append(clone)

        self.track.duplicate_clip_to_arrangement = duplicate
        self.track.delete_clip = lambda clip: self.track.arrangement_clips.remove(clip)
        self.bridge = Bridge()
        self.undo = []
        self.bridge._song = NS(
            tracks=[self.track],
            begin_undo_step=lambda: self.undo.append("begin"),
            end_undo_step=lambda: self.undo.append("end"),
        )
        self.target = dict(
            track_index=0,
            clip_view="arrangement",
            clip_index=0,
            expected_track_name="Drums",
            expected_clip_name="Loop",
            expected_start_time=0.0,
        )
        self.before = self.bridge._get_audio_clip_timing(self.target)
        self.args = dict(
            target=self.target,
            expected_fingerprint=timing_fingerprint(self.before),
            moves=[{"beat_time": 4.0, "new_beat_time": 4.125}],
            destination_time=16.0,
        )

    def test_duplicate_repair_preserves_original(self):
        result = self.bridge._repair_warp_duplicate(self.args)
        self.assertTrue(result["verified"])
        self.assertTrue(result["original_preserved"])
        self.assertEqual(self.original.warp_markers[1].beat_time, 4.0)
        self.assertEqual(self.track.arrangement_clips[1].warp_markers[1].beat_time, 4.125)
        self.assertEqual(self.undo, ["begin", "end"])

    def test_overlap_rejected_before_creation(self):
        with self.assertRaisesRegex(ValueError, "overlaps"):
            self.bridge._repair_warp_duplicate(dict(self.args, destination_time=4.0))
        self.assertEqual(len(self.track.arrangement_clips), 1)

    def test_stale_rejected(self):
        self.original.warp_markers[1].beat_time = 4.01
        with self.assertRaisesRegex(ValueError, "Stale"):
            self.bridge._repair_warp_duplicate(self.args)
        self.assertEqual(len(self.track.arrangement_clips), 1)

    def test_failed_move_cleans_preview(self):
        with patch.object(Clip, "move_warp_marker", side_effect=RuntimeError("API failed")):
            with self.assertRaisesRegex(RuntimeError, "preview removed"):
                self.bridge._repair_warp_duplicate(self.args)
        self.assertEqual(len(self.track.arrangement_clips), 1)
        self.assertEqual(self.original.warp_markers[1].beat_time, 4.0)


class FakeMCP:
    def __init__(self):
        self.tools = {}

    def tool(self, **options):
        def register(fn):
            self.tools[fn.__name__] = fn
            return fn

        return register


class WarpWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file = self.root / "pulse.wav"
        pulse_file(self.file)
        self.t = timing(self.file)
        self.calls = []
        self.mcp = FakeMCP()

        def dispatch(command, args):
            self.calls.append(command)
            if command == "get_audio_clip_timing":
                return copy.deepcopy(self.t)
            if command == "get_arrangement_clips":
                return {"clips": []}
            if command == "repair_warp_duplicate":
                return {"verified": True, "original_preserved": True}
            if command == "get_session_info":
                return {"tempo": 120}
            raise AssertionError(command)

        warp_tools.register_warp(self.mcp, dispatch)
        self.target = dict(
            track_index=0, clip_index=0, expected_track_name="Drums", expected_clip_name="Loop"
        )
        warp_tools._previews.clear()

    def tearDown(self):
        self.temp.cleanup()

    def preview(self):
        return self.mcp.tools["preview_warp_repair"](
            self.target, [{"beat_time": 4, "new_beat_time": 4.125}], 16.0
        )

    def test_preview_then_apply_with_backup_and_single_use(self):
        token = self.preview()["preview_token"]
        self.assertNotIn("repair_warp_duplicate", self.calls)
        with patch.object(warp_tools.Path, "home", return_value=self.root):
            result = self.mcp.tools["apply_warp_repair"](token)
        self.assertTrue(Path(result["backup_path"]).is_file())
        with self.assertRaises(ValueError):
            self.mcp.tools["apply_warp_repair"](token)

    def test_file_change_invalidates_preview(self):
        token = self.preview()["preview_token"]
        self.file.write_bytes(self.file.read_bytes() + b"changed")
        with self.assertRaisesRegex(ValueError, "Source file changed"):
            self.mcp.tools["apply_warp_repair"](token)
        self.assertNotIn("repair_warp_duplicate", self.calls)

    def test_expired_preview(self):
        token = self.preview()["preview_token"]
        warp_tools._previews[token]["created"] = time.monotonic() - 601
        with self.assertRaisesRegex(ValueError, "Expired"):
            self.mcp.tools["apply_warp_repair"](token)

    def test_batch_partial_coverage(self):
        result = self.mcp.tools["batch_warp_audit"]([self.target], max_audio_files=0)
        self.assertFalse(result["results"][0]["audio_checked"])
        self.assertIn("budget", result["results"][0]["audio_error"])

    def test_worker_timeout(self):
        warp_tools._cache.clear()
        with patch.object(
            warp_tools.subprocess,
            "run",
            side_effect=__import__("subprocess").TimeoutExpired("worker", 25),
        ):
            with self.assertRaisesRegex(RuntimeError, "25 seconds"):
                warp_tools._analyze(self.file)


if __name__ == "__main__":
    unittest.main()
