from array import array
from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest

from enableton.remix_assets import render_assets, project
from enableton.remix_audio import (
    aligned_source,
    compare,
    decode_window,
    file_identity,
    gain_curve,
    loudness,
    measure,
    process_values,
    write_wave,
)
from enableton.remix_workflow import plan_halftime_remix


def sine(path, seconds=8, sr=8000, amplitude=0.4, antiphase=False):
    samples = array("h")
    for i in range(round(seconds * sr)):
        v = round(amplitude * 32767 * math.sin(2 * math.pi * 110 * i / sr))
        samples.extend([v, -v if antiphase else v])
    write_wave(path, samples, sr, 2)
    return samples


def short_plan(**overrides):
    c = dict(
        style="rock_dubstep",
        tempo=120,
        drop_bar=3,
        drop_bars=2,
        lead_in_bars=1,
        source_notes=[
            dict(pitch=37, start_time=0, duration=4),
            dict(pitch=40, start_time=4, duration=4),
        ],
        source_mode="hybrid",
        vocal_mode="none",
    )
    c.update(overrides)
    return plan_halftime_remix(c)


class AudioRenderTests(unittest.TestCase):
    def test_warp_alignment_preserves_pitch_and_exact_length(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "source.wav"
            sine(p)
            binding = dict(
                timing=dict(
                    file_path=str(p),
                    warping=True,
                    warp_markers=[
                        dict(beat_time=0, sample_time=0),
                        dict(beat_time=16, sample_time=8),
                    ],
                ),
                source_start=0,
            )
            out, sr, ch = aligned_source(binding, 140, 8)
            self.assertEqual(len(out) // ch, round(8 * 60 / 140 * sr))
            crossings = sum(out[i * 2] < 0 <= out[(i + 1) * 2] for i in range(len(out) // 2 - 1))
            self.assertAlmostEqual(crossings / (len(out) // ch / sr), 110, delta=2)
            self.assertEqual(out[0], 0)

    def test_normalized_warp_overlap_has_no_internal_gain_holes(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / "constant.wav"
            write_wave(path, array("h", [10000]) * 32000, 8000, 1)
            binding = dict(
                source_start=0,
                timing=dict(
                    file_path=str(path),
                    warping=True,
                    warp_markers=[
                        dict(beat_time=b, sample_time=s)
                        for b, s in [(0, 0), (2, 1), (4, 2.2), (6, 3)]
                    ],
                ),
            )
            out, sr, ch = aligned_source(binding, 120, 6)
            self.assertEqual(len(out), 24000)
            for seam in [8000, 16000]:
                self.assertGreater(min(out[seam - 100 : seam + 100]), 9800)
                self.assertLess(max(out[seam - 100 : seam + 100]), 10200)

    def test_vocal_windows_reduce_gain_without_changing_samples_outside(self):
        plan = short_plan(vocal_regions=[dict(start=2, end=3)])
        dry = short_plan()
        frames = 16000
        a = gain_curve(plan, 4000, frames, "riff")
        b = gain_curve(dry, 4000, frames, "riff")
        self.assertLess(a[5000], b[5000])
        self.assertEqual(a[500], b[500])

    def test_transition_gap_is_ramped_and_zero_at_end(self):
        p = short_plan(overrides=dict(transition_gap_beats=0.5))
        gain = gain_curve(p, 8000, 16000, "rock_context")
        self.assertEqual(gain[-1], 0)
        edge = 16000 - round(0.5 * 60 / 120 * 8000)
        self.assertLess(abs(gain[edge - 1] - gain[edge]), 0.01)

    def test_cached_vocal_is_reused_when_only_pulses_change(self):
        with tempfile.TemporaryDirectory() as t:
            root, _ = project(str(Path(t) / "project"), True)
            source = Path(t) / "source.wav"
            sine(source)
            binding = dict(
                timing=dict(file_path=str(source), warping=False),
                source_start=0,
                file=file_identity(source),
            )
            p = short_plan(vocal_mode="continuous", vocal_regions=[dict(start=1, end=2)])
            first = render_assets(root, p, dict(riff=binding, vocal=binding), False)
            c = deepcopy(p["config"])
            c["custom_pulses"] = [dict(time=0, duration=0.5)]
            second = render_assets(
                root, plan_halftime_remix(c), dict(riff=binding, vocal=binding), False
            )
            self.assertTrue(second["assets"]["vocal"]["cached"])
            self.assertEqual(first["assets"]["vocal"]["path"], second["assets"]["vocal"]["path"])
            self.assertNotEqual(first["assets"]["riff"]["path"], second["assets"]["riff"]["path"])

    def test_measurements_and_attenuation_only_ab_match(self):
        with tempfile.TemporaryDirectory() as t:
            a = Path(t) / "A.wav"
            b = Path(t) / "B.wav"
            sine(a, 4, amplitude=0.2)
            sine(b, 4, amplitude=0.4)
            before = file_identity(b)
            report = compare(a, b, Path(t) / "ab")
            self.assertLess(report["variant"]["gain_db"], -5.5)
            self.assertEqual(before, file_identity(b))
            ar = measure(report["reference"]["path"])
            br = measure(report["variant"]["path"])
            self.assertAlmostEqual(ar["rms_dbfs"], br["rms_dbfs"], delta=0.15)
            self.assertEqual(report["match_method"], "integrated LUFS")
            self.assertIsNotNone(ar["true_peak_dbtp"])

    def test_antiphase_low_end_and_silence_are_reported(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "phase.wav"
            sine(p, 2, antiphase=True)
            result = measure(p)
            self.assertLess(result["low_band"]["correlation"], -0.99)
            q = Path(t) / "silence.wav"
            write_wave(q, array("h", [0]) * 32000, 8000, 2)
            self.assertIsNone(measure(q)["integrated_lufs"])
            with self.assertRaises(ValueError):
                compare(q, p, Path(t) / "ab")

    def test_unknown_project_and_pitched_source_are_refused(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t)
            (p / "unrelated.txt").write_text("keep")
            with self.assertRaises(ValueError):
                project(t, True)
            with self.assertRaises(ValueError):
                aligned_source(dict(timing=dict(pitch_coarse=1), source_start=0), 120, 4)

    def test_root_overrides_and_phrase_events(self):
        p = short_plan(
            drop_bars=4,
            root_overrides={"4": 42},
            vocal_regions=[dict(start=0, end=2)],
            vocal_mode="chops",
        )
        self.assertEqual(p["midi"]["sub"][1]["pitch"], 30)
        self.assertEqual(p["root_decisions"][1]["reason"], "explicit_root_override")
        self.assertTrue(p["arrangement"]["fx"])
        self.assertTrue(p["arrangement"]["vocal_chops"])
        self.assertTrue(p["root_decisions"][0]["alternatives"])
        with self.assertRaises(ValueError):
            short_plan(root_overrides={"999": 40})


if __name__ == "__main__":
    unittest.main()
