"""User Library discovery and the reversible Remote Script uninstall."""

import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from enableton import cli
from enableton.setup import candidate_libraries, discover_library, uninstall_bridge


def digest(data):
    return hashlib.sha256(data).hexdigest()


def make_install(root, extra_file=None):
    remote = Path(root) / "Remote Scripts" / "EnAbleton"
    remote.mkdir(parents=True)
    files = {"__init__.py": b"# script\n", "handler.py": b"# handler\n"}
    if extra_file:
        files[extra_file[0]] = extra_file[1]
    for name, data in files.items():
        (remote / name).write_bytes(data)
    (remote / "ext-manifest.json").write_text(
        json.dumps({"files": {name: digest(data) for name, data in files.items()}}),
        encoding="utf-8",
    )
    return remote


class DiscoveryTests(unittest.TestCase):
    def test_windows_candidates_follow_live_convention_and_dedupe(self):
        paths = candidate_libraries(
            home=r"C:\Users\producer",
            platform="win32",
            environ={"OneDrive": r"C:\Users\producer\OneDrive"},
        )
        text = [str(path) for path in paths]
        self.assertEqual(len(text), len(set(text)))
        self.assertIn(str(Path(r"C:\Users\producer") / "Music" / "Ableton" / "User Library"), text)
        self.assertIn(
            str(Path(r"C:\Users\producer\OneDrive") / "Music" / "Ableton" / "User Library"), text
        )

    def test_macos_and_linux_use_their_own_roots(self):
        mac = [str(p) for p in candidate_libraries(home="/Users/p", platform="darwin")]
        self.assertEqual(mac, ["/Users/p/Music/Ableton/User Library"])
        linux = [str(p) for p in candidate_libraries(home="/home/p", platform="linux")]
        self.assertIn("/home/p/Music/Ableton/User Library", linux)

    def test_single_existing_library_is_returned(self):
        home = "/home/producer"
        wanted = Path(home) / "Music" / "Ableton" / "User Library"
        found = discover_library(home=home, platform="linux", is_dir=lambda path: path == wanted)
        self.assertEqual(found["user_library"], str(wanted))

    def test_no_or_ambiguous_library_asks_for_the_live_settings_path(self):
        with self.assertRaises(ValueError) as empty:
            discover_library(home="/home/p", platform="linux", is_dir=lambda path: False)
        self.assertIn("Live Settings", str(empty.exception))

        with self.assertRaises(ValueError) as ambiguous:
            discover_library(home="/home/p", platform="linux", is_dir=lambda path: True)
        self.assertIn("More than one", str(ambiguous.exception))


class UninstallTests(unittest.TestCase):
    def test_install_is_moved_to_a_backup_and_nothing_else_is_touched(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "User Library"
            remote = make_install(root)
            keep = root / "Remote Scripts" / "Other Script"
            keep.mkdir()
            (keep / "keep.py").write_text("keep", encoding="utf-8")
            song = root / "song.als"
            song.write_text("set", encoding="utf-8")

            report = uninstall_bridge(remote, Path(temp) / "backups")

            self.assertFalse(remote.exists())
            backup = Path(report["backup"]) / "RemoteScript"
            self.assertTrue((backup / "__init__.py").is_file())
            self.assertTrue((backup / "ext-manifest.json").is_file())
            self.assertTrue((keep / "keep.py").is_file())
            self.assertEqual(song.read_text(encoding="utf-8"), "set")
            self.assertEqual(report["locally_modified"], [])
            self.assertFalse(report["song_modified"])
            self.assertIn("copy", report["restore"])

    def test_locally_modified_and_missing_files_are_reported(self):
        with tempfile.TemporaryDirectory() as temp:
            remote = make_install(Path(temp) / "User Library")
            (remote / "handler.py").write_text("# edited\n")
            (remote / "__init__.py").unlink()

            report = uninstall_bridge(remote, Path(temp) / "backups")

            self.assertEqual(report["locally_modified"], ["handler.py"])
            self.assertEqual(report["missing"], ["__init__.py"])

    def test_wrong_destination_and_missing_install_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            wrong = Path(temp) / "Somewhere" / "EnAbleton"
            wrong.mkdir(parents=True)
            with self.assertRaises(ValueError):
                uninstall_bridge(wrong, Path(temp) / "backups")

            not_installed = Path(temp) / "User Library" / "Remote Scripts" / "EnAbleton"
            not_installed.mkdir(parents=True)
            with self.assertRaises(ValueError) as error:
                uninstall_bridge(not_installed, Path(temp) / "backups")
            self.assertIn("nothing was removed", str(error.exception))
            self.assertTrue(not_installed.is_dir())


class CommandTests(unittest.TestCase):
    def test_uninstall_command_prints_a_report_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "User Library"
            make_install(root)
            stdout = io.StringIO()
            with (
                patch("enableton.setup.Path.home", return_value=Path(temp) / "home"),
                contextlib.redirect_stdout(stdout),
            ):
                code = cli.main(["uninstall", "--user-library", str(root)])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["song_modified"], False)

    def test_uninstall_with_nothing_installed_exits_two_with_an_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "User Library"
            root.mkdir()
            stderr = io.StringIO()
            with (
                patch("enableton.setup.Path.home", return_value=Path(temp) / "home"),
                contextlib.redirect_stderr(stderr),
            ):
                code = cli.main(["uninstall", "--user-library", str(root)])
            self.assertEqual(code, 2)
            self.assertIn("error", json.loads(stderr.getvalue()))

    def test_user_library_is_optional_and_discovered(self):
        with tempfile.TemporaryDirectory() as temp:
            remote = make_install(Path(temp) / "User Library")
            with (
                patch(
                    "enableton.setup.discover_library",
                    return_value={"user_library": str(remote.parent.parent)},
                ),
                patch("enableton.setup.Path.home", return_value=Path(temp) / "home"),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(cli.main(["uninstall"]), 0)

    def test_failed_discovery_is_a_usage_error(self):
        stderr = io.StringIO()
        with (
            patch(
                "enableton.setup.discover_library",
                side_effect=ValueError("No Ableton User Library was found"),
            ),
            contextlib.redirect_stderr(stderr),
        ):
            with self.assertRaises(SystemExit) as exit_code:
                cli.main(["uninstall"])
        self.assertEqual(exit_code.exception.code, 2)
        self.assertIn("No Ableton User Library", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
