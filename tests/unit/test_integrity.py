"""Shared helpers, guard rails and documented-count consistency."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from enableton.audio_scan_tools import scan_audio_file
from enableton.jsonio import atomic_json, read_json
from enableton.numbers import finite
from enableton.remix_assets import _process_alive, project, project_lock

ROOT = Path(__file__).resolve().parents[2]


class JsonIOTests(unittest.TestCase):
    def test_round_trip_and_atomic_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "state.json"
            atomic_json(path, {"a": 1})
            self.assertEqual(read_json(path), {"a": 1})
            atomic_json(path, {"a": 2})
            self.assertEqual(read_json(path), {"a": 2})
            self.assertEqual([p.name for p in path.parent.iterdir()], ["state.json"])


class NumbersTests(unittest.TestCase):
    def test_rejects_booleans_strings_and_non_finite(self):
        for value in (True, "1", float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                finite(value, "level")

    def test_returns_float(self):
        self.assertIsInstance(finite(3, "level"), float)


class ProjectLockTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root, _ = project(Path(self.temp.name) / "remix", create=True)
        self.lock = self.root / "operation.lock"

    def test_current_process_is_alive(self):
        self.assertIs(_process_alive(os.getpid()), True)
        self.assertFalse(_process_alive(None))

    def test_stale_lock_from_dead_process_is_reclaimed(self):
        dead = subprocess.Popen([sys.executable, "-c", "pass"])
        dead.wait()
        self.lock.write_text(json.dumps({"pid": dead.pid}))
        with project_lock(self.root):
            self.assertTrue(self.lock.exists())
        self.assertFalse(self.lock.exists())

    def test_lock_held_by_live_process_is_refused(self):
        self.lock.write_text(json.dumps({"pid": os.getpid()}))
        with self.assertRaises(RuntimeError):
            with project_lock(self.root):
                pass
        self.assertTrue(self.lock.exists())


class ScanPathTests(unittest.TestCase):
    def test_relative_path_is_refused_before_any_worker(self):
        with self.assertRaises(ValueError):
            scan_audio_file("relative.wav")


class RecipeCountTests(unittest.TestCase):
    def test_documented_counts_match_the_dataset(self):
        entries = json.loads(
            (ROOT / "src" / "enableton" / "production_recipes.json").read_text(encoding="utf-8")
        )["entries"]
        total = len(entries)
        sourced = sum(1 for entry in entries if entry.get("sources"))
        self.assertEqual(total, 50)
        self.assertEqual(sourced, 45)
        self.assertEqual(len({entry["id"] for entry in entries}), total)
        for name in ("README.md", "docs/FEATURES.md", "docs/RECIPE_CATALOG.md"):
            text = (ROOT / name).read_text(encoding="utf-8")
            self.assertIn(str(total), text, name)
            self.assertIn(str(sourced), text, name)
