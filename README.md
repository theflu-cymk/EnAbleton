# EnAbleton

An MCP extension layer for Ableton Live: production recipes, guarded nested
device control, and warp diagnostics with reversible repair previews.

**Current install: the main branch.** Python version: `0.1.0b1`.
Bridge protocol: `1.8.1-ext.15`.
Built on [`mcp-server-ableton-live==1.8.1`](https://github.com/wstierhout/ableton-live-mcp),
with **242 MCP tools: 156 upstream controls and 86 EnAbleton additions**.
The tagged prerelease `v0.1.0-beta.1` (191 tools, protocol `1.8.1-ext.5`) is retired.
This is a beta, not an Ableton-endorsed product or an unrestricted Live API.

## What it adds

- **Production library:** 13 original native bass patches, rhythmic MIDI and
  modulation tools, seven mastering techniques, artist-method references and
  50 searchable production reference entries, 45 with primary sources.
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

[Next-release roadmap](docs/ROADMAP-v0.2.0.md) · [Feature catalog](docs/FEATURES.md) · [Recipe catalog](docs/RECIPE_CATALOG.md) · [Current tool catalog](docs/TOOL_CATALOG.md) ·
[Installation](docs/INSTALLATION.md) · [Warp workflow](docs/WARP.md) ·
[Limitations](docs/LIMITATIONS.md) · [Changelog](CHANGELOG.md)

## Reusable remix creation (unreleased)

[Half-time remix guide](docs/REMIX_WORKFLOW.md) · [Starter config](examples/remix/rock-flip.json)

Ask **“Guide a rock-to-dubstep or riddim flip, keeping the riff and chorus singer.”**
Plan the musical layers, propose conservative MIDI cleanup, bind aligned stems,
render smooth audio, build owned Live lanes, capture a preview and compare at
matched loudness. Changed source MIDI or pulse controls can be prepared and rebuilt
without duplicate tracks. Start with `uv run enableton remix-guide`; the complete
loop uses `remix-prepare`, `remix-build`, `remix-preview` and `remix-compare`.
The current development catalog has 242 tools (156 upstream, 86 additions).
Arrangement audio import, rack blend macros, Serum parameter aliases and a 4/4
song-draft guide are in that catalog. `describe_tool_families` maps the new
names onto the existing ones.

## Song initiation and Live linting (unreleased)

[Live lint guide](docs/LIVE_LINT.md) · [Workflow guide](docs/SONG_INITIATION.md) ·
[Example YAML](examples/song-init/initiation.yaml) ·
[Reusable prompt](docs/prompts/SONG_INITIATION_PROMPT.md)

```powershell
# nine preparation steps for the open set; Live is probed and is not required
uv run enableton
uv run enableton start
uv run enableton lint "F:\ableton songs\In Hell\configs\initiation.yaml" --live
# default initial preparation: asks prepare or lint first
uv run enableton initiate --song-root "F:\ableton songs" --song-name "In Hell"
# name tracks, mute originals; add --plan to preview
uv run enableton prepare-tracks --live
# load stock placeholders for MIDI tracks that have notes and no instrument
uv run enableton assign-instruments --live
# lower unity gain, enable Utility DC, and load one gentle Compressor
uv run enableton repair-audio --live
# set Warp modes for layers that are already warped; add --plan to preview
uv run enableton align-tracks --live
```

Reads the running set and reports actual naming, MIDI, media, Warp, timing and
organization findings. Linting is read-only; explicit `--fix` supports guarded
names/colors with readback and re-lint. Other repairs are reported, not silently
pretended complete. Folder creation and cleanup planning remain separate stages.

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
The AbletonMCP control surface is retired. Do not enable it, and do not leave
its Remote Script where Live can select it. Two bridges must not share port
9877. Hardware-controller rows stay as they are.

`uv run enableton client-config claude-desktop` (or `cursor`) prints the entry
with this installation's interpreter and names the client's config file. Add it
there and restart the client. Manual entry, if you prefer a checkout-relative
command:

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

## Audio problem scan

Use `enableton scan-audio PATH.wav` or the read-only MCP tools
`scan_audio_problems` / `scan_clip_audio_problems` for timestamped review candidates
and targeted repair suggestions. See [audio scan coverage and usage](docs/AUDIO_SCAN.md).
No automatic processing or Live edits.
