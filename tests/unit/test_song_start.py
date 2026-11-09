"""The start screen lists nine ops and does not require a song folder."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from enableton import cli
from enableton.prep import OPS, instructions
from enableton.song_start import menu_text, payload, run


def capture(argv, tty=False):
    out = io.StringIO()
    err = io.StringIO()
    with (
        patch("enableton.song_start.probe_live", return_value=False),
        patch("sys.stdin.isatty", return_value=tty),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        code = cli.main(argv)
    return code, out.getvalue(), err.getvalue()


class MenuTests(unittest.TestCase):
    def test_handshake_shows_nine_ops_and_waits(self):
        text = instructions()
        self.assertIn(
            'When the user says "Enableton", show these nine operations and a prompt.',
            text,
        )
        self.assertNotIn('"Enableton" with prep all', text)
        for op in OPS:
            self.assertIn(op["id"], text)
            self.assertIn(op["words"], text)

    def test_tty_screen_lists_nine_ops_in_twenty_lines(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run(None, reader=lambda _prompt: "q", is_tty=lambda: True, probe=lambda: True)
        text = out.getvalue()
        self.assertEqual(code, 0)
        self.assertLessEqual(len(text.splitlines()), 20)
        self.assertIn("all", text)
        self.assertIn("Live: connected", text)
        self.assertNotIn("run this command", text)
        for op in OPS:
            self.assertIn(op["id"], text)
            self.assertIn(op["words"], text)

    def test_closed_live_still_prints_the_screen(self):
        text = menu_text(False)
        self.assertIn("Live: not connected (open Live and select EnAbleton)", text)
        self.assertLessEqual(len(text.splitlines()), 20)

    def test_piped_stdin_is_json_without_a_prompt(self):
        code, out, err = capture([])
        self.assertEqual((code, err), (0, ""))
        body = json.loads(out)
        self.assertEqual([row["id"] for row in body["options"]], [op["id"] for op in OPS])
        self.assertIn("all", body)
        self.assertNotIn(">", out)
        self.assertNotIn("run this command", out)
        self.assertFalse(body["live_changes"])
        self.assertFalse(body["playback_started"])

    def test_start_json_matches_the_ops(self):
        code, out, err = capture(["start", "--json"], tty=True)
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(
            [row["id"] for row in json.loads(out)["options"]],
            [row["id"] for row in payload(False)["options"]],
        )

    def test_quit_and_eof_exit_cleanly(self):
        for answer in ("q",):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = run(
                    None, reader=lambda _prompt: answer, is_tty=lambda: True, probe=lambda: False
                )
            self.assertEqual(code, 0)
            self.assertIn("adopt", out.getvalue())

        def boom(_prompt):
            raise EOFError

        self.assertEqual(run(None, reader=boom, is_tty=lambda: True, probe=lambda: False), 0)

    def test_free_text_after_the_menu_is_two_lines(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = run(
                None,
                reader=lambda _prompt: "make the bass twice as long",
                is_tty=lambda: True,
                probe=lambda: False,
            )
        self.assertEqual(code, 0)
        tail = out.getvalue().strip().splitlines()[-2:]
        self.assertEqual(
            tail,
            [
                "make the bass twice as long",
                "Hand this to your assistant: make the bass twice as long (MCP server EnAbleton)",
            ],
        )

    def test_free_text_argv_does_not_probe_or_print_the_menu(self):
        out = io.StringIO()
        err = io.StringIO()

        def boom():
            raise AssertionError("probed")

        with (
            patch("enableton.prep.probe_live", side_effect=boom),
            patch("enableton.song_start.probe_live", side_effect=boom),
            contextlib.redirect_stdout(out),
            contextlib.redirect_stderr(err),
        ):
            code = cli.main(["make the bass twice as long"])
        self.assertEqual(code, 0)
        self.assertEqual(err.getvalue(), "")
        self.assertEqual(
            out.getvalue().splitlines(),
            [
                "make the bass twice as long",
                "Hand this to your assistant: make the bass twice as long (MCP server EnAbleton)",
            ],
        )
        self.assertNotIn("adopt", out.getvalue())
