"""The default port is fixed; the documented override reaches both sides."""

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from enableton.port import (
    DEFAULT_PORT,
    apply_client_environment,
    client_port,
    configured,
    parse,
)


class ParseTests(unittest.TestCase):
    def test_usable_ports_are_accepted(self):
        self.assertEqual(parse("1024"), 1024)
        self.assertEqual(parse(9878), 9878)
        self.assertEqual(parse(" 65535 "), 65535)

    def test_privileged_out_of_range_and_text_are_refused(self):
        for value in ("80", "0", "70000", "abc", "", "9878.5"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse(value)


class SelectionTests(unittest.TestCase):
    def test_unset_override_keeps_the_fixed_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ENABLETON_PORT", None)
            os.environ.pop("ABLETON_PORT", None)
            self.assertIsNone(configured())
            self.assertEqual(client_port(), DEFAULT_PORT)

    def test_override_sets_the_variable_the_upstream_client_reads(self):
        with patch.dict(os.environ, {"ENABLETON_PORT": "9878"}, clear=False):
            os.environ.pop("ABLETON_PORT", None)
            self.assertEqual(apply_client_environment(), 9878)
            self.assertEqual(os.environ["ABLETON_PORT"], "9878")

    def test_the_documented_override_wins_over_a_stale_upstream_variable(self):
        with patch.dict(os.environ, {"ENABLETON_PORT": "9878", "ABLETON_PORT": "9877"}):
            self.assertEqual(apply_client_environment(), 9878)
            self.assertEqual(os.environ["ABLETON_PORT"], "9878")

    def test_an_unusable_override_fails_instead_of_guessing(self):
        with patch.dict(os.environ, {"ENABLETON_PORT": "70000"}, clear=False):
            with self.assertRaises(ValueError):
                client_port()


class ProbeTests(unittest.TestCase):
    def test_the_liveness_probe_uses_the_configured_port(self):
        from enableton import prep

        seen = []

        class FakeSocket:
            def settimeout(self, _timeout):
                pass

            def connect(self, address):
                seen.append(address)

            def close(self):
                pass

        with patch.object(prep, "client_port", return_value=9999):
            with patch.object(prep.socket, "socket", return_value=FakeSocket()):
                self.assertTrue(prep.probe_live())
        self.assertEqual(seen, [("127.0.0.1", 9999)])


@unittest.skipUnless(importlib.util.find_spec("ableton_live_mcp"), "requires 1.8.1 environment")
class GeneratedBridgeTests(unittest.TestCase):
    def build(self, port):
        from enableton.bridge_builder import build

        framework = types.ModuleType("_Framework")
        control = types.ModuleType("_Framework.ControlSurface")
        control.ControlSurface = type("ControlSurface", (), {})
        old = {key: sys.modules.get(key) for key in ("_Framework", "_Framework.ControlSurface")}
        sys.modules.update({"_Framework": framework, "_Framework.ControlSurface": control})
        try:
            with tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / "EnAbleton"
                manifest = build(target, port=port)
                return manifest, (target / "__init__.py").read_text(encoding="utf-8")
        finally:
            for key, module in old.items():
                if module is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = module

    def test_the_default_is_baked_in_rather_than_read_from_live(self):
        manifest, source = self.build(None)
        self.assertEqual(manifest["port"], DEFAULT_PORT)
        self.assertIn(f"DEFAULT_PORT = {DEFAULT_PORT}", source)
        self.assertNotIn('os.environ.get("ABLETON_MCP_PORT"', source)

    def test_a_rebuilt_bridge_listens_on_the_requested_port(self):
        manifest, source = self.build(9878)
        self.assertEqual(manifest["port"], 9878)
        self.assertIn("DEFAULT_PORT = 9878", source)

    def test_an_unusable_port_is_refused_before_anything_is_written(self):
        with self.assertRaises(ValueError):
            self.build(80)


if __name__ == "__main__":
    unittest.main()
