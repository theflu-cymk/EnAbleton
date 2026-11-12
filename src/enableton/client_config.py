"""Generate stdio MCP client configuration for supported clients.

The generated entry launches the interpreter running this package, so a client
starts the same EnAbleton installation instead of whichever ``uv`` or
``enableton`` happens to be first on the client's ``PATH``. Nothing here reads or
edits an existing client configuration; the caller prints or writes a new file.
"""

import os
from pathlib import Path
import sys

CLIENTS = ("claude-desktop", "cursor")
SERVER_NAME = "EnAbleton"

_DISPLAY = {"claude-desktop": "Claude Desktop", "cursor": "Cursor"}


def executable_path(executable=None):
    """Return the interpreter a client should launch, or explain why it cannot."""

    executable = sys.executable if executable is None else executable
    if not executable:
        raise RuntimeError("the current Python executable path is unavailable")
    return executable


def build_client_config(client, executable=None):
    """Return a stdio server entry for ``client`` using this installation's Python."""

    if client not in CLIENTS:
        raise ValueError(f"unsupported client: {client}")
    return {
        "mcpServers": {
            SERVER_NAME: {
                "command": executable_path(executable),
                "args": ["-m", "enableton", "serve"],
            }
        }
    }


def client_config_path(client, home=None, appdata=None, platform=None):
    """Return where ``client`` reads its stdio server list.

    The path is guidance for the producer, not a fact this package verifies, and
    a client may accept a different location. ``--output`` never writes there.
    """

    if client not in CLIENTS:
        raise ValueError(f"unsupported client: {client}")
    home = Path.home() if home is None else Path(home)
    if client == "cursor":
        return home / ".cursor" / "mcp.json"
    platform = sys.platform if platform is None else platform
    if platform.startswith("win"):
        base = Path(appdata or os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        return base / "Claude" / "claude_desktop_config.json"
    if platform == "darwin":
        return home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return home / ".config" / "Claude" / "claude_desktop_config.json"


def client_display(client):
    """Return the client's product name for guidance text."""

    if client not in CLIENTS:
        raise ValueError(f"unsupported client: {client}")
    return _DISPLAY[client]
