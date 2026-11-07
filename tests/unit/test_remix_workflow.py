import contextlib
from copy import deepcopy
import io
import json
import math
from pathlib import Path
import tempfile
import unittest

from enableton.cli import main
from enableton.remix_workflow import (
    guide_halftime_remix,
    plan_halftime_remix,
    pulse_gain_at,
    refine_halftime_remix,
    remix_catalog,
)


def config():
    return dict(
        style="rock_dubstep",
        tempo=140,
        drop_bar=26,
        drop_bars=4,
        source_section_start_beat=96,
        source_roles={"riff": "Selected guitar MIDI", "vocal": "Isolated singer"},
        source_notes=[
            dict(pitch=37, start_time=95.5, duration=1, velocity=85),
            dict(pitch=49, start_time=96, duration=0.5, velocity=80),
            dict(pitch=40, start_time=100.25, duration=1, velocity=80),
            dict(pitch=42, start_time=104, duration=1, velocity=80),
            dict(pitch=24, start_time=108, duration=2, velocity=80, mute=True),
        ],
    )


class RemixTests(unittest.TestCase):
    def test_offset_root_heuristics_and_exact_durations(self):
        plan = plan_halftime_remix(config())
        self.assertEqual(plan["grid"]["drop_start_beat"], 100)
        self.assertEqual(plan["grid"]["drop_end_beat"], 116)
        self.assertEqual([n["pitch"] for n in plan["midi"]["sub"]], [25, 28, 30, 30])
        self.assertTrue(all(n["duration"] == 4 for n in plan["midi"]["sub"]))
        self.assertEqual(
            [x["reason"] for x in plan["root_decisions"]],
            [
                "lowest_sounding_at_barline",
                "first_incoming_note_in_bar",
                "lowest_sounding_at_barline",
                "carry_previous_note_across_silence",
            ],
        )
        first = plan["midi"]["riff"][0]
        self.assertEqual((first["pitch"], first["start_time"], first["duration"]), (37, 0, 0.5))
        self.assertNotIn(24, [n["pitch"] for n in plan["midi"]["riff"]])

    def test_no_invented_roots_before_first_source_event(self):
        c = config()
        c["source_notes"] = c["source_notes"][2:3]
        plan = plan_halftime_remix(c)
        self.assertEqual(plan["missing_root_bars"], [26])
        self.assertEqual(plan["midi"]["sub"][0]["start_time"], 4)
        self.assertEqual(plan["status"], "needs_source_notes")

    def test_explicit_octave_fit_preserves_pitch_class(self):
        c = config()
        c["sub_range"] = [36, 47]
        plan = plan_halftime_remix(c)
        self.assertTrue(all(x["octave_adjusted_to_register"] for x in plan["root_decisions"]))
        for x in plan["root_decisions"]:
            self.assertEqual(x["sub_pitch"] % 12, x["source_pitch"] % 12)

    def test_exact_all_notes_voice_and_boundary_trim(self):
        c = config()
        c["riff_voice"] = "all_notes"
        c["source_notes"].append(dict(pitch=59, start_time=111.5, duration=2))
        p = plan_halftime_remix(c)
        self.assertIn(49, [n["pitch"] for n in p["midi"]["riff"]])
        last = p["midi"]["riff"][-1]
        self.assertEqual(last["duration"], 0.5)

    def test_profiles_anchor_snare_and_bound_all_generated_events(self):
        for style in remix_catalog()["profiles"]:
            with self.subTest(style=style):
                c = config()
                c["style"] = style
                p = plan_halftime_remix(c)
                main = [
                    n["start_time"]
                    for n in p["midi"]["drums"]
                    if n["pitch"] == 38 and n["velocity"] == 118
                ]
                self.assertEqual(main, [2, 6, 10, 14])
                for role in p["midi"].values():
                    for n in role:
                        self.assertLessEqual(n["start_time"] + n["duration"], 16 + 1e-8)
                for n in p["movement"]["pulses"]:
                    self.assertLessEqual(n["time"] + n["duration"], 16 + 1e-8)
                self.assertFalse(p["live_changes"])

    def test_gain_is_continuous_at_attack_hold_and_release_edges(self):
        pulses = [dict(time=1, duration=0.28)]
        attack = 8 * 140 / 60000
        release = 85 * 140 / 60000
        for edge in [1, 1 + attack, 1 + 0.28, 1 + 0.28 + release]:
            left = pulse_gain_at(edge - 1e-7, pulses)
            right = pulse_gain_at(edge + 1e-7, pulses)
            self.assertLess(abs(left - right), 1e-5)
        self.assertAlmostEqual(pulse_gain_at(0, pulses), 0.13)
        self.assertAlmostEqual(pulse_gain_at(1 + attack, pulses), 1)
        self.assertAlmostEqual(pulse_gain_at(4, pulses), 0.13)

    def test_fingerprints_determinism_and_nonmutation(self):
        c = config()
        before = deepcopy(c)
        a = plan_halftime_remix(c)
        b = plan_halftime_remix(c)
        self.assertEqual(a, b)
        self.assertEqual(c, before)
        c["source_notes"][0]["pitch"] += 1
        self.assertNotEqual(a["fingerprint"], plan_halftime_remix(c)["fingerprint"])

    def test_guided_decisions_do_not_misrepresent_defaults_as_answers(self):
        g = guide_halftime_remix()
        self.assertEqual(len(g["questions"]), 3)
        self.assertEqual(g["answers"], {})
        self.assertTrue(g["defaults_are_not_answers"])
        c = config()
        c.update(source_mode="hybrid", vocal_mode="continuous")
        g = guide_halftime_remix(c)
        self.assertEqual(g["status"], "review_and_build")
        self.assertFalse(g["live_changes"])

    def test_feedback_changes_movement_without_changing_root_pitches(self):
        c = config()
        before = deepcopy(c)
        old = plan_halftime_remix(c)
        revised = refine_halftime_remix(c, ["too_busy", "vocal_masked", "kick_sub_clash"])
        self.assertEqual(c, before)
        self.assertLess(len(revised["plan"]["movement"]["pulses"]), len(old["movement"]["pulses"]))
        self.assertEqual(revised["plan"]["midi"]["sub"], old["midi"]["sub"])
        self.assertEqual(len(revised["config"]["feedback_history"]), 1)
        self.assertEqual(revised["plan"]["movement"]["settings"]["vocal_duck_db"], 3)
        self.assertEqual(revised["plan"]["movement"]["settings"]["kick_duck_db"], 6)

    def test_each_refinement_is_valid_and_repeatable(self):
        for feedback in ["too_guttural", "weak_transition", "clicks", "more_riddim", "smoother"]:
            with self.subTest(feedback=feedback):
                a = refine_halftime_remix(config(), [feedback])
                self.assertEqual(a, refine_halftime_remix(config(), [feedback]))
                self.assertFalse(a["live_changes"])

    def test_invalid_inputs_fail_early(self):
        cases = [
            dict(tempo=True),
            dict(tempo=math.nan),
            dict(drop_bars=1.5),
            dict(meter=[2, 2]),
            dict(drop_bar=1),
            dict(style="missing"),
            dict(sub_octave_shift=-1),
            dict(sub_range=[40, 30]),
            dict(overrides={"native_fader_hz": 0.4}),
            dict(overrides={"pulse_patterns": [[1, 0]]}),
            dict(source_notes=[dict(pitch=True, start_time=0, duration=1)]),
            dict(source_roles={"riff": 4}),
            dict(schema_version=True),
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                plan_halftime_remix(dict(config(), **changes))
        for f in [["unknown"], ["clicks", "clicks"], []]:
            with self.assertRaises(ValueError):
                refine_halftime_remix(config(), f)

    def test_cli_plan_guide_refine_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            out = Path(tmp) / "plan.json"
            path.write_text(json.dumps(config()))
            with contextlib.redirect_stdout(io.StringIO()) as stream:
                self.assertEqual(main(["remix-plan", str(path), "--output", str(out)]), 0)
            self.assertEqual(json.loads(stream.getvalue())["status"], "planned")
            previous = out.read_text()
            with (
                contextlib.redirect_stderr(io.StringIO()),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(["remix-plan", str(path), "--output", str(out)]), 2)
            self.assertEqual(out.read_text(), previous)
            for args in [["remix-guide"], ["remix-refine", str(path), "--feedback", "smoother"]]:
                with contextlib.redirect_stdout(io.StringIO()) as stream:
                    self.assertEqual(main(args), 0)
                json.loads(stream.getvalue())
