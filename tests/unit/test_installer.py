import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from enableton import installer


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.stage = self.root / "stage"
        self.stage.mkdir()
        self.remote = self.root / "Remote Scripts" / "EnAbleton"
        self.remote.mkdir(parents=True)
        (self.remote / "__init__.py").write_text("OLD = 1\n")
        (self.stage / "__init__.py").write_text("NEW = 1\n")
        (self.stage / "access_support.py").write_text("NEW = 2\n")
        manifest = {
            "extension_version": "test",
            "enableton_version": "0.1.0b1",
            "files": {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.stage.glob("*.py")
            },
        }
        (self.stage / "ext-manifest.json").write_text(json.dumps(manifest))

    def tearDown(self):
        self.temp.cleanup()

    def install(self):
        return installer.install_bridge(
            self.stage, self.remote, self.root / "backups", replace=True
        )

    def test_install_backed_up_and_verified(self):
        result = self.install()
        self.assertGreater(result["installed_files_verified"], 2)
        self.assertEqual(
            (Path(result["backup"]) / "RemoteScript" / "__init__.py").read_text(), "OLD = 1\n"
        )
        self.assertEqual((self.remote / "__init__.py").read_text(), "NEW = 1\n")
        self.assertFalse(result["song_modified"])

    def test_existing_install_requires_explicit_replace(self):
        with self.assertRaisesRegex(ValueError, "--replace"):
            installer.install_bridge(self.stage, self.remote, self.root / "backups")

    def test_bad_stage_has_no_changes(self):
        (self.stage / "__init__.py").write_text("tampered")
        with self.assertRaises(ValueError):
            self.install()
        self.assertEqual((self.remote / "__init__.py").read_text(), "OLD = 1\n")

    def test_partial_failure_restores_prior_files(self):
        real = installer.atomic_copy
        calls = []

        def fail_once(source, destination):
            calls.append(str(destination))
            if len(calls) == 3:
                raise OSError("simulated install failure")
            return real(source, destination)

        with patch.object(installer, "atomic_copy", fail_once):
            with self.assertRaisesRegex(RuntimeError, "previous installation restored"):
                self.install()
        self.assertEqual((self.remote / "__init__.py").read_text(), "OLD = 1\n")
        self.assertFalse((self.remote / "access_support.py").exists())

    def test_first_install(self):
        destination = self.root / "new" / "Remote Scripts" / "EnAbleton"
        result = installer.install_bridge(self.stage, destination, self.root / "backups")
        self.assertTrue((destination / "__init__.py").is_file())
        self.assertFalse(result["song_modified"])
