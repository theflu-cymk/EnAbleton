"""Content names, role colors, and muted originals."""

import unittest

from enableton.track_prep import _find_copy, apply_plan, plan_tracks


def track(index, name, clips=None, devices=None, **extra):
    return {
        "index": index,
        "name": name,
        "clips": clips
        if clips is not None
        else [
            {"name": name, "view": "arrangement", "index": 0, "start_beats": 0.0, "type": "audio"}
        ],
        "devices": devices or [],
        **extra,
    }


class PlanTests(unittest.TestCase):
    def names(self, tracks):
        plan = plan_tracks(tracks)
        return [(row["working_name"], row["role"], row["color_index"]) for row in plan["tracks"]]

    def test_song_title_is_removed_and_roles_are_colored(self):
        tracks = [
            track(0, "1-Bass - fortnight"),
            track(1, "2-Drums - fortnight"),
            track(2, "3-Guitar - fortnight"),
            track(3, "4-Instrumental - fortnight"),
            track(4, "5-Piano - fortnight"),
            track(5, "7-Vocals - fortnight"),
            track(6, "8-Serum 2"),
        ]
        self.assertEqual(
            self.names(tracks),
            [
                ("01 Bass", "bass", 20),
                ("02 Drums", "drums", 6),
                ("03 Guitar", "guitar", 22),
                ("04 Reference", "reference", 14),
                ("05 Keys", "keys", 24),
                ("06 Lead Vox", "lead_vox", 11),
                ("07 Synth | Serum 2", "synth", 30),
            ],
        )

    def test_device_and_midi_content_are_used_when_the_name_is_generic(self):
        drums = track(
            0,
            "Audio",
            clips=[
                {
                    "name": "Audio",
                    "view": "arrangement",
                    "index": 0,
                    "start_beats": 0.0,
                    "type": "midi",
                    "notes": [
                        {"pitch": 36, "start_time": i, "duration": 0.25, "mute": False}
                        for i in range(8)
                    ],
                }
            ],
            devices=["Drum Rack"],
        )
        bass = track(
            1,
            "MIDI",
            clips=[
                {
                    "name": "MIDI",
                    "view": "arrangement",
                    "index": 0,
                    "start_beats": 0.0,
                    "type": "midi",
                    "notes": [
                        {"pitch": 40, "start_time": i, "duration": 1, "mute": False}
                        for i in range(8)
                    ],
                }
            ],
        )
        named = self.names([drums, bass])
        self.assertEqual(named[0][1], "drums")
        self.assertEqual(named[1][1], "bass")
        self.assertIn("Drum Rack", plan_tracks([drums, bass])["tracks"][0]["evidence"])

    def test_generic_clip_is_renamed_and_a_real_clip_name_stays(self):
        plan = plan_tracks(
            [
                track(
                    0,
                    "1-Bass - fortnight",
                    clips=[
                        {"name": "Track 1", "view": "arrangement", "index": 0, "start_beats": 0.0},
                        {"name": "Hook", "view": "arrangement", "index": 1, "start_beats": 16.0},
                    ],
                )
            ]
        )
        renames = plan["tracks"][0]["clip_renames"]
        self.assertEqual(
            renames,
            [
                {
                    "clip_index": 0,
                    "expected_name": "Track 1",
                    "start_beats": 0.0,
                    "name": "01 Bass | Fortnight",
                }
            ],
        )
        self.assertEqual(plan["tracks"][0]["original_name"], "ORIGINAL | 01 Bass | Fortnight")
        self.assertEqual(plan["tracks"][0]["original_color"], 13)
        self.assertTrue(plan["live_changes"] is False)

    def test_originals_groups_and_empty_tracks_are_skipped(self):
        plan = plan_tracks(
            [
                track(0, "ORIGINAL | 01 Bass", clips=[]),
                track(1, "Group", clips=[], extra_ignored=True, is_group=True),
                track(2, "Empty", clips=[]),
                track(3, "1-Bass - fortnight"),
            ]
        )
        self.assertEqual([row["working_name"] for row in plan["tracks"]], ["01 Bass | Fortnight"])
        self.assertEqual(
            [row["reason"] for row in plan["skipped"]],
            ["already an original", "return, main or group", "no clips or devices"],
        )

    def test_a_second_run_does_not_plan_another_duplicate(self):
        plan = plan_tracks(
            [
                track(0, "01 Bass"),
                track(1, "ORIGINAL | 01 Bass", clips=[]),
            ]
        )
        self.assertEqual(plan["tracks"][0]["status"], "ready")

    def test_notes_warp_and_faders_are_not_in_the_plan(self):
        plan = plan_tracks([track(0, "1-Bass - fortnight")])
        self.assertEqual(
            plan["leaves_unchanged"],
            ["notes", "warp", "faders", "arrangement positions", "returns", "groups"],
        )
        self.assertNotIn("volume", plan["tracks"][0])


class FakeLive:
    def __init__(self, fold_copy=False):
        self.fold_copy = fold_copy
        self.tracks = [
            {
                "name": "1-Bass - fortnight",
                "mute": False,
                "solo": False,
                "arm": True,
                "is_foldable": False,
                "clips": [{"name": "Track 1"}],
            },
            {
                "name": "2-Drums - fortnight",
                "mute": False,
                "solo": True,
                "arm": False,
                "is_foldable": False,
                "clips": [{"name": "Drums - fortnight"}],
            },
            {
                "name": "3-Guitar - fortnight",
                "mute": False,
                "solo": False,
                "arm": False,
                "is_foldable": False,
                "clips": [{"name": "Guitar - fortnight"}],
            },
        ]
        self.playing = False

    def __call__(self, command, params):
        if command == "get_session_info":
            return {
                "track_count": len(self.tracks),
                "is_playing": self.playing,
                "record_mode": False,
            }
        if command == "get_track_info":
            return dict(self.tracks[params["track_index"]])
        if command == "duplicate_track":
            index = params["track_index"]
            copy = dict(self.tracks[index])
            copy["clips"] = [dict(clip) for clip in copy["clips"]]
            copy["is_foldable"] = self.fold_copy
            number, dash, rest = copy["name"].partition("-")
            if dash and number.isdigit():
                copy["name"] = f"{int(number) + 1}-{rest}"
            self.tracks.insert(index + 1, copy)
            return {"ok": True}
        if command == "write_access_object":
            if params["object_type"] == "track":
                row = self.tracks[params["track_index"]]
                if params["expected_track_name"] != row["name"]:
                    raise RuntimeError("name guard failed")
                row.update(params["properties"])
                return {"ok": True}
            row = self.tracks[params["track_index"]]
            if params["expected_track_name"] != row["name"]:
                raise RuntimeError("clip track guard failed")
            clip = row["clips"][params["clip_index"]]
            if params["expected_clip_name"] != clip["name"]:
                raise RuntimeError("clip guard failed")
            clip["name"] = params["properties"]["name"]
            return {"ok": True}
        if command == "get_group_info":
            row = self.tracks[params["track_index"]]
            return {
                "is_foldable": row.get("is_foldable", False),
                "fold_state": row.get("fold_state"),
            }
        if command == "set_fold_state":
            row = self.tracks[params["track_index"]]
            if not row.get("is_foldable"):
                raise RuntimeError("Track is not a group track")
            row["fold_state"] = bool(params.get("folded", True))
            return {"fold_state": row["fold_state"]}
        if command == "batch":
            results = []
            for row in params["commands"]:
                results.append({"result": self(row["type"], row["params"])})
            return {"executed": len(results), "results": results}
        raise AssertionError(command)


class ClipNamedDuplicateTests(unittest.TestCase):
    def send(self, tracks):
        def send(command, params):
            if command != "get_track_info":
                raise AssertionError(command)
            return tracks[params["track_index"]]

        return send

    def test_a_proven_insert_is_accepted_when_live_names_it_after_the_clip(self):
        tracks = [{"name": "13-Audio"}, {"name": "14-HeavyDrops"}]
        send = self.send(tracks)
        with self.assertRaises(RuntimeError):
            _find_copy(send, 0, "13-Audio", len(tracks), previous_count=len(tracks))
        tracks.insert(1, {"name": "Ghosthack-DD_Drum Loop_Bully_120_Kick & Snare"})
        index, found = _find_copy(send, 0, "13-Audio", len(tracks), previous_count=2)
        self.assertEqual((index, found), (1, "Ghosthack-DD_Drum Loop_Bully_120_Kick & Snare"))
        with self.assertRaises(RuntimeError):
            _find_copy(send, 0, "13-Audio", len(tracks))

    def test_a_protected_neighbor_is_not_renamed_when_the_count_grew(self):
        tracks = [
            {"name": "13-Audio"},
            {"name": "ORIGINAL | 13-Audio"},
            {"name": "14-HeavyDrops"},
        ]
        with self.assertRaises(RuntimeError):
            _find_copy(self.send(tracks), 0, "13-Audio", len(tracks), previous_count=2)


class ClipNamedLive(FakeLive):
    def __call__(self, command, params):
        if command == "duplicate_track":
            index = params["track_index"]
            copy = dict(self.tracks[index])
            copy["clips"] = [dict(clip) for clip in copy["clips"]]
            copy["name"] = copy["clips"][0]["name"]
            self.tracks.insert(index + 1, copy)
            return {"ok": True}
        return super().__call__(command, params)


class ApplyTests(unittest.TestCase):
    def test_original_is_muted_and_working_track_is_renamed(self):
        live = FakeLive()
        plan = plan_tracks(
            [
                track(
                    0,
                    "1-Bass - fortnight",
                    clips=[
                        {
                            "name": "Track 1",
                            "view": "arrangement",
                            "index": 0,
                            "start_beats": 0.0,
                        }
                    ],
                ),
                track(1, "2-Drums - fortnight"),
                track(2, "3-Guitar - fortnight"),
            ]
        )
        preview = apply_plan(live, plan, confirm=False)
        self.assertFalse(preview["live_changes"])
        self.assertFalse(any(row["name"].startswith("ORIGINAL") for row in live.tracks))
        result = apply_plan(live, plan, confirm=True)
        self.assertEqual(
            [row["name"] for row in live.tracks],
            [
                "01 Bass",
                "ORIGINAL | 01 Bass",
                "02 Drums",
                "ORIGINAL | 02 Drums",
                "03 Guitar",
                "ORIGINAL | 03 Guitar",
            ],
        )
        self.assertFalse(live.tracks[0]["mute"])
        self.assertTrue(live.tracks[1]["mute"])
        self.assertFalse(live.tracks[1]["solo"])
        self.assertFalse(live.tracks[1]["arm"])
        self.assertEqual(live.tracks[0]["color_index"], 20)
        self.assertEqual(live.tracks[1]["color_index"], 13)
        self.assertEqual(live.tracks[0]["clips"][0]["name"], "01 Bass")
        self.assertFalse(result["results"][0]["fold_applied"])
        self.assertIn("group", result["results"][0]["fold"])
        self.assertFalse(result["playback_started"])

    def test_a_group_original_is_folded(self):
        live = FakeLive(fold_copy=True)
        plan = plan_tracks([track(0, "1-Bass - fortnight")])
        result = apply_plan(live, plan, confirm=True)
        self.assertTrue(result["results"][0]["fold_applied"])
        self.assertTrue(live.tracks[1]["fold_state"])

    def test_a_clip_named_duplicate_is_protected(self):
        live = ClipNamedLive()
        live.tracks = [
            {
                "name": "13-Audio",
                "mute": False,
                "solo": False,
                "arm": False,
                "is_foldable": False,
                "clips": [{"name": "Ghosthack-DD_Drum Loop_Bully_120_Kick & Snare"}],
            }
        ]
        plan = plan_tracks(
            [
                track(
                    0,
                    "13-Audio",
                    clips=[
                        {
                            "name": "Ghosthack-DD_Drum Loop_Bully_120_Kick & Snare",
                            "view": "arrangement",
                            "index": 0,
                            "start_beats": 96.0,
                        }
                    ],
                )
            ]
        )
        apply_plan(live, plan, confirm=True)
        self.assertEqual(
            [row["name"] for row in live.tracks],
            ["01 Drums", "ORIGINAL | 01 Drums"],
        )
        self.assertTrue(live.tracks[1]["mute"])
        self.assertFalse(live.tracks[1]["solo"])
        self.assertFalse(live.tracks[1]["arm"])

    def test_playback_blocks_the_apply(self):
        live = FakeLive()
        live.playing = True
        plan = plan_tracks([track(0, "1-Bass - fortnight")])
        with self.assertRaises(ValueError):
            apply_plan(live, plan, confirm=True)
        self.assertEqual(len(live.tracks), 3)


if __name__ == "__main__":
    unittest.main()
