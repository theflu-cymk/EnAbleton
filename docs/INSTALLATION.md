# Installation and upgrades

## Requirements and validation status

- Ableton Live 12. The development host runs **Live 12.2.5 Suite on Windows**.
- A local MCP client supporting stdio: Codex, Claude Desktop, Cursor or another
  compatible client. This guide does not install or configure an LLM provider.
- Git, uv and Python >=3.12,<3.15. The lock file pins Python dependencies.
- Operator/other instruments used by executable recipes must be available in
  your edition. Missing devices cause explicit errors; they are not substituted.

Unit tests use fake Live objects and synthetic audio; they are not a substitute
for a full Live compatibility matrix. macOS/Linux package tests do not imply
that Ableton is installed or supported on Linux.

## 1. Clone and install the local client

Install the current **main** branch. Do not check out `v0.1.0-beta.1`. That
prerelease is retired (191 tools, bridge protocol `1.8.1-ext.5`).

```powershell
git clone https://github.com/theflu-cymk/EnAbleton.git E:\projects\Ableton
cd E:\projects\Ableton
uv sync --locked
uv run enableton --version
uv tool install --from . enableton
```

`uv tool install --from . enableton` puts `enableton` on your PATH, so it runs
from any directory. `uv run enableton` stays the command inside this checkout.
The no-argument screen does not read the current directory.

Do not put a GitHub token into the URL or client configuration. Use Git's normal
credential manager for private-repository authentication. On macOS choose an
appropriate absolute checkout directory and use the equivalent commands.

## 2. Install the Live-side Remote Script

In Live Settings, locate **Library → User Library** and copy that exact path.
Do not guess it from Documents or OneDrive: customized locations are common.

```powershell
uv run enableton install --user-library "C:\path\shown\in\Live\User Library"
```

This builds the Remote Script from the pinned upstream package and installs it
at `<User Library>/Remote Scripts/EnAbleton`. It validates staged hashes and
syntax, preserves an existing installation in `~/.enableton/backups`, and rolls
back replaced files if installation fails. Existing files require `--replace`;
locally modified manifest-tracked files are refused for manual review.

Save your Live set and **fully quit and restart Live**. Toggling a control-surface
row can reuse cached Python modules. In **Settings → Tempo & MIDI**, select
**EnAbleton**, Input **None**, Output **None**. Keep hardware-controller rows.
The **AbletonMCP** control surface is retired. Remove that Remote Script from
Live's scan path so it cannot listen on port 9877 beside EnAbleton.

## 3. Configure your MCP client

Use the absolute repository path. The `--directory` option makes the command
independent of the client's working directory. Start with one Ableton MCP server
entry rather than parallel old/new configurations.

### Codex TOML

Add or update the appropriate server entry in your Codex configuration:

```toml
[mcp_servers.enableton]
command = "uv"
args = ["--directory", "E:\\projects\\Ableton", "run", "--locked", "enableton", "serve"]
startup_timeout_sec = 60
```

### JSON-based clients

See [examples/mcp.json](../examples/mcp.json). Replace the path if your checkout
is elsewhere. Restart or reconnect the client after changing the entry.

If uv is not on the client's PATH, replace `uv` with its absolute executable
path. If dependencies cannot be resolved, run `uv sync --locked` in a terminal
first; do not repeatedly launch servers with a failing installation.

## 4. Verify before editing

```powershell
uv run enableton doctor --user-library "C:\path\shown\in\Live\User Library" --json
```

`ok: true` requires matching installed file hashes, upstream protocol and the
running EnAbleton distribution version. Installed files are not proof that Live
has reloaded them. The stock upstream doctor compares against unmodified
upstream source, so use EnAbleton's doctor for the extended script.

First MCP request: “Read tempo and track names; do not edit or start playback.”
Then inspect `describe_live_access` and `describe_warp_workflow`.

## Updates and rollback

1. Save the Live set and stop active edits.
2. Stay on main for the current bridge, then run `uv sync --locked`. The tag
   `v0.1.0-beta.1` is retired.
3. Run `uv run enableton install --user-library "..." --replace`.
4. Fully restart Live, reconnect the client and rerun doctor.

The installer prints a backup path. To roll back, quit Live, restore that
backup's `RemoteScript` files to `<User Library>/Remote Scripts/EnAbleton`, check
out the matching older client tag and run `uv sync --locked`. Restart both.
Backups and reports are local and are never included in release assets.

## Troubleshooting

- **Connection refused:** Live must be running with EnAbleton selected and
  dialogs dismissed. Check only one bridge is enabled.
- **Wrong running version:** fully restart Live; do not rely on toggling rows.
- **Unknown capability:** reconnect the client after installing the matching
  script; do not send newer write commands to an old bridge.
- **Tool timeout:** inspect state before retrying. An interrupted operation may
  have completed. Warp preview tokens are single-use.
- **Unavailable plug-in parameters:** Live only exposes parameters made
  available by the plug-in. EnAbleton cannot read its hidden GUI internals.
- **Unsupported audio:** added warp analysis currently accepts integer PCM WAV.
  Convert a copy externally; keep the original file intact.

The bridge binds loopback by default. Do not expose or forward port 9877.
