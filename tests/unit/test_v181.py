"""Adapter checks; skipped in the legacy environment without upstream 1.8.1."""

import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch


@unittest.skipUnless(importlib.util.find_spec("ableton_live_mcp"), "requires 1.8.1 environment")
class MigrationTests(unittest.TestCase):
    def test_old_bridge_is_blocked_before_upstream_edit(self):
        from enableton import server as launcher

        calls = []

        def send(connection, command, params):
            calls.append(command)
            return {"version": "1.7.1-bass.1"}

        with patch.object(launcher, "_upstream_send", send):
            with self.assertRaisesRegex(RuntimeError, "older bridge"):
                launcher._version_checked_send(object(), "delete_track", {"track_index": 0})
        self.assertEqual(calls, ["get_script_info"])

    def test_matching_bridge_allows_upstream_read(self):
        from enableton import server as launcher

        calls = []

        def send(connection, command, params):
            calls.append(command)
            return (
                {"version": "1.8.1-ext.1", "upstream_version": "1.8.1"}
                if command == "get_script_info"
                else {"tempo": 150}
            )

        with patch.object(launcher, "_upstream_send", send):
            self.assertEqual(
                launcher._version_checked_send(object(), "get_session_info"), {"tempo": 150}
            )
        self.assertEqual(calls, ["get_script_info", "get_session_info"])

    def test_generated_dispatch_and_upstream_preservation(self):
        from enableton.bridge_builder import build

        framework = types.ModuleType("_Framework")
        control = types.ModuleType("_Framework.ControlSurface")
        control.ControlSurface = type("ControlSurface", (), {})
        old = {key: sys.modules.get(key) for key in ("_Framework", "_Framework.ControlSurface")}
        sys.modules.update({"_Framework": framework, "_Framework.ControlSurface": control})
        try:
            with tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / "AbletonMCP"
                manifest = build(target)
                spec = importlib.util.spec_from_file_location(
                    "migration_test_bridge",
                    target / "__init__.py",
                    submodule_search_locations=[str(target)],
                )
                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)
                cls = module.AbletonMCP
                instance = object.__new__(cls)
                info = cls._ALL_COMMANDS["get_script_info"](instance, {})
                self.assertEqual(info["upstream_version"], "1.8.1")
                for command in (
                    "write_clip_envelope",
                    "get_clip_envelope",
                    "set_sound_design_parameters",
                    "get_sound_design_parameters",
                    "create_midi_track",
                    "get_clip_notes",
                    "batch",
                    "undo",
                ):
                    self.assertIn(command, info["capabilities"])
                instance._get_clip_envelope = lambda args: args
                self.assertEqual(
                    cls._ALL_COMMANDS["get_clip_envelope"](instance, {"guard": 1}), {"guard": 1}
                )
                self.assertEqual(manifest["upstream_version"], "1.8.1")
        finally:
            for key, value in old.items():
                if value is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = value


if __name__ == "__main__":
    unittest.main()
