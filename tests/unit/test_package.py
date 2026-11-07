import contextlib
import io
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
import enableton
from enableton.cli import main
from enableton.warp_tools import _analyze
from test_warp import pulse_file


class PackageTests(unittest.TestCase):
    def test_version_and_reference_data(self):
        root = Path(__file__).resolve().parents[2]
        project = tomllib.loads((root / "pyproject.toml").read_text())
        self.assertEqual(project["project"]["version"], enableton.__version__)
        packed = Path(enableton.__file__).with_name("production_recipes.json")
        data = json.loads(packed.read_text(encoding="utf-8"))
        self.assertEqual(len(data["entries"]), 50)
        self.assertEqual(
            data, json.loads((root / "data" / "recipes.json").read_text(encoding="utf-8"))
        )

    def test_doctor_missing_installation_is_json(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            contextlib.redirect_stdout(io.StringIO()) as stream,
        ):
            code = main(["doctor", "--user-library", temp, "--json"])
            data = json.loads(stream.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(data["ok"])

    def test_namespaced_worker_runs_from_installed_package(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "pulse.wav"
            pulse_file(path, tempo=120, seconds=8)
            report = _analyze(path, max_seconds=8, tempo_hint=120)
            self.assertGreater(len(report["onsets"]), 8)
