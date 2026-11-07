from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from enableton import song_processes
from enableton.cli import main
from enableton.song_init import (
    REGISTRY,
    SnapshotAdapter,
    UnsupportedOperations,
    Result,
    load_config,
    project,
    register,
    run_pipeline,
    song_folder,
    validate,
)


def state():
    return {
        "session": {"tempo": 141, "numerator": 4, "denominator": 4},
        "tracks": [
            {
                "id": "bass",
                "name": "1-MIDI",
                "role": "bass",
                "type": "midi",
                "devices": [],
                "has_automation": False,
                "clips": [
                    {
                        "id": "phrase",
                        "type": "midi",
                        "name": "Track 1",
                        "end_beats": 4,
                        "notes": [
                            {"pitch": 29, "start_time": 0.1, "duration": 1.2, "velocity": 127},
                            {"pitch": 29, "start_time": 1.0, "duration": 0.5, "velocity": 90},
                            {"pitch": 36, "start_time": 0.1, "duration": 1.2, "velocity": 90},
                        ],
                    }
                ],
            }
        ],
    }


def step(identifier, process, **params):
    return {"id": identifier, "process": process, "enabled": True, "params": params}


def config(root):
    return {
        "schemaVersion": 1,
        "song": {"root": str(root), "name": "My Song", "onExists": "reuse"},
        "steps": [step("workspace", "create_song_folder"), step("names", "rename_tracks")],
    }


class MemoryAdapter(SnapshotAdapter):
    def supports(self, change):
        return change["kind"] in {"set_track", "set_clip", "replace_midi"}

    def apply(self, change):
        project(self.state, change)


class SongInitTests(unittest.TestCase):
    def test_complete_example_and_registry(self):
        root = Path(__file__).resolve().parents[2]
        example = load_config(root / "examples/song-init/initiation.yaml")
        self.assertEqual(len(REGISTRY), 16)
        self.assertGreaterEqual(len(example["steps"]), 16)
        self.assertTrue(all(s["process"] in REGISTRY for s in example["steps"]))

    def test_dry_run_projects_order_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = SnapshotAdapter(state())
            adapter.apply = Mock(side_effect=AssertionError("write during dry run"))
            cfg = config(Path(directory))
            cfg["steps"].append(step("colors", "color_tracks_by_type"))
            report = run_pipeline(cfg, adapter)
            adapter.apply.assert_not_called()
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertEqual(adapter.snapshot(), state())
            self.assertEqual(report["steps"][1]["before"]["workspace"]["name"], "My Song")
            self.assertEqual(report["steps"][2]["before"]["tracks"][0]["name"], "bass_Unassigned")
            self.assertEqual(report["steps"][2]["after"]["tracks"][0]["color_index"], 20)

    def test_unsupported_writer_preflight_before_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(UnsupportedOperations):
                run_pipeline(config(Path(directory)), SnapshotAdapter(state()), dry_run=False)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_folder_reuse_manifest_logs_and_cli_overrides(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = config(root)
            adapter = MemoryAdapter(state())
            report = run_pipeline(cfg, adapter, dry_run=False)
            folder = root / "my-song"
            self.assertEqual(report["songFolder"], str(folder))
            self.assertEqual(json.loads((folder / "song.json").read_text())["name"], "My Song")
            self.assertTrue((folder / "audio").is_dir())
            self.assertEqual(len(list((folder / "reports").glob("*.json"))), 1)
            (folder / "originals" / "keep.txt").write_text("keep")
            again = run_pipeline(cfg, adapter, dry_run=False)
            self.assertEqual(again["steps"][1]["changes"], [])
            self.assertEqual((folder / "originals" / "keep.txt").read_text(), "keep")
            self.assertEqual(len(list((folder / "configs").glob("*.yaml"))), 2)

    def test_path_traversal_and_reserved_names(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ["../escape", "/absolute", "CON", "LPT1", "", "a/b"]:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    song_folder({"root": directory, "name": "Song", "folderName": name})
            with self.assertRaises(ValueError):
                song_folder({"root": "relative", "name": "Song"})
            folder = Path(directory) / "other"
            folder.mkdir()
            (folder / "song.json").write_text('{"name":"Someone Else"}')
            with self.assertRaises(ValueError):
                song_folder(
                    {"root": directory, "name": "New", "folderName": "other", "onExists": "reuse"}
                )

    def test_explicit_folder_name_preserves_spaces(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            cfg["song"].update(name="In Hell", folderName="In Hell")
            report = run_pipeline(cfg, SnapshotAdapter(state()), dry_run=False, only=["workspace"])
            self.assertEqual(Path(report["songFolder"]), Path(directory) / "In Hell")
            self.assertTrue((Path(directory) / "In Hell" / "song.json").is_file())
            self.assertFalse((Path(directory) / "in-hell").exists())
            for name in [" In Hell", "In Hell ", "In  Hell", "../In Hell"]:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    song_folder({"root": directory, "name": "In Hell", "folderName": name})

    def test_subset_order_and_unknown_id(self):
        with tempfile.TemporaryDirectory() as directory:
            cfg = config(Path(directory))
            result = run_pipeline(cfg, SnapshotAdapter(state()), only=["names"])
            self.assertEqual([s["id"] for s in result["steps"]], ["names"])
            with self.assertRaises(ValueError):
                run_pipeline(cfg, SnapshotAdapter(state()), only=["typo"])
            cfg["steps"][1]["when"] = {"hasAudio": True}
            result = run_pipeline(cfg, SnapshotAdapter(state()), only=["names"], dry_run=False)
            self.assertEqual(result["steps"][0]["status"], "skipped")

    def test_failure_log_captures_after_and_stops(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = MemoryAdapter(state())
            adapter.apply = Mock(side_effect=RuntimeError("writer failed"))
            with self.assertRaises(RuntimeError):
                run_pipeline(config(Path(directory)), adapter, dry_run=False)
            logs = list((Path(directory) / "my-song" / "reports").glob("*.json"))
            last = json.loads(logs[0].read_text())[-1]
            self.assertEqual(last["status"], "failed")
            self.assertEqual(last["after"]["tracks"], state()["tracks"])
            self.assertEqual(last["after"]["workspace"]["name"], "My Song")

    def test_schema_errors_fail_early(self):
        for mutate in [
            lambda c: c.update(schemaVersion=True),
            lambda c: c["steps"].append(deepcopy(c["steps"][0])),
            lambda c: c["steps"][0].update(process="unknown"),
            lambda c: c["steps"][0].update(enabled="yes"),
            lambda c: c["steps"][0].update(when={"eval": "bad"}),
            lambda c: c["steps"][0].update(target={"clipIds": "all"}),
        ]:
            cfg = config(Path.cwd())
            mutate(cfg)
            with self.assertRaises(ValueError):
                validate(cfg)

    def test_overlap_strategies_preserve_chords_by_default(self):
        source = state()
        before = deepcopy(source)
        for strategy, length in [("trim", 3), ("shortest_wins", 2), ("longest_wins", 2)]:
            report = REGISTRY["fix_midi_overlaps"](source, {"strategy": strategy}, {})
            notes = report.changes[0]["patch"]["notes"]
            self.assertEqual(len(notes), length)
            self.assertTrue(any(n["pitch"] == 36 for n in notes))
        self.assertEqual(source, before)
        notes = REGISTRY["fix_midi_overlaps"](source, {}, {}).changes[0]["patch"]["notes"]
        self.assertAlmostEqual(notes[0]["duration"], 0.89)

    def test_quantize_tolerance_strength_and_velocity(self):
        source = state()
        result = REGISTRY["quantize_timing"](source, {"strength": 1}, {})
        self.assertEqual(result.changes[0]["patch"]["notes"][0]["start_time"], 0)
        self.assertEqual(
            REGISTRY["quantize_timing"](source, {"toleranceBeats": 0.11}, {}).changes, []
        )
        with self.assertRaises(ValueError):
            REGISTRY["quantize_timing"](source, {"strength": 2}, {})
        velocity = REGISTRY["normalize_velocities"](source, {}, {}).changes[0]["patch"]["notes"]
        self.assertEqual(velocity[0]["velocity"], 112)

    def test_missing_media_is_not_empty_and_clip_target_protects_tracks(self):
        source = state()
        source["tracks"].append(
            {
                "id": "empty",
                "type": "audio",
                "name": "Audio",
                "has_automation": False,
                "clips": [],
                "devices": [],
            }
        )
        result = REGISTRY["remove_empty_tracks"](source, {}, {"clipIds": ["phrase"]})
        self.assertEqual(result.changes, [])
        source["tracks"][1]["clips"] = [
            {"id": "missing", "name": "Missing", "type": "audio", "file_exists": False}
        ]
        self.assertEqual(REGISTRY["remove_empty_clips"](source, {}, {}).changes, [])
        self.assertTrue(REGISTRY["check_missing_samples"](source, {}, {}).notices)

    def test_extension_registration(self):
        @register("test_audit")
        def audit(state, params, target):
            return Result(notices=["custom"])

        try:
            cfg = {"schemaVersion": 1, "steps": [step("audit", "test_audit")]}
            self.assertEqual(
                run_pipeline(cfg, SnapshotAdapter(state()))["steps"][0]["notices"], ["custom"]
            )
        finally:
            REGISTRY.pop("test_audit")

    def test_cli_folder_only_apply_and_default_dry_run(self):
        root = Path(__file__).resolve().parents[2]
        snapshot = root / "examples/song-init/snapshot.example.json"
        yaml_path = root / "examples/song-init/initiation.yaml"
        with (
            tempfile.TemporaryDirectory() as directory,
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            args = [
                "song-init",
                str(yaml_path),
                "--snapshot",
                str(snapshot),
                "--only",
                "workspace",
                "--song-root",
                directory,
                "--song-name",
                "CLI Song",
            ]
            self.assertEqual(main(args), 0)
            self.assertFalse((Path(directory) / "cli-song").exists())
            self.assertEqual(main(args + ["--apply"]), 0)
            self.assertTrue((Path(directory) / "cli-song" / "song.json").is_file())
