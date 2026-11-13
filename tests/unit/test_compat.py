"""The documented Ableton Live floor is enforced, not assumed."""

import importlib.util
import unittest
from unittest.mock import patch

from enableton.compat import evaluate, parse_live_version, require_supported


class ParseTests(unittest.TestCase):
    def test_release_strings_become_comparable_tuples(self):
        self.assertEqual(parse_live_version("12.2.5"), (12, 2, 5))
        self.assertEqual(parse_live_version("12.2"), (12, 2, 0))
        self.assertEqual(parse_live_version("12"), (12, 0, 0))
        self.assertEqual(parse_live_version(" 11.3.21 "), (11, 3, 21))
        self.assertEqual(parse_live_version("13.1.4.2"), (13, 1, 4))

    def test_anything_unreadable_is_unknown_rather_than_old(self):
        for value in (None, "", "   ", "12.2 beta", "unknown", 12):
            with self.subTest(value=value):
                self.assertIsNone(parse_live_version(value))


class EvaluateTests(unittest.TestCase):
    def test_older_major_is_unsupported(self):
        self.assertIs(evaluate("11.3.21")["supported"], False)

    def test_the_documented_floor_and_newer_are_supported(self):
        for value in ("12.0", "12.2.5", "12.3.0", "13.0.1"):
            with self.subTest(value=value):
                self.assertIs(evaluate(value)["supported"], True)

    def test_unknown_stays_unverified(self):
        self.assertIsNone(evaluate("")["supported"])
        self.assertEqual(evaluate("")["minimum"], "12.0")

    def test_refusal_names_the_version_and_says_nothing_was_sent(self):
        with self.assertRaises(RuntimeError) as error:
            require_supported("11.3.21")
        message = str(error.exception)
        self.assertIn("11.3.21", message)
        self.assertIn("No command was sent", message)
        self.assertIn("Update Ableton Live", message)

    def test_supported_and_unknown_versions_do_not_raise(self):
        require_supported("12.2.5")
        require_supported("")
        require_supported(None)


@unittest.skipUnless(importlib.util.find_spec("ableton_live_mcp"), "requires 1.8.1 environment")
class ServerGateTests(unittest.TestCase):
    def call(self, info, command="delete_track"):
        from enableton import server as launcher

        calls = []
        error = None

        def send(connection, name, params):
            calls.append(name)
            return info

        with patch.object(launcher, "_upstream_send", send):
            launcher._forget_handshake()
            try:
                launcher._version_checked_send(object(), command, {"track_index": 0})
            except Exception as exc:  # the refusal is the assertion here
                error = exc
            finally:
                launcher._forget_handshake()
        return calls, error

    def test_a_live_build_below_the_floor_is_refused_before_the_command(self):
        calls, error = self.call(
            {
                "version": "1.8.1-ext.15",
                "upstream_version": "1.8.1",
                "live_version": "11.3.21",
            }
        )
        self.assertIsInstance(error, RuntimeError)
        self.assertIn("No command was sent", str(error))
        self.assertEqual(calls, ["get_script_info"])

    def test_a_supported_build_still_reaches_live(self):
        calls, error = self.call(
            {
                "version": "1.8.1-ext.15",
                "upstream_version": "1.8.1",
                "live_version": "12.2.5",
            }
        )
        self.assertIsNone(error)
        self.assertEqual(calls, ["get_script_info", "delete_track"])

    def test_a_bridge_that_reports_no_live_version_is_not_refused(self):
        calls, error = self.call({"version": "1.8.1-ext.15", "upstream_version": "1.8.1"})
        self.assertIsNone(error)
        self.assertEqual(calls, ["get_script_info", "delete_track"])


if __name__ == "__main__":
    unittest.main()
