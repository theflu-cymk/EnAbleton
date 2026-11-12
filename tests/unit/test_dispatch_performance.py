import ast
from pathlib import Path
import unittest


class DispatchChecks(unittest.TestCase):
    def dispatch(self, info):
        source = Path(__file__).resolve().parents[2] / "src/enableton/server.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        wanted = {"dispatch", "_handshake_info", "_require_version", "_forget_handshake"}
        body = [
            node
            for node in tree.body
            if (isinstance(node, ast.FunctionDef) and node.name in wanted)
            or (
                isinstance(node, ast.Assign)
                and any(getattr(target, "id", None) == "_handshake" for target in node.targets)
            )
        ]
        self.assertEqual(len(body), len(wanted) + 1)
        calls = []
        connection = object()
        failing = {"command": None}

        def send(conn, command, params):
            self.assertIs(conn, connection)
            calls.append(command)
            if command == failing["command"]:
                raise OSError("socket closed by Live")
            return info if command == "get_script_info" else {"done": True}

        env = dict(
            get_ableton_connection=lambda: connection,
            _upstream_send=send,
            COMPATIBLE_VERSIONS={"valid"},
            UPSTREAM_VERSION="1.8.1",
        )
        exec(compile(ast.Module(body=body, type_ignores=[]), "server", "exec"), env)
        return env["dispatch"], calls, failing

    def test_one_handshake_covers_every_operation_on_a_connection(self):
        fn, calls, _failing = self.dispatch(
            dict(version="valid", upstream_version="1.8.1", capabilities=["edit"])
        )
        self.assertEqual(fn("edit", {}), {"done": True})
        self.assertEqual(fn("edit", {}), {"done": True})
        self.assertEqual(calls, ["get_script_info", "edit", "edit"])

    def test_incompatible_or_missing_capability_never_sends_operation(self):
        for info in [
            dict(version="old", upstream_version="1.8.1", capabilities=["edit"]),
            dict(version="valid", upstream_version="old", capabilities=["edit"]),
            dict(version="valid", upstream_version="1.8.1", capabilities=[]),
        ]:
            fn, calls, _failing = self.dispatch(info)
            with self.assertRaises(RuntimeError):
                fn("edit", {})
            self.assertEqual(calls, ["get_script_info"])

    def test_a_failed_send_re_guards_the_next_operation(self):
        info = dict(version="valid", upstream_version="1.8.1", capabilities=["edit"])
        fn, calls, failing = self.dispatch(info)
        fn("edit", {})
        failing["command"] = "edit"
        with self.assertRaises(OSError):
            fn("edit", {})
        failing["command"] = None
        info["version"] = "old"
        with self.assertRaises(RuntimeError):
            fn("edit", {})
        self.assertEqual(calls, ["get_script_info", "edit", "edit", "get_script_info"])
