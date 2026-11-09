"""Warp-mode alignment. Markers, starts, and the mix are not written."""

import unittest

from enableton.align_tracks import (
    BEATS,
    COMPLEX,
    COMPLEX_PRO,
    REPITCH,
    TONES,
    apply_plan,
    plan_alignment,
)


def audio(index, name, mode, warping=True, available=None):
    clip = {
        "name": name,
        "type": "audio",
        "view": "arrangement",
        "index": 0,
        "start_beats": 4.0,
        "warping": warping,
        "warp_mode": mode,
    }
    if available is not None:
        clip["available_warp_modes"] = available
    return {"index": index, "name": name, "type": "audio", "clips": [clip]}


class PlanTests(unittest.TestCase):
    def test_roles_pick_beats_tones_or_complex_pro(self):
        plan = plan_alignment(
            [
                audio(0, "2-Drums", COMPLEX),
                audio(1, "Sub Bass", COMPLEX),
                audio(2, "7-Vocals", BEATS),
                audio(3, "ORIGINAL | 2-Drums", COMPLEX),
                {"index": 4, "name": "Print", "type": "midi", "clips": []},
            ]
        )
        chosen = [
            (row["track_name"], row["warp_mode"], row["warp_mode_name"]) for row in plan["actions"]
        ]
        self.assertEqual(
            chosen,
            [
                ("2-Drums", BEATS, "Beats"),
                ("Sub Bass", TONES, "Tones"),
                ("7-Vocals", COMPLEX_PRO, "Complex Pro"),
            ],
        )
        self.assertIn("Markers", plan["actions"][0]["message"])
        self.assertTrue(any(row["reason"] == "already an original" for row in plan["skipped"]))
        self.assertTrue(any(row["reason"] == "not an audio track" for row in plan["skipped"]))
        joined = " ".join(item["reason"] for item in plan["not_automated"])
        self.assertIn("polarity", joined)
        self.assertIn("EQ", joined)
        self.assertIn("group", joined)
        self.assertNotIn("limiter", " ".join(plan["writes"]))

    def test_repitch_and_unwarped_clips_stay(self):
        plan = plan_alignment(
            [
                audio(0, "Drums", REPITCH),
                audio(1, "Vocals", BEATS, warping=False),
                audio(2, "Loop", BEATS, available=[BEATS, TONES, COMPLEX]),
            ]
        )
        self.assertEqual([row["warp_mode_name"] for row in plan["actions"]], ["Complex"])
        self.assertIn("Complex Pro is not available", plan["actions"][0]["message"])
        codes = [row["code"] for row in plan["reports"]]
        self.assertEqual(codes, ["repitch", "warp_off"])

    def test_an_existing_mode_is_not_an_action(self):
        plan = plan_alignment([audio(0, "Drums", BEATS)])
        self.assertEqual(plan["actions"], [])
        self.assertEqual(plan["reports"][0]["code"], "warp_mode_ready")


class FakeLive:
    def __init__(self):
        self.playing = False
        self.calls = []
        self.mode = {0: COMPLEX}
        self.available = {0: [BEATS, TONES, REPITCH, COMPLEX, COMPLEX_PRO]}
        self.warping = {0: True}
        self.tracks = {0: {"name": "Drums"}}

    def __call__(self, command, params):
        self.calls.append(command)
        if command == "get_session_info":
            return {"is_playing": self.playing, "record_mode": False}
        if command == "get_track_info":
            return dict(self.tracks[params["track_index"]])
        if command == "get_audio_clip_timing":
            self._guard(params)
            index = params["track_index"]
            return {
                "warping": self.warping[index],
                "warp_mode": self.mode[index],
                "available_warp_modes": list(self.available[index]),
            }
        if command == "set_access_warp":
            self._guard(params)
            if set(params["properties"]) != {"warp_mode"}:
                raise AssertionError("unexpected warp write")
            mode = params["properties"]["warp_mode"]
            if mode not in self.available[params["track_index"]]:
                raise RuntimeError("mode unavailable")
            self.mode[params["track_index"]] = mode
            return {"verified": True}
        raise AssertionError(command)

    def _guard(self, params):
        if params["expected_track_name"] != self.tracks[params["track_index"]]["name"]:
            raise AssertionError("track guard")
        if params["expected_clip_name"] != "Drums":
            raise AssertionError("clip guard")
        if params["expected_start_time"] != 4.0:
            raise AssertionError("start guard")


class ApplyTests(unittest.TestCase):
    def plan(self):
        return plan_alignment([audio(0, "Drums", COMPLEX)])

    def test_confirm_and_playback_block_writes(self):
        live = FakeLive()
        preview = apply_plan(live, self.plan(), confirm=False)
        self.assertFalse(preview["live_changes"])
        live.playing = True
        with self.assertRaisesRegex(ValueError, "playback"):
            apply_plan(live, self.plan(), confirm=True)
        self.assertNotIn("set_access_warp", live.calls)

    def test_one_mode_is_written_and_then_left(self):
        live = FakeLive()
        plan = self.plan()
        result = apply_plan(live, plan, confirm=True)
        self.assertEqual(live.mode[0], BEATS)
        self.assertEqual(result["results"][0]["status"], "set_warp_mode")
        self.assertTrue(result["results"][0]["verified"])
        self.assertTrue(result["live_changes"])
        self.assertFalse(result["playback_started"])
        again = apply_plan(live, plan, confirm=True)
        self.assertEqual(again["results"][0]["status"], "ready")
        self.assertFalse(again["results"][0]["wrote"])
        self.assertFalse(again["live_changes"])
        self.assertEqual(live.calls.count("set_access_warp"), 1)

    def test_complex_pro_falls_back_when_the_clip_lacks_it(self):
        live = FakeLive()
        live.tracks[2] = {"name": "Vocals"}
        live.mode[2] = BEATS
        live.available[2] = [BEATS, TONES, COMPLEX]
        live.warping[2] = True
        plan = plan_alignment([audio(2, "Vocals", BEATS)])
        self.assertEqual(plan["actions"][0]["warp_mode"], COMPLEX_PRO)

        def send(command, params):
            if command == "get_audio_clip_timing" and params["expected_clip_name"] != "Vocals":
                raise AssertionError("clip guard")
            if command == "set_access_warp":
                if params["expected_clip_name"] != "Vocals":
                    raise AssertionError("clip guard")
                mode = params["properties"]["warp_mode"]
                if mode not in live.available[2]:
                    raise RuntimeError("mode unavailable")
                live.mode[2] = mode
                return {"verified": True}
            if command == "get_track_info":
                return {"name": "Vocals"}
            if command == "get_session_info":
                return {"is_playing": False, "record_mode": False}
            if command == "get_audio_clip_timing":
                return {
                    "warping": True,
                    "warp_mode": live.mode[2],
                    "available_warp_modes": list(live.available[2]),
                }
            raise AssertionError(command)

        result = apply_plan(send, plan, confirm=True)
        self.assertEqual(live.mode[2], COMPLEX)
        self.assertIn("Complex is used", result["results"][0]["reason"])
        self.assertTrue(result["results"][0]["verified"])


if __name__ == "__main__":
    unittest.main()
