"""Synthetic PCM evidence, CLI/worker behavior, and fake-Live read-only targeting."""

import contextlib
import hashlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

from enableton.audio_scan import scan_pcm
from enableton.audio_scan_tools import scan_audio_file, scan_clip
from enableton.cli import main


class AudioScanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "source.wav"
        self.sr = 8000

    def write(self, values, channels=1, width=2):
        with wave.open(str(self.path), "wb") as audio:
            audio.setparams((channels, width, self.sr, 0, "NONE", "not compressed"))
            scale = 2 ** (width * 8 - 1)
            if width == 1:
                raw = bytes(round(v * scale) + 128 for v in values)
            else:
                raw = b"".join(
                    round(v * scale).to_bytes(width, "little", signed=True) for v in values
                )
            audio.writeframes(raw)

    def sine(self, seconds=1):
        return [
            0.2 * math.sin(2 * math.pi * 100 * i / self.sr) for i in range(round(self.sr * seconds))
        ]

    def test_clean_sine_metrics_and_no_mutation(self):
        self.write(self.sine())
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        report = scan_audio_file(str(self.path))
        self.assertEqual(report["finding_counts"], {})
        self.assertFalse(report["coverage"]["partial"])
        self.assertAlmostEqual(report["channels"][0]["rms_dbfs"], -16.99, places=2)
        self.assertEqual(digest, hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_click_gap_rail_dc_and_offset_timestamps(self):
        samples = self.sine(2)
        samples[10000] = 0.99
        samples[12000:12400] = [0] * 400
        samples[14000:14008] = [32767 / 32768] * 8
        self.write(samples)
        report = scan_pcm(str(self.path), 1, 1)
        self.assertTrue(report["coverage"]["partial"])
        self.assertIn("discontinuity", report["finding_counts"])
        self.assertIn("silence_gap", report["finding_counts"])
        self.assertIn("near_full_scale", report["finding_counts"])
        self.assertEqual(report["channels"][0]["rail_samples"], 8)
        self.assertTrue(all(f["start_seconds"] >= 1 for f in report["findings"]))
        self.assertTrue(all(not f["autofixable"] for f in report["findings"]))
        self.write([0.02] * 800)
        self.assertIn("dc_offset", scan_pcm(str(self.path))["finding_counts"])

    def test_stereo_opposite_polarity_not_silence(self):
        samples = self.sine()
        self.write([v for x in samples for v in (x, -x)], channels=2)
        report = scan_pcm(str(self.path))
        self.assertEqual(report["finding_counts"], {})
        self.assertEqual(len(report["channels"]), 2)

    def test_widths_silence_and_unsupported(self):
        for width in (1, 2, 3, 4):
            self.write([0] * 800, width=width)
            report = scan_pcm(str(self.path))
            self.assertIsNone(report["channels"][0]["rms_dbfs"])
            self.assertEqual(report["finding_counts"], {})
        for kwargs in (
            {"max_seconds": 0},
            {"max_seconds": 121},
            {"start_seconds": -1},
            {"max_seconds": float("nan")},
            {"start_seconds": 10},
        ):
            with self.assertRaises(ValueError):
                scan_pcm(str(self.path), **kwargs)
        with self.assertRaises(ValueError):
            scan_audio_file(str(self.path.with_suffix(".mp3")))

    def test_truncated_file_rejected(self):
        self.write(self.sine())
        self.path.write_bytes(self.path.read_bytes()[:-200])
        with self.assertRaisesRegex(ValueError, "Truncated"):
            scan_pcm(str(self.path))

    def test_cli_report_exclusive_and_error(self):
        self.write(self.sine())
        dest = Path(self.temp.name) / "report.json"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["scan-audio", str(self.path), "--report", str(dest)]), 0)
        self.assertEqual(json.loads(dest.read_text())["finding_counts"], {})
        original = dest.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["scan-audio", str(self.path), "--report", str(dest)]), 2)
        self.assertEqual(original, dest.read_bytes())

    def test_clip_window_freshness_and_no_mutations(self):
        self.write(self.sine())
        timing = dict(
            track_name="Bass",
            clip_name="Stem",
            file_path=str(self.path),
            warping=False,
            start_marker=0.25,
            end_marker=0.5,
        )
        calls = []

        def dispatch(command, target):
            calls.append(command)
            return timing.copy()

        report = scan_clip(dispatch, {"track_index": 2, "clip_index": 0})
        self.assertEqual(calls, ["get_audio_clip_timing"] * 2)
        self.assertEqual(report["coverage"]["start_seconds"], 0.25)
        with (
            patch("enableton.audio_scan_tools.scan_audio_file", return_value={}),
            patch("enableton.audio_scan_tools.timing_fingerprint", side_effect=["a", "b"]),
        ):
            with self.assertRaisesRegex(ValueError, "Clip changed"):
                scan_clip(dispatch, {})

    def test_float_wav_rejected_and_example_counts_preserved(self):
        self.write(self.sine())
        raw = bytearray(self.path.read_bytes())
        raw[20:22] = (3).to_bytes(2, "little")
        self.path.write_bytes(raw)
        with self.assertRaises(ValueError):
            scan_audio_file(str(self.path))
        self.write([0.8 if i % 160 == 0 else 0 for i in range(8000)])
        report = scan_pcm(str(self.path))
        self.assertGreater(report["finding_counts"]["discontinuity"], 24)
        self.assertEqual(sum(f["code"] == "discontinuity" for f in report["findings"]), 24)

    def test_invalid_clip_window_does_not_read_live(self):
        def dispatch(*args):
            self.fail("Invalid arguments should not access Live")

        for duration in (0, 121, float("inf")):
            with self.assertRaises(ValueError):
                scan_clip(dispatch, {}, duration)

    def test_worker_timeout(self):
        import subprocess

        with patch(
            "enableton.audio_scan_tools.subprocess.run",
            side_effect=subprocess.TimeoutExpired("worker", 25),
        ):
            with self.assertRaisesRegex(RuntimeError, "25 seconds"):
                scan_audio_file(str(self.path))


if __name__ == "__main__":
    unittest.main()
