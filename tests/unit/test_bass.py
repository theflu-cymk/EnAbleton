import copy
import math
import unittest
from enableton.bass_patterns import curve_points, phrase, inspect_sub_notes, SHAPES
from enableton.bass_recipes import RECIPES, get_recipe
from enableton.envelope_support import plan_steps
from enableton.bass_tools import register


class MusicalTests(unittest.TestCase):
    def test_all_shapes_are_bounded_and_writable(self):
        for shape in SHAPES:
            with self.subTest(shape=shape):
                points = curve_points(shape, 4, 36, -1, 1, events=[4, 8, 12])
                self.assertEqual(points[0]["time"], 4)
                self.assertEqual(points[-1]["time"], 36)
                self.assertTrue(all(-1 <= p["value"] <= 1 for p in points))
                steps = plan_steps(points, 4, 36, -1, 1, "hold", 0.0625)
                self.assertLessEqual(len(steps), 2048)

    def test_duck_follows_actual_events_and_recovers(self):
        points = curve_points(
            "duck", 0, 4, 0.1, 0.8, events=[1], release_beats=0.5, hold_beats=0.0625
        )
        by_time = {p["time"]: p["value"] for p in points}
        self.assertAlmostEqual(by_time[0], 0.8)
        self.assertAlmostEqual(by_time[1], 0.1)
        self.assertAlmostEqual(by_time[1.5625], 0.8)

    def test_invalid_curve_arguments(self):
        for kwargs in [
            dict(shape="unknown"),
            dict(low=float("nan")),
            dict(cycle_beats=0),
            dict(resolution=0),
            dict(end=0),
            dict(shape="duck", events=[]),
            dict(events=[float("inf")]),
            dict(hold_beats=-1),
        ]:
            args = dict(shape="wobble", start=0, end=4)
            args.update(kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                curve_points(**args)

    def test_phrase_deterministic_and_monophonic(self):
        for style in ["tearout", "dubstep", "brostep", "halftime"]:
            for role in ["call", "response", "sub"]:
                result = phrase(style, 8, 29, role, 42)
                self.assertEqual(result, phrase(style, 8, 29, role, 42))
                self.assertTrue(
                    all(
                        0 <= n["start_time"] < n["start_time"] + n["duration"] <= 32
                        for n in result["notes"]
                    )
                )
                self.assertFalse(inspect_sub_notes(result["notes"])["overlaps"])
                self.assertTrue(all(1 <= n["velocity"] <= 127 for n in result["notes"]))

    def test_call_response_do_not_overlap(self):
        for style in ["tearout", "brostep", "dubstep", "halftime"]:
            combined = phrase(style, role="call")["notes"] + phrase(style, role="response")["notes"]
            self.assertEqual(inspect_sub_notes(combined)["overlaps"], [])

    def test_recipe_variants_are_independent(self):
        for recipe_id in RECIPES:
            recipe = get_recipe(recipe_id)
            self.assertTrue(recipe["sources"])
            self.assertTrue(recipe["chain"])
            for d in recipe["chain"]:
                self.assertTrue(all(math.isfinite(v) for v in d["parameters"].values()))
            recipe["chain"][0]["parameters"]["Volume"] = 999
            self.assertNotEqual(get_recipe(recipe_id)["chain"][0]["parameters"]["Volume"], 999)

    def test_midi_analysis_has_honest_scope(self):
        self.assertIn("MIDI structure only", inspect_sub_notes([])["scope"])
        self.assertAlmostEqual(
            inspect_sub_notes([dict(pitch=29, start_time=0, duration=1)])["frequency_hz"]["29"],
            43.65,
        )


class Registry:
    def __init__(self):
        self.tools = {}

    def tool(self, **kwargs):
        def add(fn):
            self.tools[fn.__name__] = fn
            return fn

        return add


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.registry = Registry()
        self.calls = []
        self.capabilities = [
            "get_sound_design_parameters",
            "set_sound_design_parameters",
            "get_clip_envelope",
            "write_clip_envelope",
        ]
        self.track = dict(
            index=0,
            name="SUB",
            is_midi_track=True,
            devices=[],
            clip_slots=[dict(index=0, has_clip=False, clip=None)],
        )
        self.notes = []
        register(self.registry, self.send)

    def send(self, command, args):
        self.calls.append((command, copy.deepcopy(args)))
        if command == "get_script_info":
            return dict(capabilities=self.capabilities)
        if command == "get_track_info":
            return copy.deepcopy(self.track)
        if command == "create_clip":
            self.track["clip_slots"][0] = dict(
                index=0, has_clip=True, clip=dict(name="new", loop_start=0, loop_end=args["length"])
            )
            return {}
        if command == "set_clip_name":
            self.track["clip_slots"][0]["clip"]["name"] = args["name"]
            return {}
        if command == "add_notes_to_clip":
            self.notes += args["notes"]
            return {}
        if command == "get_clip_notes":
            return dict(notes=self.notes, note_count=len(self.notes))
        if command == "get_sound_design_parameters":
            return dict(
                parameters=[dict(index=1, name="Drive", min=-12, max=12, is_quantized=False)]
            )
        if command == "get_clip_envelope":
            return dict(loop_start=0, loop_end=4, min=-12, max=12, exists=False)
        if command == "write_clip_envelope":
            return dict(verified=True)
        raise AssertionError("Unexpected call " + command)

    def test_catalog_and_preview_never_call_live(self):
        self.assertEqual(len(self.registry.tools["bass_design_catalog"]()["recipes"]), len(RECIPES))
        self.registry.tools["preview_bass_design"]()
        self.registry.tools["bass_resampling_workflow"]()
        self.assertEqual(self.calls, [])

    def test_occupied_slot_preserved(self):
        self.track["clip_slots"][0]["has_clip"] = True
        with self.assertRaisesRegex(ValueError, "occupied"):
            self.registry.tools["create_bass_phrase"](0, 0, "SUB")
        self.assertEqual([c[0] for c in self.calls], ["get_track_info"])

    def test_phrase_readback(self):
        result = self.registry.tools["create_bass_phrase"](0, 0, "SUB", role="sub")
        self.assertTrue(result["verified"])

    def test_stale_target_rejected(self):
        with self.assertRaisesRegex(ValueError, "name changed"):
            self.registry.tools["create_bass_phrase"](0, 0, "OLD NAME")

    def test_movement_maps_parameter_range(self):
        self.track["clip_slots"][0] = dict(index=0, has_clip=True, clip=dict(name="SUB CLIP"))
        result = self.registry.tools["apply_bass_movement"](
            0, 0, "SUB", parameter_name="Drive", low=0, high=1
        )
        self.assertTrue(result["verified"])
        args = next(a for c, a in self.calls if c == "write_clip_envelope")
        self.assertAlmostEqual(min(p["value"] for p in args["points"]), -12)
        self.assertAlmostEqual(max(p["value"] for p in args["points"]), 12)
        self.assertEqual(args["expected_clip_name"], "SUB CLIP")
        self.assertEqual(args["interpolation"], "hold")

    def test_missing_reload_rejected_before_build(self):
        self.capabilities = []
        with self.assertRaisesRegex(RuntimeError, "Restart Ableton"):
            self.registry.tools["create_native_bass"]()
        self.assertEqual([c[0] for c in self.calls], ["get_script_info"])

    def test_parameter_inspection_arguments_are_serializable(self):
        import json

        self.registry.tools["get_sound_design_parameters"](0, 0, "SUB")
        json.dumps(self.calls)


class BuildTests(unittest.TestCase):
    def test_all_recipe_builds_and_movement(self):
        for recipe_id in RECIPES:
            with self.subTest(recipe=recipe_id):
                recipe = get_recipe(recipe_id)
                calls = []
                current = {
                    "index": 3,
                    "name": "new",
                    "is_midi_track": True,
                    "devices": [],
                    "clip_slots": [{"index": 0, "has_clip": False, "clip": None}],
                }
                notes = []

                def send(command, args):
                    calls.append(command)
                    if command == "get_script_info":
                        return {
                            "capabilities": [
                                "get_sound_design_parameters",
                                "set_sound_design_parameters",
                                "get_clip_envelope",
                                "write_clip_envelope",
                            ]
                        }
                    if command == "get_browser_items_at_path":
                        return {
                            "items": [
                                {
                                    "name": (
                                        d["preset"]
                                        if args["path"].endswith("/" + d["name"]) and d["preset"]
                                        else d["name"]
                                    ),
                                    "uri": "mock:" + d["name"],
                                    "is_loadable": True,
                                }
                                for d in recipe["chain"]
                            ]
                        }
                    if command == "create_midi_track":
                        return {"index": 3}
                    if command == "set_track_name":
                        current["name"] = args["name"]
                        return {}
                    if command == "load_browser_item":
                        d = recipe["chain"][len(current["devices"])]
                        current["devices"].append(
                            {
                                "name": d["preset"].removesuffix(".adv")
                                if d["preset"]
                                else d["name"],
                                "index": len(current["devices"]),
                            }
                        )
                        return {}
                    if command == "get_track_info":
                        return copy.deepcopy(current)
                    if command == "get_sound_design_parameters":
                        d = recipe["chain"][args["device_index"]]
                        return {
                            "device_name": current["devices"][args["device_index"]]["name"],
                            "parameters": [
                                {
                                    "name": name,
                                    "index": i,
                                    "min": 0,
                                    "max": 1,
                                    "is_quantized": False,
                                }
                                for i, name in enumerate(d["parameters"])
                            ],
                        }
                    if command == "set_sound_design_parameters":
                        return {"verified": True}
                    if command == "create_clip":
                        current["clip_slots"][0] = {
                            "index": 0,
                            "has_clip": True,
                            "clip": {"name": "new"},
                        }
                        return {}
                    if command == "set_clip_name":
                        current["clip_slots"][0]["clip"]["name"] = args["name"]
                        return {}
                    if command == "add_notes_to_clip":
                        notes.extend(args["notes"])
                        return {}
                    if command == "get_clip_notes":
                        return {"notes": notes, "note_count": len(notes)}
                    if command == "get_clip_envelope":
                        return {"loop_start": 0, "loop_end": 16, "min": 0, "max": 1}
                    if command == "write_clip_envelope":
                        self.assertLessEqual(len(args["points"]), 2048)
                        return {"verified": True}
                    raise AssertionError(command)

                registry = Registry()
                register(registry, send)
                result = registry.tools["create_native_bass"](recipe=recipe_id)
                self.assertEqual(result["track_index"], 3)
                self.assertEqual(len(result["verified_parameter_batches"]), len(recipe["chain"]))
                self.assertTrue(notes)
                self.assertNotIn("start_playback", calls)
                self.assertNotIn("set_tempo", calls)
                self.assertNotIn("duplicate_session_clip_to_arrangement", calls)


if __name__ == "__main__":
    unittest.main(verbosity=2)
