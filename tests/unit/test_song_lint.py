from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

from enableton.cli import main
from enableton.song_lint import (
    collect_live,
    lint_state,
    run_lint,
    apply_metadata_fixes,
    write_report,
)


def fixture():
    return {
        "source": "snapshot",
        "session": {"tempo": 140, "numerator": 4, "denominator": 4},
        "tracks": [
            {
                "id": "t",
                "index": 0,
                "name": "1-MIDI",
                "type": "midi",
                "role": "bass",
                "devices": [],
                "clips": [
                    {
                        "id": "c",
                        "name": "Track 1",
                        "view": "arrangement",
                        "type": "midi",
                        "start_beats": 0,
                        "end_beats": 4,
                        "notes": [
                            {
                                "note_id": 1,
                                "pitch": 29,
                                "start_time": 0.1,
                                "duration": 1.5,
                                "velocity": 127,
                            },
                            {
                                "note_id": 2,
                                "pitch": 29,
                                "start_time": 1.0,
                                "duration": 0.5,
                                "velocity": 100,
                            },
                            {
                                "note_id": 3,
                                "pitch": 36,
                                "start_time": 0.1,
                                "duration": 1.5,
                                "velocity": 100,
                            },
                        ],
                    }
                ],
            }
        ],
    }


class FakeLive:
    def __init__(self):
        self.calls = []
        self.writes = []
        self.name = "1-MIDI"
        self.clip_name = "Track 1"
        self.clip_start = 0
        self.color = 0
        self.fail_notes = False
        self.frozen = False
        self.grouping_supported = True
        self.notes = deepcopy(fixture()["tracks"][0]["clips"][0]["notes"])

    def send_command(self, kind, params):
        self.calls.append((kind, deepcopy(params)))
        if kind == "batch":
            results = [
                {"result": self.send_command(c["type"], c["params"])} for c in params["commands"]
            ]
            return {"results": results, "executed": len(results)}
        if kind == "get_session_info":
            return {
                "tempo": 140,
                "signature_numerator": 4,
                "signature_denominator": 4,
                "track_count": 2,
                "is_playing": False,
                "record_mode": False,
                "song_length": 4,
            }
        i = params.get("track_index", 0)
        if kind == "get_track_info":
            return {
                "index": i,
                "name": self.name if i == 0 else "GROUP | Layers",
                "is_midi_track": i == 0,
                "is_audio_track": i == 1,
                "arm": None if i == 1 or self.frozen else False,
                "devices": [],
                "color_index": self.color if i == 0 else 13,
                "mute": False,
                "clip_slots": [
                    {
                        "index": 0,
                        "has_clip": True,
                        "clip": {"name": "ORIGINAL | Backup", "length": 4},
                    }
                ]
                if i == 0
                else [],
            }
        if kind == "get_group_info":
            if not self.grouping_supported:
                raise RuntimeError("Unknown command")
            return {"is_foldable": i == 1, "group_track": None, "is_grouped": False}
        if kind == "get_arrangement_clips":
            if i == 1:
                raise RuntimeError("Main, Group and Return Tracks have no arrangement clips")
            return {
                "clips": [
                    {
                        "name": self.clip_name,
                        "start_time": self.clip_start,
                        "end_time": 4,
                        "is_audio_clip": False,
                        "is_midi_clip": True,
                    }
                ]
            }
        if kind == "get_access_notes":
            if self.fail_notes:
                raise RuntimeError("Note API unavailable")
            return {"notes": deepcopy(self.notes), "loop_start": 0, "loop_end": 4}
        if kind == "read_access_object":
            if params.get("expected_track_name") != self.name:
                raise RuntimeError("Stale track")
            if params.get("clip_view") == "arrangement" and (
                params.get("expected_start_time") != self.clip_start
                or params.get("expected_clip_name") != self.clip_name
            ):
                raise RuntimeError("Stale clip")
            return {"properties": {"name": self.clip_name, "color_index": self.color}}
        if kind == "write_access_object":
            if params["expected_track_name"] != (self.name if i == 0 else "GROUP | Layers"):
                raise RuntimeError("Stale write target")
            if params["object_type"] == "clip":
                self.send_command("read_access_object", params)
                self.clip_name = params["properties"].get("name", self.clip_name)
            else:
                self.name = params["properties"].get("name", self.name)
                self.color = params["properties"].get("color_index", self.color)
            self.writes.append(deepcopy(params))
            return {"verified": True}
        if kind == "batch":
            results = []
            for command in params["commands"]:
                results.append({"result": self.send_command(command["type"], command["params"])})
            return {"executed": len(results), "results": results}
        raise AssertionError("Unexpected command: " + kind)


class LiveLintTests(unittest.TestCase):
    def test_collector_and_default_live_lint_are_read_only(self):
        live = FakeLive()
        report = run_lint({"steps": []}, live=True, connection=live)
        self.assertEqual(live.writes, [])
        self.assertTrue(report["readOnly"])
        self.assertEqual(report["source"], "live")
        self.assertEqual(report["exitCode"], 1)
        self.assertTrue(any(f["code"] == "MIDI_SAME_PITCH_OVERLAP" for f in report["findings"]))
        self.assertFalse(
            any(k in {"add_notes_to_clip", "set_tempo", "delete_clip"} for k, _ in live.calls)
        )

    def test_frozen_track_is_not_misclassified_as_a_group(self):
        live = FakeLive()
        live.frozen = True
        captured = collect_live(live)
        self.assertEqual(captured["tracks"][0]["type"], "midi")
        self.assertEqual(len(captured["tracks"][0]["clips"]), 1)
        self.assertEqual(captured["tracks"][1]["type"], "group")

    def test_old_bridge_group_error_is_not_an_empty_track(self):
        live = FakeLive()
        live.grouping_supported = False
        captured = collect_live(live)
        self.assertTrue(captured["tracks"][1]["is_group"])
        self.assertFalse(captured["capture_errors"])

    def test_read_failure_is_incomplete_not_empty(self):
        live = FakeLive()
        live.fail_notes = True
        report = run_lint({}, live=True, connection=live)
        self.assertEqual(report["exitCode"], 2)
        self.assertEqual(report["status"], "incomplete")
        self.assertFalse(any(f["code"] == "MIDI_EMPTY_CLIP" for f in report["findings"]))
        self.assertFalse(live.writes)

    def test_original_session_backups_are_protected(self):
        live = FakeLive()
        report = run_lint({}, live=True, connection=live, include_session=True)
        self.assertTrue(report["scope"]["includeSession"])
        self.assertFalse(
            any(f["clip"] and f["clip"]["view"] == "session" for f in report["findings"])
        )

    def test_disabled_cleanup_steps_do_not_disable_lint(self):
        report = run_lint(
            {"steps": [{"id": "midi", "process": "quantize_timing", "enabled": False}]},
            snapshot=fixture(),
        )
        self.assertTrue(any(f["rule"] == "midi_grid" for f in report["findings"]))

    def test_chords_are_not_monophonized(self):
        state = fixture()
        state["tracks"][0]["role"] = "chords"
        notes = state["tracks"][0]["clips"][0]["notes"]
        notes[1]["pitch"] = 33
        notes[1]["start_time"] = 0.1
        report = lint_state(state, selected_rules=["midi_overlaps"])
        self.assertFalse(report["findings"])
        state["tracks"][0]["role"] = "bass"
        self.assertTrue(lint_state(state, selected_rules=["midi_overlaps"])["findings"])

    def test_missing_audio_is_an_error_not_empty(self):
        state = fixture()
        clip = state["tracks"][0]["clips"][0]
        clip.update(type="audio", file_exists=False, audio_path="missing.wav")
        clip.pop("notes")
        report = lint_state(state)
        self.assertTrue(
            any(
                f["code"] == "AUDIO_MISSING" and f["severity"] == "error"
                for f in report["findings"]
            )
        )
        self.assertFalse(any(f["code"] == "AUDIO_ZERO_LENGTH" for f in report["findings"]))

    def test_invalid_notes_and_nonfinite_time(self):
        state = fixture()
        state["tracks"][0]["clips"][0]["notes"][0]["pitch"] = 200
        report = lint_state(state, selected_rules=["midi_validity"])
        self.assertEqual(report["exitCode"], 1)
        self.assertFalse(report["findings"][0]["autofixable"])

    def test_negative_pickup_notes_are_valid(self):
        state = fixture()
        state["tracks"][0]["clips"][0]["notes"][0]["start_time"] = -0.25
        report = lint_state(state, selected_rules=["midi_validity"])
        self.assertFalse(report["findings"])
        self.assertEqual(report["exitCode"], 0)

    def test_intentional_short_clip_is_only_info(self):
        state = fixture()
        state["tracks"][0]["clips"][0]["end_beats"] = 3.5
        report = lint_state(state, selected_rules=["clip_boundaries"])
        self.assertEqual(report["exitCode"], 0)
        self.assertEqual(report["findings"][0]["severity"], "info")
        self.assertFalse(report["findings"][0]["autofixable"])

    def test_velocity_saturation_is_detected(self):
        state = fixture()
        state["tracks"][0]["clips"][0]["notes"] = [
            {"pitch": 36, "start_time": i, "duration": 0.1, "velocity": 127} for i in range(10)
        ]
        report = lint_state(state, selected_rules=["midi_dynamics"])
        self.assertEqual(report["findings"][0]["code"], "MIDI_MAX_VELOCITY")

    def test_explicit_stem_groups_and_optional_unassessed_status(self):
        state = fixture()
        report = lint_state(state)
        self.assertEqual(
            next(c for c in report["checks"] if c["rule"] == "stem_sync")["status"], "not_evaluated"
        )
        self.assertEqual(lint_state(state, selected_rules=["stem_sync"])["exitCode"], 2)
        with self.assertRaises(ValueError):
            lint_state(state, {"rules": {"stem_sync": {"params": {"groups": [["bad", "t"]]}}}})

    def test_filename_half_double_is_review_not_wrong_tempo(self):
        state = fixture()
        clip = state["tracks"][0]["clips"][0]
        clip.update(
            type="audio",
            warping=True,
            audio_path="Loop_140_Bass.wav",
            warp_markers=[
                {"beat_time": 0, "sample_time": 0},
                {"beat_time": 4, "sample_time": 24 / 7},
            ],
        )
        report = lint_state(state, selected_rules=["warp_maps"])
        self.assertEqual(report["findings"][0]["code"], "WARP_HALF_DOUBLE")
        self.assertEqual(report["findings"][0]["severity"], "info")

    def test_fix_applies_only_metadata_and_re_lints(self):
        live = FakeLive()
        original = deepcopy(live.notes)
        report = run_lint({}, live=True, connection=live, fix=True)
        self.assertFalse(report["readOnly"])
        self.assertEqual(len(report["appliedFixIds"]), 2)
        self.assertFalse(
            any(
                f["code"] in {"TRACK_DEFAULT_NAME", "CLIP_DEFAULT_NAME"} for f in report["findings"]
            )
        )
        self.assertTrue(any(f["code"] == "MIDI_SAME_PITCH_OVERLAP" for f in report["findings"]))
        self.assertEqual(live.notes, original)
        self.assertTrue(all(set(w["properties"]) <= {"name", "color_index"} for w in live.writes))

    def test_stale_fix_target_has_no_writes(self):
        live = FakeLive()
        report = run_lint({}, live=True, connection=live)
        live.clip_start = 1
        with self.assertRaises(RuntimeError):
            apply_metadata_fixes(report, live)
        self.assertFalse(live.writes)

    def test_snapshot_fixes_and_incomplete_fixes_are_rejected(self):
        with self.assertRaises(ValueError):
            run_lint({}, snapshot=fixture(), fix=True)
        live = FakeLive()
        live.fail_notes = True
        with self.assertRaises(ValueError):
            run_lint({}, live=True, connection=live, fix=True)
        self.assertFalse(live.writes)

    def test_unknown_rule_and_fail_threshold(self):
        with self.assertRaises(ValueError):
            lint_state(fixture(), {"rules": {"misspelled": {}}})
        self.assertEqual(lint_state(fixture(), {"failOn": "error"})["exitCode"], 0)
        self.assertEqual(lint_state(fixture(), {"failOn": "info"})["exitCode"], 1)
        state = fixture()
        state["capture_errors"] = [{"target": "t", "error": "unavailable"}]
        self.assertEqual(lint_state(state, {"failOn": "none"})["exitCode"], 2)

    def test_cli_snapshot_lint_writes_only_explicit_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "initiation.yaml"
            config.write_text(yaml.safe_dump({"schemaVersion": 1, "steps": []}))
            snapshot = root / "state.json"
            snapshot.write_text(json.dumps(fixture()))
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = main(["lint", str(config), "--snapshot", str(snapshot)])
            self.assertEqual(status, 1)
            self.assertTrue(json.loads(output.getvalue())["readOnly"])
            self.assertEqual(set(p.name for p in root.iterdir()), {"state.json", "initiation.yaml"})
            report_path = root / "lint.json"
            with contextlib.redirect_stdout(io.StringIO()):
                main(
                    [
                        "song-init",
                        str(config),
                        "--snapshot",
                        str(snapshot),
                        "--lint",
                        "--report",
                        str(report_path),
                    ]
                )
            self.assertEqual(json.loads(report_path.read_text())["mode"], "lint")
            with self.assertRaises(ValueError):
                write_report(report_path, {})

    def test_blank_names_are_reported_without_unsupported_fix(self):
        state = fixture()
        state["tracks"][0]["clips"][0]["name"] = ""
        result = lint_state(state, selected_rules=["clip_naming"])
        self.assertEqual(result["findings"][0]["code"], "CLIP_DEFAULT_NAME")
        self.assertFalse(result["findings"][0]["autofixable"])
        self.assertEqual(result["status"], "review")

    def test_harmonic_rub_is_review_only_and_does_not_retune(self):
        state = fixture()
        state["tracks"][0]["role"] = "chords"
        state["tracks"][0]["clips"][0]["notes"][1].update(pitch=30, start_time=0.1, duration=2)
        before = deepcopy(state)
        result = lint_state(state, selected_rules=["harmonic_layering"])
        self.assertEqual(result["findings"][0]["code"], "MIDI_SUSTAINED_CLOSE_INTERVAL")
        self.assertFalse(result["findings"][0]["autofixable"])
        self.assertEqual(state, before)
        state["tracks"][0]["role"] = "drums"
        self.assertFalse(lint_state(state, selected_rules=["harmonic_layering"])["findings"])

    def test_selected_clip_scope_and_unknown_ids(self):
        state = fixture()
        state["tracks"].append(
            {"id": "outside", "name": "Other", "role": "audio", "type": "audio", "clips": []}
        )
        result = run_lint({}, snapshot=state, target={"clipIds": ["c"]})
        self.assertEqual(result["summary"]["tracks"], 1)
        self.assertEqual(result["summary"]["midiNotes"], 3)
        self.assertEqual(result["scope"]["target"], {"clipIds": ["c"]})
        with self.assertRaises(ValueError):
            run_lint({}, snapshot=state, target={"trackIds": ["unknown"]})

    def test_note_data_absent_cannot_pass(self):
        state = fixture()
        state["tracks"][0]["clips"][0].pop("notes")
        self.assertEqual(lint_state(state)["exitCode"], 2)

    def test_report_preflight_before_live_connection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = root / "initiation.yaml"
            config.write_text(yaml.safe_dump({"schemaVersion": 1, "steps": []}))
            occupied = root / "existing.json"
            occupied.write_text("keep")
            with (
                patch("enableton.song_lint.run_lint") as runner,
                contextlib.redirect_stderr(io.StringIO()),
            ):
                with self.assertRaises(SystemExit):
                    main(["lint", str(config), "--live", "--report", str(occupied)])
            runner.assert_not_called()
            self.assertEqual(occupied.read_text(), "keep")
