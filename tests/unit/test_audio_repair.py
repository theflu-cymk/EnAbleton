"""Measured clip-gain, Utility DC, and gentle Compressor repairs."""

import unittest

from enableton.audio_repair import (
    GAIN_STEP,
    UNITY_GAIN,
    apply_plan,
    compressor_settings,
    compressor_values,
    dc_decision,
    gain_decision,
    plan_repairs,
)


def scan(*codes):
    return {
        "finding_counts": {code: 1 for code in codes},
        "findings": [{"code": code, "start_seconds": 1.25} for code in codes],
        "coverage": {
            "start_seconds": 0,
            "end_seconds": 30,
            "partial": True,
            "timestamps": "source-file seconds, not Arrangement or warped playback time",
        },
    }


def measured(counts, channels=None, start=1.25):
    payload = {
        "finding_counts": dict(counts),
        "findings": [
            {"code": code, "start_seconds": start} for code, count in counts.items() if count
        ],
        "coverage": {
            "start_seconds": 0,
            "end_seconds": 30,
            "partial": True,
            "timestamps": "source-file seconds, not Arrangement or warped playback time",
        },
    }
    if channels is not None:
        payload["channels"] = channels
    return payload


def audio(index, name, codes=(), devices=None, **clip_extra):
    clip = {
        "name": name,
        "type": "audio",
        "view": "arrangement",
        "index": 0,
        "start_beats": 4.0,
        "scan": scan(*codes),
    }
    clip.update(clip_extra)
    return {
        "index": index,
        "name": name,
        "type": "audio",
        "devices": devices or [],
        "clips": [clip],
    }


class DecisionTests(unittest.TestCase):
    def test_unity_gain_steps_once_and_then_stops(self):
        decision = gain_decision(UNITY_GAIN)
        self.assertTrue(decision["write"])
        self.assertAlmostEqual(decision["gain"], round(UNITY_GAIN * GAIN_STEP, 6))
        self.assertIn("does not restore", decision["reason"])
        self.assertFalse(gain_decision(decision["gain"])["write"])
        self.assertFalse(gain_decision(0.1)["write"])
        self.assertEqual(gain_decision(0.7)["status"], "review")
        self.assertFalse(gain_decision(0.7)["write"])

    def test_dc_is_set_only_for_one_unambiguous_switch(self):
        off = {
            "name": "DC",
            "is_quantized": True,
            "value": 0,
            "min": 0,
            "max": 1,
            "value_items": ["Off", "On"],
            "automation_state": 0,
        }
        decision = dc_decision([off, {"name": "Gain", "is_quantized": False, "value": 1}])
        self.assertEqual((decision["write"], decision["name"], decision["value"]), (True, "DC", 1))
        on = dict(off, value=1)
        self.assertFalse(dc_decision([on])["write"])
        self.assertEqual(dc_decision([on])["status"], "ready")
        self.assertFalse(dc_decision([{"name": "Gain", "is_quantized": False}])["write"])
        self.assertFalse(
            dc_decision(
                [
                    {"name": "DC", "is_quantized": True, "value": 0, "value_items": ["Off", "On"]},
                    {
                        "name": "DC Filter",
                        "is_quantized": True,
                        "value": 0,
                        "value_items": ["Off", "On"],
                    },
                ]
            )["write"]
        )
        self.assertFalse(
            dc_decision([{"name": "DC", "is_quantized": False, "value": 0, "min": 0, "max": 1}])[
                "write"
            ]
        )


class PlanTests(unittest.TestCase):
    def test_only_full_scale_and_dc_become_actions(self):
        plan = plan_repairs(
            [
                audio(0, "Vox", ("near_full_scale", "level_jump", "discontinuity", "silence_gap")),
                audio(1, "Sub", ("dc_offset",)),
                audio(2, "ORIGINAL | Vox", ("near_full_scale",)),
                {
                    "index": 3,
                    "name": "Print",
                    "type": "midi",
                    "clips": [],
                },
                audio(4, "Broken", scan_error="Only integer PCM WAV is supported"),
            ]
        )
        kinds = [(row["status"], row["track_name"]) for row in plan["actions"]]
        self.assertEqual(kinds, [("lower_gain", "Vox"), ("dc_filter", "Sub")])
        self.assertEqual(
            [row["code"] for row in plan["reports"]],
            ["level_jump", "discontinuity", "silence_gap"],
        )
        self.assertIn("compressor", plan["reports"][0]["message"])
        self.assertIn("fade", plan["reports"][1]["message"])
        self.assertIn("source-file seconds", plan["window"])
        self.assertTrue(plan["actions"][0]["window"]["partial"])
        self.assertIn("Session clips", plan["session_clips"])
        self.assertFalse(plan["live_changes"])
        reasons = [row["reason"] for row in plan["skipped"]]
        self.assertTrue(any("original" in reason for reason in reasons))
        self.assertTrue(any("PCM" in reason for reason in reasons))
        self.assertNotIn("limiter", " ".join(plan["writes"]))

    def test_repeated_level_jumps_plan_one_gentle_compressor(self):
        loud = audio(1, "Drums", scan=measured({"level_jump": 6}, channels=[{"rms_dbfs": -20.0}]))
        quiet = audio(1, "Drums", scan=measured({"level_jump": 2, "silence_gap": 1}))
        loud["clips"].append(quiet["clips"][0])
        dense = audio(2, "Hat", scan=measured({"level_jump": 2, "discontinuity": 25}))
        plan = plan_repairs([loud, dense])
        compressors = [row for row in plan["actions"] if row["status"] == "level_compressor"]
        self.assertEqual(len(compressors), 1)
        chosen = compressors[0]
        self.assertEqual(chosen["track_name"], "Drums")
        self.assertEqual(chosen["jump_count"], 6)
        self.assertEqual(chosen["threshold_db"], -18.0)
        self.assertEqual(chosen["ratio"], 2.0)
        self.assertEqual(
            (chosen["attack_ms"], chosen["release_ms"], chosen["knee_db"]), (20.0, 200.0, 10.0)
        )
        self.assertIn("Makeup stays off", chosen["message"])
        codes = [(row["track_name"], row["code"]) for row in plan["reports"]]
        self.assertNotIn(("Drums", "level_jump"), codes)
        self.assertIn(("Hat", "level_jump"), codes)
        self.assertIn(("Drums", "silence_gap"), codes)
        hat_clicks = next(row for row in plan["reports"] if row["code"] == "discontinuity")
        self.assertIn("percussion", hat_clicks["message"])
        self.assertIn("Compressor", " ".join(plan["writes"]))
        self.assertNotIn("limiter", " ".join(plan["writes"]))

    def test_threshold_follows_rms_inside_a_fixed_window(self):
        hot = compressor_settings(measured({"level_jump": 3}, channels=[{"rms_dbfs": -4}]))
        cold = compressor_settings(
            measured({"level_jump": 4}, channels=[{"rms_dbfs": -40}, {"rms_dbfs": True}])
        )
        missing = compressor_settings(measured({"level_jump": 3}))
        self.assertEqual(hot["threshold_db"], -8.0)
        self.assertEqual(cold["threshold_db"], -24.0)
        self.assertEqual(missing["threshold_db"], -18.0)
        self.assertIn("missing", missing["basis"])
        self.assertIsNone(compressor_settings(measured({"level_jump": 2})))

    def test_two_to_one_is_native_one_half(self):
        values = compressor_values(
            {
                "threshold_db": -18,
                "ratio": 2,
                "attack_ms": 20,
                "release_ms": 200,
                "knee_db": 10,
            }
        )
        self.assertEqual(values["Ratio"], 0.5)
        self.assertEqual(values["Knee"], 10.0)
        self.assertEqual(values["Attack"], 0.660206)
        self.assertGreater(values["Release"], 0.25)
        self.assertLess(values["Release"], 0.375)
        self.assertGreater(values["Threshold"], 0.375)
        self.assertLess(values["Threshold"], 0.5)


class FakeLive:
    def __init__(self):
        self.tracks = {
            0: {"name": "Vox", "devices": []},
            1: {"name": "Sub", "devices": []},
        }
        self.gain = {0: UNITY_GAIN}
        self.playing = False
        self.loads = []
        self.writes = []
        self.parameters = []
        self.dc_value = 0
        self.compressor_available = True
        self.compressor_values = {}
        self.compressor_displays = {
            "Threshold": "-18.0 dB",
            "Ratio": "2.00 : 1",
            "Attack": "20.0 ms",
            "Release": "200 ms",
            "Knee": "10.0 dB",
        }
        self.compressor_rows_override = None
        self.refine_hits = {}
        self.dc_parameters = [
            {
                "name": "DC",
                "is_quantized": True,
                "value": 0,
                "min": 0,
                "max": 1,
                "value_items": ["Off", "On"],
                "automation_state": 0,
            }
        ]
        self.utility_available = True

    def __call__(self, command, params):
        if command == "get_session_info":
            return {"is_playing": self.playing, "record_mode": False}
        if command == "get_track_info":
            row = self.tracks[params["track_index"]]
            return {"name": row["name"], "devices": [dict(device) for device in row["devices"]]}
        if command == "read_access_object":
            self._guard(params)
            return {"properties": {"gain": self.gain[params["track_index"]]}, "unavailable": []}
        if command == "write_access_object":
            self._guard(params)
            self.writes.append(dict(params["properties"]))
            self.gain[params["track_index"]] = params["properties"]["gain"]
            return {"verified": True, "properties": dict(params["properties"])}
        if command == "get_browser_items_at_path":
            if params["path"] != "audio_effects":
                return {"items": []}
            items = []
            if self.utility_available:
                items.append({"name": "Utility", "uri": "live://utility", "is_loadable": True})
            if self.compressor_available:
                items.append(
                    {
                        "name": "Compressor",
                        "uri": "query:AudioFx#Compressor",
                        "is_loadable": True,
                    }
                )
            return {"items": items}
        if command == "load_browser_item":
            self.loads.append(params["item_uri"])
            devices = self.tracks[params["track_index"]]["devices"]
            if "compressor" in params["item_uri"].casefold():
                loaded = {"index": len(devices), "name": "Compressor", "class_name": "Compressor2"}
            else:
                loaded = {"index": len(devices), "name": "Utility", "class_name": "StereoGain"}
            devices.append(loaded)
            return {"loaded": True}
        if command == "get_sound_design_parameters":
            if params["expected_track_name"] != self.tracks[params["track_index"]]["name"]:
                raise AssertionError("track guard")
            if params["expected_device_name"] == "Compressor":
                if self.compressor_rows_override is not None:
                    return {
                        "device_name": "Compressor",
                        "parameters": [dict(row) for row in self.compressor_rows_override],
                    }
                rows = []
                for name in ("Threshold", "Ratio", "Attack", "Release", "Knee"):
                    rows.append(
                        {
                            "name": name,
                            "value": self.compressor_values.get(name, 0),
                            "display_value": self.compressor_displays.get(name, "0"),
                            "automation_state": 0,
                            "is_quantized": False,
                        }
                    )
                return {"device_name": "Compressor", "parameters": rows}
            if params["expected_device_name"] != "Utility":
                raise AssertionError("device guard")
            rows = [dict(row) for row in self.dc_parameters]
            for row in rows:
                if row["name"] == "DC":
                    row["value"] = self.dc_value
            return {"device_name": "Utility", "parameters": rows}
        if command == "set_sound_design_parameters":
            written = dict(params["parameters"])
            self.parameters.append(written)
            if "DC" in written:
                self.dc_value = written["DC"]
                return {"verified": True, "device_name": "Utility"}
            self.compressor_values.update(written)
            if len(written) == 1:
                name = next(iter(written))
                if name in self.refine_hits:
                    self.compressor_displays[name] = self.refine_hits[name]
            return {"verified": True, "device_name": "Compressor"}
        raise AssertionError(command)

    def _guard(self, params):
        row = self.tracks[params["track_index"]]
        if params["expected_track_name"] != row["name"]:
            raise AssertionError("track guard")
        if params["expected_clip_name"] != row["name"]:
            raise AssertionError("clip guard")
        if params["expected_start_time"] != 4.0:
            raise AssertionError("start guard")
        if set(params.get("properties", {})) - {"gain"}:
            raise AssertionError("unexpected clip property")


class ApplyTests(unittest.TestCase):
    def plan(self):
        return plan_repairs(
            [
                audio(0, "Vox", ("near_full_scale", "level_jump")),
                audio(1, "Sub", ("dc_offset",)),
            ]
        )

    def test_confirm_and_playback_block_writes(self):
        live = FakeLive()
        plan = self.plan()
        preview = apply_plan(live, plan, confirm=False)
        self.assertFalse(preview["live_changes"])
        live.playing = True
        with self.assertRaisesRegex(ValueError, "playback"):
            apply_plan(live, plan, confirm=True)
        self.assertEqual(live.writes, [])
        self.assertEqual(live.loads, [])

    def test_gain_and_dc_are_written_once(self):
        live = FakeLive()
        plan = self.plan()
        result = apply_plan(live, plan, confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.writes, [{"gain": round(UNITY_GAIN * GAIN_STEP, 6)}])
        self.assertEqual(live.loads, ["live://utility"])
        self.assertEqual(live.parameters, [{"DC": 1}])
        self.assertTrue(result["live_changes"])
        self.assertFalse(result["playback_started"])
        self.assertEqual(result["reports"][0]["code"], "level_jump")
        again = apply_plan(live, plan, confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.writes, [{"gain": round(UNITY_GAIN * GAIN_STEP, 6)}])
        self.assertEqual(live.loads, ["live://utility"])
        self.assertEqual(live.parameters, [{"DC": 1}])
        self.assertFalse(again["live_changes"])

    def test_a_boosted_clip_and_a_missing_dc_parameter_are_not_guessed(self):
        live = FakeLive()
        live.gain[0] = 0.7
        live.dc_parameters = [{"name": "Gain", "is_quantized": False, "value": 0.5}]
        result = apply_plan(live, self.plan(), confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.writes, [])
        self.assertEqual(live.parameters, [])
        self.assertEqual(result["results"][0]["status"], "review")
        self.assertTrue(result["results"][1]["utility_loaded"])
        self.assertFalse(result["results"][1]["wrote"])
        self.assertIn("does not expose", result["results"][1]["reason"])

    def test_an_existing_utility_is_not_loaded_again(self):
        live = FakeLive()
        live.tracks[1]["devices"] = [{"index": 2, "name": "Utility", "class_name": "StereoGain"}]
        live.dc_value = 1
        plan = plan_repairs(
            [audio(1, "Sub", ("dc_offset",), devices=[{"name": "Utility", "index": 2}])]
        )
        result = apply_plan(live, plan, confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.loads, [])
        self.assertEqual(live.parameters, [])
        self.assertEqual(result["results"][0]["status"], "ready")
        self.assertFalse(result["live_changes"])

    def test_repeated_jumps_load_one_compressor_and_then_stop(self):
        live = FakeLive()
        live.tracks[4] = {"name": "Drums", "devices": []}
        plan = plan_repairs(
            [audio(4, "Drums", scan=measured({"level_jump": 6}, channels=[{"rms_dbfs": -20.0}]))]
        )
        result = apply_plan(live, plan, confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.loads, ["query:AudioFx#Compressor"])
        written = live.parameters[0]
        self.assertEqual(written["Ratio"], 0.5)
        self.assertEqual(written["Knee"], 10.0)
        self.assertEqual(written["Attack"], 0.660206)
        self.assertTrue(
            all(0 <= written[name] <= 1 for name in ("Threshold", "Ratio", "Attack", "Release"))
        )
        self.assertNotIn("Makeup", written)
        self.assertNotIn("Output Gain", written)
        self.assertEqual(result["results"][0]["status"], "level_compressor")
        self.assertTrue(result["results"][0]["verified"])
        self.assertTrue(result["live_changes"])
        again = apply_plan(live, plan, confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.loads, ["query:AudioFx#Compressor"])
        self.assertEqual(len(live.parameters), 1)
        self.assertEqual(again["results"][0]["status"], "ready")
        self.assertIn("left unchanged", again["results"][0]["reason"])
        self.assertFalse(again["live_changes"])

    def test_an_existing_glue_compressor_is_not_replaced(self):
        live = FakeLive()
        present = [{"index": 0, "name": "Glue Compressor", "class_name": "GlueCompressor"}]
        live.tracks[4] = {"name": "Drums", "devices": [dict(present[0])]}
        plan = plan_repairs([audio(4, "Drums", devices=present, scan=measured({"level_jump": 8}))])
        result = apply_plan(live, plan, confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.loads, [])
        self.assertEqual(live.parameters, [])
        self.assertEqual(result["results"][0]["status"], "ready")
        self.assertFalse(result["live_changes"])

    def test_a_wrong_ratio_display_is_refined_inside_the_native_range(self):
        live = FakeLive()
        live.tracks[4] = {"name": "Drums", "devices": []}
        live.compressor_displays["Ratio"] = "4.00 : 1"
        live.refine_hits["Ratio"] = "2.00 : 1"
        plan = plan_repairs([audio(4, "Drums", scan=measured({"level_jump": 3}))])
        result = apply_plan(live, plan, confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.parameters[0]["Ratio"], 0.5)
        refined = live.parameters[1]
        self.assertEqual(set(refined), {"Ratio"})
        self.assertGreater(refined["Ratio"], 0)
        self.assertLess(refined["Ratio"], 0.5)
        self.assertEqual(result["results"][0]["status"], "level_compressor")
        self.assertTrue(result["results"][0]["verified"])

    def test_a_missing_compressor_control_is_left_unset(self):
        live = FakeLive()
        live.tracks[4] = {"name": "Drums", "devices": []}
        live.compressor_rows_override = [
            {"name": "Gain", "automation_state": 0, "display_value": "0 dB", "value": 0}
        ]
        plan = plan_repairs([audio(4, "Drums", scan=measured({"level_jump": 3}))])
        result = apply_plan(live, plan, confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.loads, ["query:AudioFx#Compressor"])
        self.assertEqual(live.parameters, [])
        row = result["results"][0]
        self.assertEqual(row["status"], "unavailable")
        self.assertTrue(row["compressor_loaded"])
        self.assertFalse(row["wrote"])
        self.assertIn("Undo", row["reason"])
        self.assertTrue(result["live_changes"])

    def test_a_missing_browser_compressor_loads_nothing(self):
        live = FakeLive()
        live.tracks[4] = {"name": "Drums", "devices": []}
        live.compressor_available = False
        plan = plan_repairs([audio(4, "Drums", scan=measured({"level_jump": 5}))])
        result = apply_plan(live, plan, confirm=True, sleeper=lambda _seconds: None)
        self.assertEqual(live.loads, [])
        self.assertEqual(result["results"][0]["status"], "unavailable")
        self.assertFalse(result["results"][0]["compressor_loaded"])
        self.assertFalse(result["live_changes"])


if __name__ == "__main__":
    unittest.main()
