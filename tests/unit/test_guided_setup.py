"""The read-only first-run setup check."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from enableton import cli
from enableton.guided_setup import inspect_installation, report


def digest(data):
    return hashlib.sha256(data).hexdigest()


def make_install(root, manifest=None):
    remote = Path(root) / "Remote Scripts" / "EnAbleton"
    remote.mkdir(parents=True)
    files = {"__init__.py": b"# script\n", "handler.py": b"# handler\n"}
    for name, data in files.items():
        (remote / name).write_bytes(data)
    document = {"files": {name: digest(data) for name, data in files.items()}}
    document.update(manifest or {})
    (remote / "ext-manifest.json").write_text(json.dumps(document), encoding="utf-8")
    return remote


class InspectTests(unittest.TestCase):
    def test_missing_install_is_reported_without_error(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "User Library"
            library.mkdir()
            state = inspect_installation(library / "Remote Scripts" / "EnAbleton")
            self.assertEqual(state["state"], "missing")
            self.assertFalse(Path(state["path"]).exists())

    def test_matching_files_report_installed_with_versions(self):
        with tempfile.TemporaryDirectory() as temp:
            remote = make_install(
                Path(temp) / "User Library",
                {"upstream_version": "1.8.1", "extension_version": "1.8.1-ext.15"},
            )
            state = inspect_installation(remote)
            self.assertEqual(state["state"], "installed")
            self.assertEqual(state["installed_extension_version"], "1.8.1-ext.15")
            self.assertEqual(state["modified_files"], [])

    def test_edited_and_deleted_files_report_modified(self):
        with tempfile.TemporaryDirectory() as temp:
            remote = make_install(Path(temp) / "User Library")
            (remote / "handler.py").write_text("# edited\n")
            (remote / "__init__.py").unlink()
            state = inspect_installation(remote)
            self.assertEqual(state["state"], "modified")
            self.assertEqual(state["modified_files"], ["handler.py"])
            self.assertEqual(state["missing_files"], ["__init__.py"])

    def test_unreadable_manifest_is_not_mistaken_for_installed(self):
        with tempfile.TemporaryDirectory() as temp:
            remote = make_install(Path(temp) / "User Library")
            (remote / "ext-manifest.json").write_text("{", encoding="utf-8")
            self.assertEqual(inspect_installation(remote)["state"], "unreadable")


class ReportTests(unittest.TestCase):
    def test_missing_install_asks_for_install_then_doctor(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "User Library"
            library.mkdir()
            result = report(library)
            self.assertFalse(result["ready"])
            self.assertTrue(result["next"][0].startswith("enableton install"))
            self.assertIn("enableton doctor", result["next"][1])
            self.assertFalse(result["song_modified"])

    def test_installed_script_drops_the_install_step(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "User Library"
            make_install(library)
            result = report(library)
            self.assertTrue(result["ready"])
            self.assertEqual(len(result["next"]), 1)
            self.assertIn("enableton doctor", result["next"][0])

    def test_modified_install_requires_reviewed_replacement(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "User Library"
            remote = make_install(library)
            (remote / "handler.py").write_text("# edited\n")
            result = report(library)
            self.assertFalse(result["ready"])
            self.assertIn("--replace", result["next"][0])

    def test_client_entry_appears_only_when_requested(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "User Library"
            make_install(library)
            self.assertNotIn("client_config", report(library))
            entry = report(library, "cursor")["client_config"]
            self.assertEqual(entry["client"], "cursor")
            self.assertIn("mcpServers", entry["entry"])
            self.assertIn("enableton client-config cursor", report(library, "cursor")["next"])

    def test_check_writes_nothing_into_the_user_library(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "User Library"
            make_install(library)
            song = library / "song.als"
            song.write_text("set", encoding="utf-8")
            before = sorted(str(p) for p in library.rglob("*"))
            result = report(library, "claude-desktop")
            self.assertEqual(sorted(str(p) for p in library.rglob("*")), before)
            self.assertEqual(song.read_text(encoding="utf-8"), "set")
            self.assertFalse(result["song_modified"])
            self.assertIn("launches nothing", result["writes"])


class CommandTests(unittest.TestCase):
    def test_installed_library_exits_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "User Library"
            make_install(library)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["setup", "--user-library", str(library)])
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(stdout.getvalue())["ready"])

    def test_pending_install_exits_one(self):
        with tempfile.TemporaryDirectory() as temp:
            library = Path(temp) / "User Library"
            library.mkdir()
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                code = cli.main(["setup", "--user-library", str(library), "--client", "cursor"])
            self.assertEqual(code, 1)
            payload = json.loads(stdout.getvalue())
            self.assertFalse(payload["ready"])
            self.assertEqual(payload["client_config"]["client"], "cursor")


if __name__ == "__main__":
    unittest.main()
