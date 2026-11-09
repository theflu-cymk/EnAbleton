"""`enableton initiate`: ask-first entry point for the default preset."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from enableton import cli, initial_prep


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = cli.main(argv)
    return code, out.getvalue()


def workflow(config_dir, mode, *extra):
    return [
        "initiate",
        "--song-root",
        "/music",
        "--song-name",
        "Song",
        "--mode",
        mode,
        "--live",
        "--keep-config",
        str(Path(config_dir) / "initiate.yaml"),
        *extra,
    ]


class AskFirstTests(unittest.TestCase):
    def test_no_mode_asks_and_writes_nothing(self):
        code, out = run(["initiate", "--song-root", "/music", "--song-name", "Song"])
        self.assertEqual(code, 2)
        payload = json.loads(out)
        self.assertEqual(payload["question"], initial_prep.ENTRY_QUESTION)
        self.assertEqual(set(payload["modes"]), {"lint", "prepare"})
        self.assertEqual(set(payload["phases"]), set(initial_prep.PHASES))
        self.assertIn("--mode", payload["next"])

    def test_mode_without_a_source_is_rejected(self):
        with self.assertRaises(SystemExit) as caught:
            run(["initiate", "--song-root", "/music", "--song-name", "S", "--mode", "lint"])
        self.assertEqual(caught.exception.code, 2)

    def test_config_write_failure_is_json_not_a_traceback(self):
        out = io.StringIO()
        argv = workflow(tempfile.gettempdir(), "lint")
        with (
            patch.object(initial_prep, "write_config", side_effect=OSError("exists")),
            contextlib.redirect_stdout(out),
        ):
            code = cli.main(argv)
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(out.getvalue())["error"], "exists")


class ModeTests(unittest.TestCase):
    def test_lint_mode_never_passes_apply(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            with patch(
                "enableton.song_init.main", side_effect=lambda argv: calls.append(argv) or 0
            ):
                code = cli.main(workflow(temp, "lint"))
            self.assertTrue((Path(temp) / "initiate.yaml").is_file())
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("--lint", calls[0])
        self.assertNotIn("--apply", calls[0])

    def test_prepare_mode_audits_before_applying(self):
        calls = []
        ran = []
        with tempfile.TemporaryDirectory() as temp:
            with (
                patch(
                    "enableton.song_init.main",
                    side_effect=lambda argv: calls.append(list(argv)) or 0,
                ),
                patch(
                    "enableton.prep.run_all",
                    side_effect=lambda source, options=None: ran.append(options or {}) or [],
                ),
            ):
                code = cli.main(workflow(temp, "prepare"))
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertIn("--lint", calls[0])
        self.assertNotIn("--apply", calls[0])
        self.assertEqual(len(ran), 1)
        self.assertFalse(ran[0].get("plan"))

    def test_prepare_stops_when_the_audit_cannot_capture(self):
        calls = []
        with tempfile.TemporaryDirectory() as temp:
            with patch(
                "enableton.song_init.main", side_effect=lambda argv: calls.append(argv) or 2
            ):
                code = cli.main(workflow(temp, "prepare"))
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
