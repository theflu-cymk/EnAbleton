import ast
from pathlib import Path
import unittest


class DispatchChecks(unittest.TestCase):
    def dispatch(self, info):
        source = Path(__file__).resolve().parents[2] / "src/enableton/server.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        function = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "dispatch"
        )
        calls = []
        connection = object()

        def send(conn, command, params):
            self.assertIs(conn, connection)
            calls.append(command)
            return info if command == "get_script_info" else {"done": True}

        env = dict(
            get_ableton_connection=lambda: connection,
            _upstream_send=send,
            COMPATIBLE_VERSIONS={"valid"},
            UPSTREAM_VERSION="1.8.1",
        )
        exec(compile(ast.Module(body=[function], type_ignores=[]), "dispatch", "exec"), env)
        return env["dispatch"], calls

    def test_supported_operation_needs_only_two_calls(self):
        fn, calls = self.dispatch(
            dict(version="valid", upstream_version="1.8.1", capabilities=["edit"])
        )
        self.assertEqual(fn("edit", {}), {"done": True})
        self.assertEqual(calls, ["get_script_info", "edit"])

    def test_incompatible_or_missing_capability_never_sends_operation(self):
        for info in [
            dict(version="old", upstream_version="1.8.1", capabilities=["edit"]),
            dict(version="valid", upstream_version="old", capabilities=["edit"]),
            dict(version="valid", upstream_version="1.8.1", capabilities=[]),
        ]:
            fn, calls = self.dispatch(info)
            with self.assertRaises(RuntimeError):
                fn("edit", {})
            self.assertEqual(calls, ["get_script_info"])

    def test_each_operation_gets_a_fresh_guard(self):
        info = dict(version="valid", upstream_version="1.8.1", capabilities=["edit"])
        fn, calls = self.dispatch(info)
        fn("edit", {})
        info["version"] = "old"
        with self.assertRaises(RuntimeError):
            fn("edit", {})
        self.assertEqual(calls, ["get_script_info", "edit", "get_script_info"])
