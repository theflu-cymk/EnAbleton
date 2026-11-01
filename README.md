# EnAbleton

An MCP extension layer for Ableton Live: production recipes, guarded nested
device control, and warp diagnostics with reversible repair previews.

**First release: v0.1.0-beta.1.** Python version: `0.1.0b1`.
Built on [`mcp-server-ableton-live==1.8.1`](https://github.com/wstierhout/ableton-live-mcp),
with **191 MCP tools: 156 upstream controls and 35 EnAbleton additions**.
This is a beta, not an Ableton-endorsed product or an unrestricted Live API.

## What it adds

- **Production library:** 13 original native bass patches, rhythmic MIDI and
  modulation tools, seven mastering techniques, artist-method references and
  47 searchable source-linked production entries.
- **Deeper control:** nested devices on tracks, returns and Main; formatted
  parameter inspection; guarded batches; rack-chain mixers; full-range Session
  and Arrangement MIDI reads and note-ID editing.
- **Warp workflow:** complete marker reads, tempo and half/double-time estimates,
  candidate downbeats, groove-aware alignment, drift and loop-seam review,
  reference-event matching and warp-mode guidance.
- **Reversible repair:** explicit marker moves on a non-overlapping duplicate,
  with expiring previews, source/target fingerprints, timing backups, readback
  checks and a preserved original.
- **Operational safeguards:** bounded audio workers, cache invalidation,
  per-clip batch failures, capability/version checks and recoverable installation.

[Feature catalog](docs/FEATURES.md) · [Recipe catalog](docs/RECIPE_CATALOG.md) · [All 191 tools](docs/TOOL_CATALOG.md) ·
[Installation](docs/INSTALLATION.md) · [Warp workflow](docs/WARP.md) ·
[Limitations](docs/LIMITATIONS.md) · [Changelog](CHANGELOG.md)

## Quick start

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Git.
Python 3.12–3.14 is required; uv can provide it.

```powershell
git clone https://github.com/theflu-cymk/EnAbleton.git E:\projects\Ableton
cd E:\projects\Ableton
uv sync --locked
uv run enableton install --user-library "C:\path\to\your\actual\User Library"
```

Use the User Library path shown in Live Settings. Save your set, fully restart
Live, and select **EnAbleton** as the Control Surface with Input/Output **None**.
Disable the previous AbletonMCP control-surface row; two bridges must not share
port 9877. Hardware-controller rows stay as they are.

Add this stdio server to an MCP client, then restart/reconnect that client:

```json
{
  "mcpServers": {
    "EnAbleton": {
      "command": "uv",
      "args": ["--directory", "E:\\projects\\Ableton", "run", "--locked", "enableton", "serve"]
    }
  }
}
```

```powershell
uv run enableton doctor --user-library "C:\path\to\your\actual\User Library" --json
```

Ask: **“Read the current tempo and track names. Do not change the set.”**
The full installation guide includes Codex configuration, upgrades and rollback.
The repository is private; GitHub access is required to clone it. It is not
published to PyPI, so `uvx enableton` is not an installation instruction.

## Honest limits

Tempo/downbeat results are estimates; audible beat placement still needs
listening. The added audio analyzer supports integer PCM WAV, not arbitrary
audio formats. Installing tools never changes a Live set. Actual Live marker
repair APIs remain capability-gated and require real readback; synthetic tests
do not certify sound quality. GUI-only commands, hidden plug-in controls, audio
to MIDI conversion and track reordering are not added here.

The reference website remains a separate project; the underlying recipe data is
included here and searchable over MCP. No commercial audio, presets or Live sets
are distributed. This server works with a compatible local MCP client; a skill
file alone does not connect Grok or another hosted chatbot to your computer.

## Development

```powershell
uv sync --locked
uv run python -m unittest discover -s tests/unit -p "test_*.py"
uv run python tests/integration/test_transport.py
uv run ruff check .
uv run ruff format --check .
uv build
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [release policy](docs/RELEASING.md).
MIT licensed; upstream notices are preserved in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
