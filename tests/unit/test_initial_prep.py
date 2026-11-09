"""Default initial preparation preset: schema, defaults and safety."""

import tempfile
import unittest
import unittest.mock
from pathlib import Path

import yaml

from enableton import initial_prep
from enableton.song_init import validate
from enableton.song_processes import REGISTRY


class PhaseTests(unittest.TestCase):
    def test_phases_are_ordered_and_complete(self):
        self.assertEqual(
            initial_prep.PHASES, ("protect", "identify", "audible", "time", "navigate", "gate")
        )
        seen = [step["phase"] for step in initial_prep.describe()]
        self.assertEqual(seen, sorted(seen, key=initial_prep.PHASES.index))
        self.assertEqual(set(seen), set(initial_prep.PHASES))

    def test_step_ids_and_processes_are_unique_and_registered(self):
        ids = [step["id"] for step in initial_prep.STEPS]
        self.assertEqual(len(ids), len(set(ids)))
        for step in initial_prep.STEPS:
            self.assertIn(step["process"], REGISTRY, step["id"])

    def test_describe_covers_every_step_once(self):
        described = initial_prep.describe()
        self.assertEqual(len(described), len(initial_prep.STEPS))
        self.assertEqual(
            {item["id"] for item in described},
            {step["id"] for step in initial_prep.STEPS},
        )


class SafetyDefaultTests(unittest.TestCase):
    def enabled(self):
        return {step["id"] for step in initial_prep.STEPS if step["enabled"]}

    def test_check_is_the_only_step_off_by_default(self):
        self.assertEqual(
            self.enabled(), {"adopt", "name", "label", "voice", "level", "lock", "frame", "map"}
        )
        check = next(step for step in initial_prep.STEPS if step["id"] == "check")
        self.assertFalse(check["enabled"])
        self.assertEqual(check["process"], "prep_check")

    def test_steps_follow_the_nine_operations(self):
        self.assertEqual(
            [step["id"] for step in initial_prep.STEPS],
            [
                "adopt",
                "name",
                "label",
                "voice",
                "level",
                "lock",
                "frame",
                "map",
                "check",
            ],
        )
        self.assertTrue(all(step["process"] == f"prep_{step['id']}" for step in initial_prep.STEPS))


class ConfigTests(unittest.TestCase):
    def test_prepare_config_is_schema_valid(self):
        config = initial_prep.build_config("/music/Song", "Song", mode="prepare")
        validate(config)
        self.assertEqual(len(config["steps"]), len(initial_prep.STEPS))
        self.assertTrue(any(step["enabled"] for step in config["steps"]))

    def test_lint_config_is_schema_valid_and_writes_nothing(self):
        config = initial_prep.build_config("/music/Song", "Song", mode="lint")
        validate(config)
        self.assertFalse(any(step["enabled"] for step in config["steps"]))
        self.assertIn("rules", config["lint"])
        self.assertNotIn("initialPrep", config)

    def test_invalid_input_is_rejected(self):
        with self.assertRaises(ValueError):
            initial_prep.build_config("/music/Song", "Song", mode="apply")
        with self.assertRaises(ValueError):
            initial_prep.build_config("", "Song")
        with self.assertRaises(ValueError):
            initial_prep.build_config("/music/Song", "   ")

    def test_written_config_round_trips_as_yaml(self):
        with tempfile.TemporaryDirectory() as temp:
            path = initial_prep.write_config(
                Path(temp) / "initiate.yaml", "/music/Song", "Song", mode="prepare"
            )
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        validate(loaded)
        self.assertEqual(loaded["song"]["root"], "/music/Song")


class IsolationTests(unittest.TestCase):
    def test_build_config_does_not_share_preset_state(self):
        config = initial_prep.build_config("/music/Song", "Song", mode="prepare")
        config["steps"][0]["params"]["injected"] = True
        config["lint"]["rules"]["missing_samples"]["enabled"] = False
        self.assertNotIn("injected", initial_prep.STEPS[0]["params"])
        self.assertTrue(initial_prep.LINT["rules"]["missing_samples"]["enabled"])

    def test_two_configs_are_independent(self):
        first = initial_prep.build_config("/music/A", "A", mode="prepare")
        second = initial_prep.build_config("/music/B", "B", mode="prepare")
        first["steps"][1]["enabled"] = False
        self.assertTrue(second["steps"][1]["enabled"])

    def test_write_config_never_replaces_an_existing_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "initiate.yaml"
            initial_prep.write_config(path, "/music/Song", "Song")
            with self.assertRaises(FileExistsError):
                initial_prep.write_config(path, "/music/Song", "Song")

    def test_validation_rejects_a_malformed_preset(self):
        broken = [dict(step, phase="nonsense") for step in initial_prep.STEPS]
        with unittest.mock.patch.object(initial_prep, "STEPS", broken):
            with self.assertRaises(ValueError):
                initial_prep.build_config("/music/Song", "Song")
        duplicate = [dict(step) for step in initial_prep.STEPS] + [dict(initial_prep.STEPS[0])]
        with unittest.mock.patch.object(initial_prep, "STEPS", duplicate):
            with self.assertRaises(ValueError):
                initial_prep.describe()


if __name__ == "__main__":
    unittest.main()
