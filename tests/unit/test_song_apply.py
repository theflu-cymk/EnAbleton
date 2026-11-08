"""Live adapter behaviour: guards, ID-based note reconciliation, refusals."""

from copy import deepcopy
import unittest
from unittest import mock

from enableton.song_apply import LiveAdapter
from enableton.song_init import UnsupportedOperations


def capture():
    return {
        "session": {"tempo": 140, "numerator": 4, "denominator": 4},
        "tracks": [
            {
                "id": "track:0",
                "index": 0,
                "name": "Bass",
                "type": "midi",
                "clips": [
                    {
                        "id": "track:0:session:0",
                        "name": "Phrase",
                        "view": "session",
                        "type": "midi",
                        "locator": dict(
                            track_index=0,
                            clip_view="session",
                            clip_index=0,
                            expected_track_name="Bass",
                            expected_clip_name="Phrase",
                        ),
                        "start_beats": 0.0,
                        "end_beats": 4.0,
                        "notes": [],
                    },
                    {
                        "id": "track:0:arrangement:0",
                        "name": "Verse",
                        "view": "arrangement",
                        "type": "midi",
                        "locator": dict(
                            track_index=0,
                            clip_view="arrangement",
                            clip_index=0,
                            expected_track_name="Bass",
                            expected_clip_name="Verse",
                            expected_start_time=8.0,
                        ),
                        "start_beats": 8.0,
                        "end_beats": 16.0,
                        "notes": [],
                    },
                ],
            },
            {
                "id": "track:1",
                "index": 1,
                "name": "Empty",
                "type": "midi",
                "clips": [],
            },
            {
                "id": "track:2",
                "index": 2,
                "name": "Vox",
                "type": "audio",
                "clips": [
                    {
                        "id": "track:2:session:0",
                        "name": "Take",
                        "view": "session",
                        "type": "audio",
                        "locator": dict(
                            track_index=2,
                            clip_view="session",
                            clip_index=0,
                            expected_track_name="Vox",
                            expected_clip_name="Take",
                        ),
                        "start_beats": 0.0,
                        "end_beats": 16.0,
                        "notes": [],
                    }
                ],
            },
        ],
    }


def notes():
    return {
        1: {
            "note_id": 1,
            "pitch": 40,
            "start_time": 0.1,
            "duration": 1.0,
            "velocity": 90.0,
            "mute": False,
        },
        2: {
            "note_id": 2,
            "pitch": 40,
            "start_time": 2.0,
            "duration": 1.0,
            "velocity": 90.0,
            "mute": False,
        },
    }


class FakeBridge:
    def __init__(self, ignore=()):
        self.notes = notes()
        self.calls = []
        self.ignore = set(ignore)
        self.state = capture()
        self.properties = {}

    def __call__(self, command, params):
        self.calls.append((command, deepcopy(params)))
        if command in self.ignore:
            return {"verified": False}
        if command == "get_access_notes":
            return {"notes": [dict(note) for note in self.notes.values()]}
        if command == "modify_access_notes":
            for row in params["notes"]:
                self.notes[row["note_id"]].update(
                    {key: value for key, value in row.items() if key != "note_id"}
                )
            return {"verified": True}
        if command == "delete_access_notes":
            for row in params["notes"]:
                self.notes.pop(row["note_id"])
            return {"verified": True}
        if command == "insert_access_notes":
            for row in params["notes"]:
                ident = max(self.notes) + 1
                self.notes[ident] = dict(row, note_id=ident)
            return {"verified": True}
        if command == "write_access_object":
            self.properties.update(params.get("properties", {}))
            return {"verified": True}
        if command == "read_access_object":
            return {"properties": dict(self.properties)}
        if command == "set_access_warp":
            self.properties.update(params["properties"])
            return {"verified": True}
        if command == "delete_track":
            self.state["tracks"] = [
                track for track in self.state["tracks"] if track["index"] != params["track_index"]
            ]
            return {"deleted": True}
        if command in {"delete_clip", "delete_arrangement_clip"}:
            view = "session" if command == "delete_clip" else "arrangement"
            index = params.get("clip_index", params.get("arrangement_clip_index"))
            for track in self.state["tracks"]:
                track["clips"] = [
                    clip
                    for clip in track["clips"]
                    if not (clip["view"] == view and clip["locator"]["clip_index"] == index)
                ]
            return {"deleted": True}
        raise AssertionError("unexpected command " + command)

    def commands(self):
        return [command for command, _ in self.calls]

    def params(self, command):
        return [params for kind, params in self.calls if kind == command]


def adapter(bridge):
    return LiveAdapter(bridge, capture(), refresh=lambda: deepcopy(bridge.state))


class LiveAdapterTests(unittest.TestCase):
    def test_track_write_keeps_identity_guards(self):
        bridge = FakeBridge()
        adapter(bridge).apply(
            {"kind": "set_track", "target": "track:0", "patch": {"name": "bass_Sub"}}
        )
        params = bridge.params("write_access_object")[0]
        self.assertEqual(params["object_type"], "track")
        self.assertEqual(params["expected_track_name"], "Bass")
        self.assertEqual(params["properties"], {"name": "bass_Sub"})

    def test_clip_write_reuses_captured_locator(self):
        bridge = FakeBridge()
        adapter(bridge).apply(
            {"kind": "set_clip", "target": "track:0:session:0", "patch": {"color_index": 12}}
        )
        params = bridge.params("write_access_object")[0]
        self.assertEqual(params["expected_clip_name"], "Phrase")
        self.assertEqual(params["clip_index"], 0)
        self.assertEqual(params["properties"], {"color_index": 12})

    def test_session_write_maps_names(self):
        bridge = FakeBridge()
        adapter(bridge).apply(
            {"kind": "set_session", "target": "session", "patch": {"tempo": 150, "numerator": 3}}
        )
        params = bridge.params("write_access_object")[0]
        self.assertEqual(params["object_type"], "song")
        self.assertEqual(params["properties"], {"tempo": 150, "signature_numerator": 3})

    def test_replace_midi_modifies_and_deletes_by_id(self):
        bridge = FakeBridge()
        planned = [dict(notes()[1], start_time=0.0), dict(notes()[2], mute=True)]
        planned[1]["note_id"] = 2
        adapter(bridge).apply(
            {"kind": "replace_midi", "target": "track:0:session:0", "patch": {"notes": planned}}
        )
        self.assertEqual(bridge.commands().count("delete_access_notes"), 0)
        modifies = bridge.params("modify_access_notes")[0]["notes"]
        self.assertEqual({row["note_id"] for row in modifies}, {1, 2})
        self.assertEqual(bridge.notes[1]["start_time"], 0.0)

    def test_replace_midi_deletes_notes_missing_from_plan(self):
        bridge = FakeBridge()
        adapter(bridge).apply(
            {
                "kind": "replace_midi",
                "target": "track:0:session:0",
                "patch": {"notes": [dict(notes()[1])]},
            }
        )
        deleted = bridge.params("delete_access_notes")[0]["notes"]
        self.assertEqual(deleted, [{"note_id": 2}])
        self.assertNotIn(2, bridge.notes)

    def test_replace_midi_refuses_stale_or_id_less_notes(self):
        bridge = FakeBridge()
        stale = [dict(notes()[1], note_id=99)]
        with self.assertRaisesRegex(ValueError, "recapture"):
            adapter(bridge).apply(
                {"kind": "replace_midi", "target": "track:0:session:0", "patch": {"notes": stale}}
            )
        incomplete = [{"pitch": 40, "start_time": 0.0}]
        with self.assertRaisesRegex(ValueError, "Insert requires"):
            adapter(bridge).apply(
                {
                    "kind": "replace_midi",
                    "target": "track:0:session:0",
                    "patch": {"notes": incomplete},
                }
            )
        self.assertEqual(bridge.notes, notes())

    def test_verification_failure_is_loud(self):
        bridge = FakeBridge(ignore={"modify_access_notes"})
        planned = [dict(notes()[1], start_time=0.0), dict(notes()[2])]
        with self.assertRaisesRegex(RuntimeError, "did not match"):
            adapter(bridge).apply(
                {
                    "kind": "replace_midi",
                    "target": "track:0:session:0",
                    "patch": {"notes": planned},
                }
            )

    def test_grouping_is_the_only_platform_limit(self):
        bridge = FakeBridge()
        live = adapter(bridge)
        change = {"kind": "group_tracks", "target": ["track:0"], "patch": {"name": "X"}}
        self.assertFalse(live.supports(change))
        self.assertIn("group", live.reason(change))
        with self.assertRaisesRegex(UnsupportedOperations, "group"):
            live.apply(change)
        with self.assertRaises(UnsupportedOperations):
            live.apply({"kind": "set_track", "target": "track:0", "patch": {"loop": True}})
        with self.assertRaises(UnsupportedOperations):
            live.apply({"kind": "set_session", "target": "session", "patch": {"key": "Fm"}})
        self.assertEqual(bridge.calls, [])

    def test_unknown_targets_refused(self):
        with self.assertRaises(ValueError):
            adapter(FakeBridge()).apply(
                {"kind": "set_track", "target": "track:9", "patch": {"name": "x"}}
            )

    def test_delete_track_uses_name_guard(self):
        bridge = FakeBridge()
        adapter(bridge).apply({"kind": "delete_track", "target": "track:1", "patch": {}})
        params = bridge.params("delete_track")[0]
        self.assertEqual(params["track_index"], 1)
        self.assertEqual(params["expected_track_name"], "Empty")

    def test_delete_clip_routes_by_view(self):
        session = FakeBridge()
        adapter(session).apply({"kind": "delete_clip", "target": "track:0:session:0", "patch": {}})
        self.assertEqual(session.commands().count("delete_clip"), 1)
        self.assertEqual(session.commands().count("delete_arrangement_clip"), 0)
        arrangement = FakeBridge()
        adapter(arrangement).apply(
            {"kind": "delete_clip", "target": "track:0:arrangement:0", "patch": {}}
        )
        params = arrangement.params("delete_arrangement_clip")[0]
        self.assertEqual(params["expected_start_time"], 8.0)
        self.assertEqual(params["expected_clip_name"], "Verse")

    def test_resize_clip_writes_session_length_and_reports_arrangement(self):
        bridge = FakeBridge()
        adapter(bridge).apply(
            {"kind": "resize_clip", "target": "track:0:session:0", "patch": {"end_beats": 8}}
        )
        params = bridge.params("write_access_object")[0]
        self.assertEqual(params["properties"], {"loop_end": 8.0})
        with self.assertRaisesRegex(UnsupportedOperations, "arrangement|Arrangement"):
            adapter(FakeBridge()).apply(
                {
                    "kind": "resize_clip",
                    "target": "track:0:arrangement:0",
                    "patch": {"end_beats": 8},
                }
            )

    def test_set_warp_uses_guarded_command_and_checks_audio(self):
        bridge = FakeBridge()
        adapter(bridge).apply(
            {"kind": "set_warp", "target": "track:2:session:0", "patch": {"warp_mode": 2}}
        )
        params = bridge.params("set_access_warp")[0]
        self.assertEqual(params["properties"], {"warp_mode": 2})
        self.assertEqual(params["expected_clip_name"], "Take")
        with self.assertRaisesRegex(ValueError, "audio"):
            adapter(FakeBridge()).apply(
                {"kind": "set_warp", "target": "track:0:session:0", "patch": {"warping": True}}
            )

    def test_replace_midi_inserts_notes_without_ids(self):
        bridge = FakeBridge()
        planned = [
            dict(notes()[1]),
            dict(notes()[2]),
            {"pitch": 50, "start_time": 3.0, "duration": 0.5, "velocity": 100.0},
        ]
        adapter(bridge).apply(
            {"kind": "replace_midi", "target": "track:0:session:0", "patch": {"notes": planned}}
        )
        inserted = bridge.params("insert_access_notes")[0]["notes"]
        self.assertEqual(inserted[0]["pitch"], 50)
        self.assertEqual(len(bridge.notes), 3)

    def test_widened_track_and_clip_properties(self):
        bridge = FakeBridge()
        live = adapter(bridge)
        live.apply({"kind": "set_track", "target": "track:0", "patch": {"mute": True, "arm": True}})
        live.apply({"kind": "set_clip", "target": "track:0:session:0", "patch": {"looping": False}})
        written = [params["properties"] for params in bridge.params("write_access_object")]
        self.assertEqual(written[0], {"mute": True, "arm": True})
        self.assertEqual(written[1], {"looping": False})
        self.assertEqual(
            set(live.supports({"kind": kind}) and kind for kind in ("delete_track",)),
            {"delete_track"},
        )

    def test_set_clip_routes_warp_mode_to_warp_writer(self):
        bridge = FakeBridge()
        live = adapter(bridge)
        live.apply(
            {
                "kind": "set_clip",
                "target": "track:2:session:0",
                "patch": {"warp_mode": 2, "gain": 0.5},
            }
        )
        self.assertEqual(bridge.params("set_access_warp")[0]["properties"], {"warp_mode": 2})
        self.assertEqual(bridge.params("write_access_object")[0]["properties"], {"gain": 0.5})
        with self.assertRaisesRegex(ValueError, "audio"):
            live.apply(
                {"kind": "set_clip", "target": "track:0:session:0", "patch": {"warp_mode": 2}}
            )

    def test_track_monitoring_state_is_writable(self):
        bridge = FakeBridge()
        adapter(bridge).apply(
            {"kind": "set_track", "target": "track:0", "patch": {"current_monitoring_state": 2}}
        )
        self.assertEqual(
            bridge.params("write_access_object")[0]["properties"],
            {"current_monitoring_state": 2},
        )


class RefreshTests(unittest.TestCase):
    """A refresh must capture Session clips, or later Session edits cannot resolve."""

    def test_refresh_captures_session_clips(self):
        calls = []

        def fake_collect(connection, include_session=False, track_indices=None):
            calls.append(include_session)
            return capture()

        with mock.patch("enableton.song_lint.collect_live", fake_collect):
            adapter = LiveAdapter(FakeBridge(), capture())
            adapter.apply({"kind": "set_track", "target": "track:0", "patch": {"name": "bass_Sub"}})
        self.assertEqual(calls, [True])


if __name__ == "__main__":
    unittest.main()
