"""Unit tests for local energy analysis; synthesized WAV files only."""

import math
from pathlib import Path
import statistics
import struct
import tempfile
import unittest
import wave

from enableton import energy


def write_split_tone(path, seconds=2.0, rate=16000):
    """Low sine for the first half, high sine for the second half."""
    half = int(rate * seconds / 2)
    frames = bytearray()
    for index in range(half):
        frames += struct.pack("<h", int(12000 * math.sin(2 * math.pi * 40 * index / rate)))
    for index in range(half):
        frames += struct.pack("<h", int(12000 * math.sin(2 * math.pi * 5000 * index / rate)))
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))


class SeriesTests(unittest.TestCase):
    def test_bands_separate_low_and_high_halves(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tone.wav"
            write_split_tone(path)
            series = energy.energy_series(str(path), bpm=120, max_seconds=2)
        self.assertEqual(len(series["rms"]), series["count"])
        self.assertEqual(len(series["times"]), series["count"])
        self.assertEqual(series["count"], 16)
        half = series["count"] // 2
        low_first = statistics.mean(series["bands"]["sub"][:half])
        low_second = statistics.mean(series["bands"]["sub"][half:])
        high_first = statistics.mean(series["bands"]["high"][:half])
        high_second = statistics.mean(series["bands"]["high"][half:])
        self.assertGreater(low_first, low_second)
        self.assertGreater(high_second, high_first)
        self.assertIn("one-pole", series["method"])

    def test_rejects_unsupported_format_and_bad_bpm(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tone.mp3"
            path.write_bytes(b"x")
            with self.assertRaises(ValueError):
                energy.energy_series(str(path), bpm=120)
            wav_path = Path(folder) / "tone.wav"
            write_split_tone(wav_path)
            with self.assertRaises(ValueError):
                energy.energy_series(str(wav_path), bpm=5)
            with self.assertRaises(ValueError):
                energy.energy_series("relative.wav", bpm=120)


class ClashTests(unittest.TestCase):
    def test_same_file_clashes_everywhere_and_ranks(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "tone.wav"
            write_split_tone(path)
            report = energy.band_clash(str(path), str(path), bpm=120, max_seconds=2, top=3)
        self.assertEqual(len(report["bands"]), 5)
        self.assertEqual(len(report["suggestions"]), 3)
        scores = [row["clash_score"] for row in report["bands"]]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for row in report["bands"]:
            self.assertGreater(row["clash_score"], 0)
            self.assertTrue(1 <= row["eq_band"] <= 8)
        self.assertTrue(report["alignment"]["same_window"])


class SegmentTests(unittest.TestCase):
    def test_splits_on_level_change(self):
        series = {
            "bpm": 120.0,
            "times": [index * 0.125 for index in range(32)],
            "rms": [0.2] * 16 + [0.9] * 16,
        }
        plan = energy.segment_plan(series, min_segment_sixteenths=4, threshold=0.1)
        self.assertEqual(plan["count"], 2)
        self.assertEqual(plan["segments"][0]["energy_class"], "low")
        self.assertEqual(plan["segments"][1]["energy_class"], "high")
        self.assertEqual(plan["segments"][1]["start_beat"], 4.0)

    def test_rejects_short_and_invalid(self):
        with self.assertRaises(ValueError):
            energy.segment_plan({"bpm": 120.0, "times": [0.0], "rms": [0.1]})
        series = {"bpm": 120.0, "times": [index * 0.125 for index in range(8)], "rms": [0.2] * 8}
        with self.assertRaises(ValueError):
            energy.segment_plan(series, min_segment_sixteenths=1)


if __name__ == "__main__":
    unittest.main()
