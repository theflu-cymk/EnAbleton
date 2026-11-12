"""Client config generation: no writes to a client's own settings."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from enableton import cli
from enableton.client_config import build_client_config, client_config_path


class BuildConfigTests(unittest.TestCase):
    def test_clients_share_a_deterministic_stdio_config(self):
        for client in ("claude-desktop", "cursor"):
            with self.subTest(client=client):
                config = build_client_config(client, r"C:\Tools\Python\python.exe")
                self.assertEqual(
                    config,
                    {
                        "mcpServers": {
                            "EnAbleton": {
                                "command": r"C:\Tools\Python\python.exe",
                                "args": ["-m", "enableton", "serve"],
                            }
                        }
                    },
                )
                self.assertEqual(
                    json.dumps(config, indent=2, allow_nan=False),
                    json.dumps(
                        build_client_config(client, r"C:\Tools\Python\python.exe"), indent=2
                    ),
                )

    def test_unsupported_client_and_missing_interpreter_are_refused(self):
        with self.assertRaises(ValueError):
            build_client_config("vscode", "python")
        with self.assertRaises(RuntimeError):
            build_client_config("cursor", "")

    def test_config_locations_are_reported_per_client(self):
        self.assertEqual(
            client_config_path("cursor", home=r"C:\Users\producer"),
            Path(r"C:\Users\producer") / ".cursor" / "mcp.json",
        )
        self.assertEqual(
            client_config_path(
                "claude-desktop",
                home=r"C:\Users\producer",
                appdata=r"C:\Users\producer\AppData\Roaming",
                platform="win32",
            ),
            Path(r"C:\Users\producer\AppData\Roaming") / "Claude" / "claude_desktop_config.json",
        )
        self.assertEqual(
            client_config_path("claude-desktop", home="/home/producer", platform="darwin"),
            Path("/home/producer")
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json",
        )


class CommandTests(unittest.TestCase):
    def run_cli(self, argv, executable=r"C:\Python\python.exe"):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch("enableton.client_config.sys.executable", executable):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_stdout_is_only_the_config_and_guidance_goes_to_stderr(self):
        for client in ("claude-desktop", "cursor"):
            with self.subTest(client=client):
                code, out, err = self.run_cli(["client-config", client])
                self.assertEqual(code, 0)
                config = json.loads(out)
                self.assertEqual(
                    config["mcpServers"]["EnAbleton"]["command"], r"C:\Python\python.exe"
                )
                self.assertEqual(
                    config["mcpServers"]["EnAbleton"]["args"], ["-m", "enableton", "serve"]
                )
                self.assertIn("add this entry to", err)

    def test_preparation_screen_does_not_claim_the_command(self):
        code, out, err = self.run_cli(["client-config", "cursor"])
        self.assertEqual(code, 0)
        self.assertIn("mcpServers", json.loads(out))
        self.assertNotIn("nine preparation", (out + err).casefold())

    def test_output_option_creates_only_a_new_file(self):
        with tempfile.TemporaryDirectory() as temp:
            output_path = Path(temp) / "cursor.json"
            code, out, _ = self.run_cli(["client-config", "cursor", "--output", str(output_path)])
            self.assertEqual(code, 0)
            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                json.loads(out),
            )

            code, out, err = self.run_cli(["client-config", "cursor", "--output", str(output_path)])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("already exists", err)

    def test_missing_output_directory_is_reported_not_created(self):
        with tempfile.TemporaryDirectory() as temp:
            output_path = Path(temp) / "missing" / "cursor.json"
            code, out, err = self.run_cli(["client-config", "cursor", "--output", str(output_path)])
            self.assertEqual(code, 2)
            self.assertEqual(out, "")
            self.assertIn("error", json.loads(err))
            self.assertFalse(output_path.parent.exists())


if __name__ == "__main__":
    unittest.main()
