"""Fake-Live coverage for the nine preparation operations."""

import contextlib
import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from enableton import cli
from enableton.prep import OPS, resolve, run, run_all


def session(tempo=120):
    return {
        "tempo": tempo,
        "numerator": 4,
        "denominator": 4,
        "is_playing": False,
        "recording": False,
    }


def state(tracks, **extra):
    for index, track in enumerate(tracks):
        track["index"] = index
    body = {"session": session(), "tracks": tracks, "locators": [], "writes": []}
    body.update(extra)
    return body


def audio(name, **clip):
    base = {
        "index": 0,
        "name": "clip",
        "type": "audio",
        "view": "arrangement",
        "start": 0.0,
        "end": 8.0,
        "loop_start": 0.0,
        "loop_end": 8.0,
        "end_marker": 8.0,
        "warping": True,
        "warp_mode": 4,
        "gain": 0.4,
        "sample_frames": 100,
        "available_warp_modes": [0, 1, 2, 3, 4, 6],
    }
    base.update(clip)
    return {"index": 0, "name": name, "type": "audio", "clips": [base]}


def midi(name, pitch=36):
    return {
        "index": 0,
        "name": name,
        "type": "midi",
        "devices": [],
        "clips": [
            {
                "index": 0,
                "name": "take",
                "type": "midi",
                "view": "session",
                "loop_start": 0.0,
                "loop_end": 4.0,
                "end": 4.0,
                "notes": [{"pitch": pitch, "start_time": 0, "duration": 1, "velocity": 100}],
            }
        ],
    }


def names(body):
    return [track.get("name") for track in body["tracks"]]


class DispatchTests(unittest.TestCase):
    def test_number_and_align_alias_are_lock(self):
        self.assertEqual(resolve("6"), "lock")
        self.assertEqual(resolve("align"), "lock")
        self.assertEqual(resolve("a"), "adopt")

    def test_cli_number_and_alias_dispatch_lock(self):
        body = state([audio("Drums", sample_frames=20, warp_mode=0)])
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "set.json"
            path.write_text(json.dumps(body), encoding="utf-8")
            for argv in (["6", "--snapshot", str(path)], ["align", "--snapshot", str(path)]):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    code = cli.main(argv)
                payload = json.loads(out.getvalue())
                self.assertEqual(payload["op"], "lock")
                self.assertIn(code, (0, 1))


class IdempotentTests(unittest.TestCase):
    def cases(self):
        return {
            "adopt": state([audio("Bass", sample_frames=10)]),
            "name": state([audio("Bass", sample_frames=10)]),
            "label": state([audio("01 Bass", sample_frames=10)]),
            "voice": state([midi("Keys", pitch=60)]),
            "level": state([audio("Loop", full_scale=True, gain=0.4, sample_frames=10)]),
            "lock": state(
                [
                    audio("Drums", sample_frames=1000, warp_mode=0),
                    audio("Bass", sample_frames=10, warp_mode=4),
                ]
            ),
            "frame": state(
                [
                    audio(
                        "Loop",
                        warping=False,
                        end=1.1,
                        loop_end=1.1,
                        end_marker=1.1,
                        view="session",
                    )
                ]
            ),
            "map": state([audio("Drums", sample_frames=10)], energy=[{"time": 0, "level": 0.2}]),
            "check": state([audio("Audio", sample_frames=10)]),
        }

    def test_second_run_writes_nothing(self):
        for op_id, body in self.cases().items():
            with self.subTest(op=op_id):
                first = run(op_id, body, {})
                self.assertNotEqual(first["status"], "refused", first)
                marked = len(body["writes"])
                second = run(op_id, body, {})
                self.assertEqual(second["changed"], [], second)
                self.assertEqual(len(body["writes"]), marked)
                if op_id == "check":
                    self.assertNotEqual(second["status"], "refused", second)
                else:
                    self.assertEqual(second["status"], "unchanged", second)

    def test_plan_writes_nothing_and_reports_planned(self):
        for op in OPS:
            with self.subTest(op=op["id"]):
                body = self.cases()[op["id"]]
                before = deepcopy(body)
                result = run(op["id"], body, {"plan": True})
                self.assertEqual(result["status"], "planned", result)
                self.assertEqual(body["writes"], before["writes"])
                self.assertEqual(names(body), names(before))


class StandaloneTests(unittest.TestCase):
    def unnamed(self):
        return state(
            [
                midi("Track 1", pitch=60),
                audio("Audio", warping=True, warp_mode=4, gain=0.2, sample_frames=8),
            ]
        )

    def test_each_op_leaves_role_names_unwritten(self):
        for op in OPS:
            with self.subTest(op=op["id"]):
                body = self.unnamed()
                result = run(op["id"], body, {})
                self.assertNotIn(result["status"], {"refused", "error"}, result)
                for track in body["tracks"]:
                    self.assertNotRegex(track["name"], r"^\d\d\s+")

    def test_adopt_live_protects_a_copy_live_named_after_the_clip(self):
        tracks = [{"name": "13-Audio", "mute": False, "solo": False, "arm": False}]

        def dispatch(command, params=None):
            params = params or {}
            if command == "get_session_info":
                return {"track_count": len(tracks)}
            if command == "duplicate_track":
                tracks.insert(
                    1,
                    {
                        "name": "Ghosthack-DD_Drum Loop_Bully_120_Kick & Snare",
                        "mute": False,
                        "solo": False,
                        "arm": False,
                    },
                )
                return {"ok": True}
            if command == "get_track_info":
                return tracks[params["track_index"]]
            if command == "write_access_object":
                row = tracks[params["track_index"]]
                self.assertEqual(
                    params["expected_track_name"], "Ghosthack-DD_Drum Loop_Bully_120_Kick & Snare"
                )
                self.assertEqual(params["track_index"], 1)
                row.update(params["properties"])
                return {"ok": True}
            if command == "get_group_info":
                return {"is_foldable": False}
            raise AssertionError(command)

        from enableton.prep import _adopt_live

        _adopt_live(dispatch, 0, "13-Audio", "ORIGINAL | 13-Audio")
        self.assertEqual(tracks[0]["name"], "13-Audio")
        self.assertEqual(tracks[1]["name"], "ORIGINAL | 13-Audio")
        self.assertTrue(tracks[1]["mute"])
        self.assertFalse(tracks[1]["solo"])
        self.assertFalse(tracks[1]["arm"])
        self.assertEqual(tracks[1]["color_index"], 13)

    def test_adopt_skips_an_existing_original_sibling(self):
        body = state(
            [
                audio("Bass"),
                audio("ORIGINAL | Bass"),
            ]
        )
        result = run("adopt", body, {})
        self.assertEqual(len(body["tracks"]), 2)
        self.assertEqual(body["writes"], [])
        self.assertEqual(result["changed"], [])

    def _commands(self, body):
        batch = body["writes"][-1]
        self.assertEqual(batch["type"], "batch")
        return [command["params"] for command in batch["params"]["commands"]]

    def test_label_targets_the_clip_view(self):
        arranged = state([audio("01 Bass", start=2.0)])
        run("label", arranged, {})
        params = self._commands(arranged)[0]
        self.assertEqual(params["clip_view"], "arrangement")
        self.assertEqual(params["expected_start_time"], 2.0)
        self.assertEqual(params["expected_clip_name"], "clip")
        session_clip = state([midi("01 Keys", pitch=60)])
        run("label", session_clip, {})
        params = self._commands(session_clip)[0]
        self.assertEqual(params["clip_view"], "session")
        self.assertNotIn("expected_start_time", params)

    def test_lock_targets_arrangement_audio(self):
        body = state(
            [
                audio("Drums", sample_frames=1000, warp_mode=0, start=2.0),
                audio("Bass", sample_frames=10, warp_mode=4, start=1.944),
            ]
        )
        run("lock", body, {})
        params = self._commands(body)[0]
        self.assertEqual(params["clip_view"], "arrangement")
        self.assertEqual(params["expected_start_time"], 1.944)
        self.assertEqual(params["expected_track_name"], "Bass")
        self.assertEqual(params["properties"], {"warp_mode": 1})

    def test_lock_warp_off_without_a_render_is_unsupported(self):
        body = state(
            [
                audio("Drums", sample_frames=400, warp_mode=0),
                audio("Loop", sample_frames=12, warping=False, rendered=False),
            ]
        )
        result = run("lock", body, {})
        self.assertEqual(body["writes"], [])
        self.assertFalse(body["tracks"][1]["clips"][0]["warping"])
        self.assertEqual(
            result["unsupported"],
            [{"target": "track:1:clip:0", "reason": "needs reference and rendered replacement"}],
        )

    def test_frame_unwarped_clip_uses_seconds(self):
        body = state(
            [
                audio(
                    "Audio",
                    warping=False,
                    view="session",
                    end=1.1,
                    loop_start=0.0,
                    loop_end=1.1,
                    end_marker=1.1,
                )
            ]
        )
        result = run("frame", body, {})
        seconds = [row for row in result["changed"] if row.get("units") == "seconds"]
        self.assertTrue(seconds, result)
        self.assertTrue(all(row["to"] == 2.0 for row in seconds), seconds)
        self.assertNotIn(0, [row["to"] for row in seconds])
        self.assertNotIn(4, [row["to"] for row in seconds])
        self.assertEqual(body["tracks"][0]["clips"][0]["end"], 1.1)
        self.assertEqual(body["tracks"][0]["clips"][0]["loop_end"], 2.0)
        self.assertEqual(body["tracks"][0]["clips"][0]["end_marker"], 2.0)
        for params in self._commands(body):
            self.assertNotIn("end", params["properties"])
            self.assertEqual(params["properties"]["loop_end"], 2.0)

    def test_frame_does_not_snap_loop_end_onto_loop_start(self):
        body = state(
            [
                audio(
                    "Loop",
                    warping=True,
                    view="session",
                    loop_start=8.0,
                    loop_end=8.2,
                    end_marker=8.2,
                    end=8.2,
                )
            ]
        )
        run("frame", body, {})
        clip = body["tracks"][0]["clips"][0]
        self.assertEqual(clip["loop_start"], 8.0)
        self.assertGreater(clip["loop_end"], clip["loop_start"])
        self.assertGreaterEqual(clip["end_marker"], clip["loop_end"])
        params = self._commands(body)[0]
        self.assertGreater(params["properties"]["loop_end"], clip["loop_start"])
        self.assertNotIn("end", params["properties"])

    def test_label_skips_an_unnamed_clip(self):
        body = state([audio("01 Bass", sample_frames=10)])
        body["tracks"][0]["clips"].append(
            {
                "index": 1,
                "name": "",
                "type": "audio",
                "view": "arrangement",
                "start": 16.0,
                "end": 24.0,
                "loop_start": 0.0,
                "loop_end": 8.0,
                "warping": True,
            }
        )
        result = run("label", body, {})
        self.assertEqual(body["tracks"][0]["clips"][1]["name"], "")
        self.assertNotEqual(body["tracks"][0]["clips"][0]["name"], "clip")
        self.assertEqual(
            result["unsupported"],
            [{"target": "track:0:clip:1", "reason": "clip name is empty"}],
        )
        for params in self._commands(body):
            self.assertTrue(params["expected_clip_name"])

    def test_skip_name_still_targets_later_ops(self):
        body = state([midi("Bass", pitch=40), audio("Drums", sample_frames=80, warp_mode=4)])
        results = run_all(body, {"skip": ["name"]})
        self.assertNotIn("name", [row["op"] for row in results])
        self.assertEqual(body["tracks"][0]["name"], "Bass")
        label = next(row for row in results if row["op"] == "label")
        self.assertTrue(label["changed"], label)
        self.assertTrue(str(label["changed"][0]["to"]).startswith("01 "), label)

    def test_playing_refuses_a_write(self):
        body = state([audio("Bass")])
        body["session"]["is_playing"] = True
        result = run("name", body, {})
        self.assertEqual(result["status"], "refused")
        self.assertEqual(body["writes"], [])
        self.assertEqual(body["tracks"][0]["name"], "Bass")

    def test_map_without_create_locator_is_refused(self):
        body = state([audio("Drums")], capabilities=[], energy=[{"time": 0, "level": 0.4}])
        result = run("map", body, {})
        self.assertEqual(result["status"], "refused")
        self.assertEqual(body["locators"], [])
        self.assertEqual(body["writes"], [])


if __name__ == "__main__":
    unittest.main()
