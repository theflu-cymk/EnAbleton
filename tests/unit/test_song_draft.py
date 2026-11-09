"""Song-draft planning stays local. Apply is checked against a fake Live session."""

import unittest

from enableton.song_draft import apply_draft, guide_draft, plan_draft, refine_draft, tool_families


def pitches(plan, role):
    track = next(row for row in plan["tracks"] if row["role"] == role)
    return [note["pitch"] for note in track["notes"]]


class GuideTests(unittest.TestCase):
    def test_asks_at_most_three_questions(self):
        guide = guide_draft()
        self.assertEqual(len(guide["questions"]), 3)
        self.assertFalse(guide["live_changes"])
        partial = guide_draft({"genre": "house"})
        self.assertEqual([row["field"] for row in partial["questions"]], ["energy", "key"])

    def test_dubstep_redirects_to_the_halftime_guide(self):
        guide = guide_draft({"genre": "dubstep", "energy": "high", "key": "Am"})
        self.assertEqual(guide["redirect_tool"], "guide_halftime_remix_workflow")
        self.assertNotIn("plan", guide)
        self.assertEqual(
            plan_draft({"genre": "riddim", "energy": "low", "key": "C"})["status"],
            "use_halftime_guide",
        )


class PlanTests(unittest.TestCase):
    def plan(self, **extra):
        config = {"genre": "house", "energy": "medium", "key": "Am", "bars": 32}
        config.update(extra)
        return plan_draft(config)

    def test_forms_roles_and_general_midi_guesses(self):
        short = self.plan(bars=16)
        self.assertEqual([row["name"] for row in short["sections"]], ["A", "B"])
        self.assertEqual(short["length_beats"], 64)
        medium = self.plan()
        self.assertEqual(medium["sections"][0]["name"], "Intro")
        self.assertEqual(medium["length_beats"], 128)
        long = self.plan(bars=64)
        self.assertIn("Breakdown", [row["name"] for row in long["sections"]])
        self.assertEqual(long["length_beats"], 256)
        self.assertEqual([row["name"] for row in medium["tracks"]], ["Drums", "Bass", "Chords"])
        self.assertIn(45, pitches(medium, "bass"))
        self.assertEqual(medium["drum_pitches"]["kick"], 36)
        self.assertIn("get_drum_pads", medium["drum_pitches"]["evidence"])
        self.assertIn(42, pitches(medium, "drums"))
        high = self.plan(energy="high", bars=16)
        self.assertEqual(high["tracks"][-1]["name"], "Lead")

    def test_refine_tokens_and_locked_sections(self):
        planned = self.plan(energy="low", bars=32)
        space = refine_draft(planned, ["more_space"])["plan"]
        self.assertNotIn(42, pitches(space, "drums"))
        energetic = refine_draft(planned, ["more_energy"])["plan"]
        self.assertIn(42, pitches(energetic, "drums"))
        velocities = [note["velocity"] for note in energetic["tracks"][0]["notes"]]
        self.assertGreater(max(velocities), 78)
        brighter = refine_draft(self.plan(bars=32), ["brighter"])["plan"]
        self.assertGreaterEqual(min(pitches(brighter, "chords")), 72)
        darker = refine_draft(self.plan(bars=32), ["darker"])["plan"]
        self.assertLessEqual(max(pitches(darker, "chords")), 59)
        self.assertEqual(refine_draft(self.plan(bars=64), ["shorter"])["plan"]["bars"], 16)
        self.assertEqual(refine_draft(self.plan(bars=16), ["longer"])["plan"]["bars"], 32)
        self.assertEqual(refine_draft(self.plan(bars=32), ["longer"])["plan"]["bars"], 64)
        locked = self.plan(bars=32)
        locked["locked_sections"] = ["A"]
        locked["config"]["locked_sections"] = ["A"]
        revised = refine_draft(locked, ["brighter"])["plan"]
        window = next(row for row in revised["sections"] if row["name"] == "A")
        old = [
            note["pitch"]
            for note in next(row for row in locked["tracks"] if row["role"] == "chords")["notes"]
            if window["start_beat"] <= note["start_time"] < window["end_beat"]
        ]
        kept = [
            note["pitch"]
            for note in next(row for row in revised["tracks"] if row["role"] == "chords")["notes"]
            if window["start_beat"] <= note["start_time"] < window["end_beat"]
        ]
        self.assertEqual(sorted(kept), sorted(old))
        self.assertGreaterEqual(
            min(
                note["pitch"] for note in revised["tracks"][2]["notes"] if note["start_time"] >= 64
            ),
            72,
        )
        with self.assertRaisesRegex(ValueError, "unlock"):
            refine_draft(locked, ["shorter"])


class FakeLive:
    def __init__(self, playing=False, meter=(4, 4), scenes=8):
        self.calls = []
        self.playing = playing
        self.meter = meter
        self.scenes = scenes
        self.time = 12.0
        self.next_index = 4
        self.tracks = {}
        self.locators = []
        self.undone = 0
        self.fail_on = None
        self.index_bias = 0

    def __call__(self, command, params):
        params = dict(params or {})
        self.calls.append((command, params))
        if command == self.fail_on:
            raise RuntimeError("injected failure")
        if command == "get_session_info":
            return {
                "is_playing": self.playing,
                "record_mode": False,
                "signature_numerator": self.meter[0],
                "signature_denominator": self.meter[1],
                "scene_count": self.scenes,
                "current_song_time": self.time,
                "tempo": 120,
                "track_count": self.next_index,
            }
        if command == "batch":
            results = []
            commands = params.get("commands") or []
            try:
                for cmd in commands:
                    result = self(cmd.get("type"), cmd.get("params") or {})
                    results.append({"type": cmd.get("type"), "result": result})
            except Exception as error:
                raise RuntimeError(
                    "batch failed at step %d of %d: %s (completed steps are one undo away)"
                    % (len(results), len(commands), error)
                ) from error
            return {"executed": len(results), "results": results}
        if command == "undo":
            self.undone += 1
            self.tracks.clear()
            self.next_index = 4
            return {"undone": True}
        if command == "get_locators":
            return {"locators": [dict(row) for row in self.locators]}
        if command == "set_tempo":
            return {"tempo": params["tempo"]}
        if command == "create_midi_track":
            index = self.next_index
            self.next_index += 1
            self.tracks[index] = {"name": "", "has_clip": False, "devices": []}
            return {"index": index + self.index_bias, "name": "MIDI"}
        if command == "get_track_info":
            track = self.tracks[params["track_index"]]
            return {
                "name": track["name"],
                "clip_slots": [{"has_clip": track["has_clip"]}],
                "devices": track["devices"],
            }
        if command == "set_track_name":
            self.tracks[params["track_index"]]["name"] = params["name"]
            return {}
        if command == "set_clip_name":
            self.tracks[params["track_index"]]["clip_name"] = params["name"]
            return {"name": params["name"]}
        if command == "create_clip":
            self.tracks[params["track_index"]]["has_clip"] = True
            return {}
        if command == "add_notes_to_clip":
            self.tracks[params["track_index"]]["notes"] = params["notes"]
            return {}
        if command == "set_current_song_time":
            self.time = params["time"]
            return {}
        if command == "create_locator":
            return {"name": params["name"], "time": self.time}
        raise AssertionError(command)


class ApplyTests(unittest.TestCase):
    def test_confirm_and_transport_guards_send_nothing_dangerous(self):
        plan = plan_draft({"genre": "pop", "energy": "medium", "key": "C", "bars": 16})
        live = FakeLive()
        preview = apply_draft(live, plan, confirm=False)
        self.assertFalse(preview["live_changes"])
        self.assertEqual(live.calls, [])
        live.playing = True
        with self.assertRaisesRegex(ValueError, "Stop playback"):
            apply_draft(live, plan, confirm=True)
        self.assertEqual([call[0] for call in live.calls], ["get_session_info"])
        stopped = FakeLive(meter=(3, 4))
        with self.assertRaisesRegex(ValueError, "4/4"):
            apply_draft(stopped, plan, confirm=True)
        self.assertNotIn("start_playback", [call[0] for call in stopped.calls])

    def test_apply_uses_returned_indexes_and_restores_the_playhead(self):
        plan = plan_draft(
            {
                "genre": "melodic",
                "energy": "high",
                "key": "F#m",
                "bars": 16,
                "tempo": 100,
                "apply_tempo": True,
            }
        )
        live = FakeLive()
        report = apply_draft(live, plan, confirm=True)
        self.assertEqual([row["track_index"] for row in report["tracks"]], [4, 5, 6, 7])
        self.assertEqual(
            [row["name"] for row in report["tracks"]], ["Drums", "Bass", "Chords", "Lead"]
        )
        self.assertFalse(report["playback_started"])
        self.assertTrue(report["tempo_changed"])
        self.assertEqual(report["locators_skipped"], [])
        self.assertEqual([row["name"] for row in report["locators"]], ["A", "B"])
        batch = live.calls[1]
        self.assertEqual(batch[0], "batch")
        kinds = [command["type"] for command in batch[1]["commands"]]
        self.assertEqual(kinds[0], "set_tempo")
        self.assertEqual(batch[1]["commands"][0]["params"]["tempo"], 100)
        self.assertNotIn("create_locator", kinds)
        self.assertNotIn("set_current_song_time", kinds)
        names = [
            command["params"]["name"]
            for command in batch[1]["commands"]
            if command["type"] == "set_track_name"
        ]
        self.assertEqual(names, ["Drums", "Bass", "Chords", "Lead"])
        indexes = [
            command["params"]["track_index"]
            for command in batch[1]["commands"]
            if command["type"] == "set_track_name"
        ]
        self.assertEqual(indexes, [4, 5, 6, 7])
        self.assertNotIn("start_playback", [call[0] for call in live.calls])
        self.assertEqual(live.time, 12.0)
        self.assertEqual(live.calls[-1], ("set_current_song_time", {"time": 12.0}))
        locator_names = [call[1]["name"] for call in live.calls if call[0] == "create_locator"]
        self.assertEqual(locator_names, ["A", "B"])

    def test_an_existing_locator_at_zero_is_not_renamed(self):
        plan = plan_draft({"genre": "pop", "energy": "medium", "key": "C", "bars": 16})
        live = FakeLive()
        live.locators = [{"index": 0, "name": "Drop", "time": 0.0}]
        report = apply_draft(live, plan, confirm=True)
        self.assertEqual(report["locators_skipped"], [0.0])
        self.assertEqual([row["name"] for row in report["locators"]], ["B"])
        moved = [call[1]["time"] for call in live.calls if call[0] == "set_current_song_time"]
        self.assertNotIn(0, moved)
        self.assertNotIn(0.0, moved)

    def test_a_mid_batch_failure_undoes_the_apply(self):
        plan = plan_draft({"genre": "pop", "energy": "medium", "key": "C", "bars": 16})
        live = FakeLive()
        live.fail_on = "create_clip"
        with self.assertRaisesRegex(RuntimeError, "batch failed"):
            apply_draft(live, plan, confirm=True)
        self.assertEqual(live.undone, 1)
        self.assertEqual(live.tracks, {})
        self.assertNotIn("create_locator", [call[0] for call in live.calls])

    def test_a_wrong_track_index_is_undone(self):
        plan = plan_draft({"genre": "pop", "energy": "medium", "key": "C", "bars": 16})
        live = FakeLive()
        live.index_bias = 3
        with self.assertRaisesRegex(RuntimeError, "did not match"):
            apply_draft(live, plan, confirm=True)
        self.assertEqual(live.undone, 1)
        self.assertEqual(live.tracks, {})

    def test_a_tampered_plan_is_refused_before_live(self):
        plan = plan_draft({"genre": "hip_hop", "energy": "medium", "key": "Bb", "bars": 16})
        plan["tracks"][0]["notes"][0]["pitch"] = 40
        live = FakeLive()
        with self.assertRaisesRegex(ValueError, "plan again"):
            apply_draft(live, plan, confirm=True)
        self.assertEqual(live.calls, [])


class FamilyTests(unittest.TestCase):
    def test_families_name_real_tools_and_do_not_rename_magnitude(self):
        described = tool_families()
        names = [tool for family in described["families"] for tool in family["tools"]]
        for name in (
            "create_arrangement_audio_clip",
            "inspect_rack",
            "map_rack_blend_macro",
            "set_plugin_parameter",
            "guide_song_draft",
            "guide_halftime_remix_workflow",
            "get_drum_pads",
            "plan_track_preparation",
            "apply_track_preparation",
            "plan_instrument_assignment",
            "apply_instrument_assignment",
            "plan_audio_repair",
            "apply_audio_repair",
            "plan_track_alignment",
            "apply_track_alignment",
        ):
            self.assertIn(name, names)
        self.assertNotIn("map_rack_magnitude", names)
        self.assertFalse(described["live_changes"])
