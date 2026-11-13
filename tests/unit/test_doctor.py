"""doctor names EnAbleton, not the retired upstream script, when nothing answers."""

import unittest

from enableton.doctor import _connection_error


class ConnectionErrorTests(unittest.TestCase):
    def message(self):
        return RuntimeError(
            "Not connected to Ableton. Start Live, select AbletonMCP as the Control Surface "
            "(Settings > Tempo & MIDI > MIDI), set Input/Output to None, and run "
            "`ableton-live-mcp doctor`."
        )

    def test_the_retired_script_is_not_named(self):
        result = _connection_error(self.message())
        self.assertNotIn("AbletonMCP", result["connection_error"])
        self.assertNotIn("AbletonMCP", result["connection_detail"])
        self.assertNotIn("ableton-live-mcp doctor", result["connection_detail"])

    def test_the_guidance_names_enableton_and_a_restart(self):
        message = _connection_error(self.message())["connection_error"]
        self.assertIn("EnAbleton", message)
        self.assertIn("Control", message)
        self.assertIn("fully restart Live", message)

    def test_an_unrelated_reason_is_kept_for_debugging(self):
        result = _connection_error(RuntimeError("Something else broke"))
        self.assertEqual(result["connection_detail"], "Something else broke.")


if __name__ == "__main__":
    unittest.main()
