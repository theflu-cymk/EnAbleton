"""Placeholder instruments for MIDI tracks that have notes and no instrument."""

import unittest
from unittest.mock import patch

from enableton.assign_instruments import (
    apply_plan,
    has_instrument,
    plan_assignments,
    plan_live,
)


def notes(pitches, duration=1):
    return [
        {"pitch": pitch, "start_time": float(index), "duration": duration, "mute": False}
        for index, pitch in enumerate(pitches)
    ]


def midi(index, name, pitches, devices=None, **extra):
    return {
        "index": index,
        "name": name,
        "type": "midi",
        "devices": devices or [],
        "clips": [
            {
                "name": name,
                "view": "arrangement",
                "index": 0,
                "start_beats": 0.0,
                "type": "midi",
                "notes": notes(pitches),
            }
        ],
        **extra,
    }


class PlanTests(unittest.TestCase):
    def test_roles_pick_audible_placeholders(self):
        drum_notes = [
            {"pitch": 36, "start_time": float(i), "duration": 0.25, "mute": False} for i in range(8)
        ]
        plan = plan_assignments(
            [
                {
                    "index": 0,
                    "name": "MIDI",
                    "type": "midi",
                    "devices": [],
                    "clips": [
                        {
                            "name": "MIDI",
                            "type": "midi",
                            "notes": drum_notes,
                            "view": "arrangement",
                            "index": 0,
                            "start_beats": 0,
                        }
                    ],
                },
                midi(1, "Bass", [40] * 8),
                midi(2, "Piano", [48, 52, 55, 60, 64, 67]),
            ]
        )
        self.assertEqual(
            [(row["role"], row["candidates"]) for row in plan["tracks"]],
            [
                ("drums", ["Impulse"]),
                ("bass", ["Operator"]),
                ("keys", ["Electric", "Wavetable"]),
            ],
        )
        self.assertIn("Replace it", plan["tracks"][0]["reason"])
        self.assertIn("empty Drum Rack", plan["choices"]["drums"])
        self.assertNotIn("notes", plan["writes"][0])

    def test_loaded_instruments_and_effects_are_distinct(self):
        self.assertTrue(has_instrument([{"name": "Serum", "type": "plugin", "class_name": ""}]))
        self.assertTrue(
            has_instrument([{"name": "Operator", "type": "instrument", "class_name": "Operator"}])
        )
        self.assertFalse(
            has_instrument([{"name": "EQ Eight", "type": "audio_effect", "class_name": "Eq8"}])
        )
        self.assertFalse(has_instrument(["EQ Eight", "Utility"]))
        self.assertTrue(has_instrument(["Serum"]))
        self.assertTrue(
            has_instrument(
                [
                    {
                        "name": "Instrument Rack",
                        "type": "rack",
                        "class_name": "InstrumentGroupDevice",
                    }
                ]
            )
        )
        self.assertFalse(
            has_instrument(
                [
                    {
                        "name": "Audio Effect Rack",
                        "type": "rack",
                        "class_name": "AudioEffectGroupDevice",
                    }
                ]
            )
        )
        plan = plan_assignments(
            [
                midi(0, "Bass", [40] * 8, devices=[{"name": "Serum", "type": "plugin"}]),
                midi(
                    1,
                    "Bass 2",
                    [40] * 8,
                    devices=[{"name": "EQ Eight", "type": "audio_effect"}],
                ),
                midi(2, "Audio", [60] * 8, type="audio"),
                midi(3, "Empty", []),
                midi(4, "ORIGINAL | 01 Bass", [40] * 8),
                midi(5, "Kit", [36] * 8, is_group=True),
                midi(6, "Out", [40] * 8, midi_output="MPK mini"),
                midi(7, "Silent", [40] * 8, midi_output="No Output"),
                midi(8, "Mix", [40] * 8, midi_output="Main"),
            ]
        )
        self.assertEqual([row["track_name"] for row in plan["tracks"]], ["Bass 2", "Silent", "Mix"])
        reasons = {row["name"]: row["reason"] for row in plan["skipped"]}
        self.assertIn("already has an instrument", reasons["Bass"])
        self.assertIn("not a MIDI", reasons["Audio"])
        self.assertIn("no active notes", reasons["Empty"])
        self.assertIn("original", reasons["ORIGINAL | 01 Bass"])
        self.assertIn("group", reasons["Kit"])
        self.assertIn("routed", reasons["Out"])

    def test_muted_notes_are_not_assigned(self):
        track = midi(0, "Bass", [40] * 8)
        track["clips"][0]["notes"] = [
            {"pitch": 40, "start_time": 0, "duration": 1, "mute": True} for _ in range(8)
        ]
        plan = plan_assignments([track])
        self.assertEqual(plan["tracks"], [])
        self.assertIn("no active notes", plan["skipped"][0]["reason"])


class FakeLive:
    def __init__(self):
        self.tracks = [{"name": "Bass", "is_frozen": False, "devices": []}]
        self.playing = False
        self.items = {
            "instruments": [
                {"name": "Operator", "uri": "live://operator", "is_loadable": True},
                {"name": "Wavetable", "uri": "live://wavetable", "is_loadable": True},
                {"name": "Impulse", "uri": "live://impulse", "is_loadable": True},
                {"name": "Electric", "uri": "live://electric", "is_loadable": True},
            ]
        }
        self.loads = []
        self.calls = []
        self.appear = True
        self.sleeps = 0

    def __call__(self, command, params):
        self.calls.append(command)
        if command == "get_session_info":
            return {"is_playing": self.playing, "record_mode": False, "track_count": 1}
        if command == "get_track_info":
            return dict(self.tracks[params["track_index"]], devices=list(self.tracks[0]["devices"]))
        if command == "get_browser_items_at_path":
            return {"items": list(self.items.get(params["path"], []))}
        if command == "load_browser_item":
            self.loads.append(params["item_uri"])
            if self.appear:
                name = params["item_uri"].rsplit("/", 1)[-1].title()
                self.tracks[0]["devices"].append(
                    {"index": 0, "name": name, "type": "instrument", "class_name": name}
                )
            return {"loaded": True}
        if command == "set_sound_design_parameters":
            raise AssertionError("placeholder load must not edit parameters")
        raise AssertionError(command)


class ApplyTests(unittest.TestCase):
    def plan(self):
        return plan_assignments([midi(0, "Bass", [40] * 8)])

    def test_confirm_and_playback_are_required_gates(self):
        live = FakeLive()
        preview = apply_plan(live, self.plan(), confirm=False)
        self.assertFalse(preview["live_changes"])
        live.playing = True
        with self.assertRaisesRegex(ValueError, "playback"):
            apply_plan(live, self.plan(), confirm=True)
        self.assertEqual(live.loads, [])

    def test_operator_loads_once_and_parameters_stay(self):
        live = FakeLive()
        result = apply_plan(live, self.plan(), confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.loads, ["live://operator"])
        self.assertEqual(live.tracks[0]["devices"][0]["name"], "Operator")
        self.assertIn("Replace it", result["results"][0]["message"])
        self.assertTrue(result["live_changes"])
        self.assertFalse(result["playback_started"])
        self.assertNotIn("set_sound_design_parameters", live.calls)

    def test_missing_electric_falls_back_to_wavetable(self):
        live = FakeLive()
        live.items["instruments"] = [
            item for item in live.items["instruments"] if item["name"] != "Electric"
        ]
        plan = plan_assignments([midi(0, "Piano", [48, 52, 55, 60, 64, 67])])
        live.tracks[0]["name"] = "Piano"
        apply_plan(live, plan, confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.loads, ["live://wavetable"])

    def test_an_unconfirmed_load_is_not_retried(self):
        live = FakeLive()
        live.appear = False

        def sleeper(_seconds):
            live.sleeps += 1

        with self.assertRaisesRegex(RuntimeError, "Inspect that track"):
            apply_plan(live, self.plan(), confirm=True, sleeper=sleeper)
        self.assertEqual(live.loads, ["live://operator"])
        self.assertEqual(live.sleeps, 12)

    def test_a_device_that_appears_later_is_left_alone(self):
        live = FakeLive()
        live.tracks[0]["devices"] = [{"name": "Serum", "type": "plugin", "class_name": "Plugin"}]
        result = apply_plan(live, self.plan(), confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.loads, [])
        self.assertIn("already has an instrument", result["not_applied"][0]["reason"])


class LivePlanTests(unittest.TestCase):
    @patch("enableton.song_lint.collect_live")
    def test_hardware_output_is_skipped_and_a_failed_read_is_unconfirmed(self, collect):
        collect.return_value = {
            "tracks": [
                {
                    "index": 0,
                    "name": "Bass",
                    "type": "midi",
                    "is_group": False,
                    "devices": [],
                    "clips": [
                        {
                            "name": "Bass",
                            "view": "arrangement",
                            "type": "midi",
                            "start_beats": 0,
                            "notes": notes([40] * 8),
                            "locator": {"clip_index": 0},
                        }
                    ],
                }
            ],
            "capture_errors": [],
        }

        def routed(command, params):
            self.assertEqual(command, "get_track_routing")
            self.assertEqual(params["track_index"], 0)
            return {"output_routing_type": {"display_name": "MPK mini"}}

        plan = plan_live(routed)
        self.assertEqual(plan["tracks"], [])
        self.assertIn("routed", plan["skipped"][0]["reason"])

        def missing(_command, _params):
            raise RuntimeError("routing is not loaded")

        plan = plan_live(missing)
        self.assertEqual(plan["tracks"][0]["candidates"], ["Operator"])
        self.assertTrue(plan["routing_unconfirmed"])
        self.assertEqual(plan["tracks"][0]["routing"], "not confirmed")


if __name__ == "__main__":
    unittest.main()
