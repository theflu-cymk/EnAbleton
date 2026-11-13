# EnAbleton v0.1.0-beta.2

Second beta of the MVP. Python version `0.1.0b2`, Git tag `v0.1.0-beta.2`,
bridge protocol `1.8.1-ext.15`, 242 tools (156 upstream, 86 additions).

This supersedes the earlier draft of this file, which described 204 tools and
protocol `ext.8`. Those numbers were never released.

## What this beta is

A locally installed MCP server plus a generated Ableton Live Remote Script. It
prepares an open Live set, inspects and edits devices, clips, notes and warp
data with guarded writes, and reports what it cannot do rather than guessing.
Install it from this repository at the tag below; no PyPI publication is
configured.

## Supported platform

Windows with Ableton Live 12 or later. macOS is untested and unsupported for
this beta. Live builds below 12.0 are refused before any command is sent, and
editions and individual 12.x builds remain unverified. See
[LIMITATIONS.md](LIMITATIONS.md).

## Changes since v0.1.0-beta.1

- Refuse Live calls below the documented Live 12 floor, before a command is
  sent; the bridge reports the build it runs inside and `doctor` shows it.
- `enableton setup`: read-only first-run check with the commands still needed.
- `enableton uninstall`: timestamped backup, modified files listed, no Live set
  touched.
- User Library discovery for `install`, `doctor` and `uninstall`; an explicit
  path still wins.
- `enableton client-config claude-desktop|cursor`: per-installation MCP entry.
- `enableton` with no arguments shows nine preparation steps; `--plan`
  previews and `all` runs them in order.
- Fixed loopback port 9877 with an `ENABLETON_PORT` / `--port` override baked
  into the generated script, and a mismatch reported by `doctor`.
- Proprietary end-user licence, terms of sale with no refunds, and a
  local-only privacy statement.

## Install

```powershell
git clone https://github.com/theflu-cymk/EnAbleton.git E:\projects\Ableton
cd E:\projects\Ableton
git checkout v0.1.0-beta.2
uv sync --locked
uv run enableton setup
uv run enableton install
```

Save the set, fully quit Live, then select only **EnAbleton** in
Settings → Tempo & MIDI with Input and Output set to None. Run
`uv run enableton doctor` before editing anything. Full steps and
troubleshooting are in [INSTALLATION.md](INSTALLATION.md).

## Evidence in this beta

What is verified: unit tests over fake Live objects, an MCP transport test (242
tools), installation, hashing, backup and rollback paths, and lint/format/CI on
Windows and Linux. What is not verified: any of it running against a real Live
installation. The three workflows in the release checklist have not been
recorded on a Live host, so no compatibility or audio-quality claim is made. See
[product/WORKFLOWS.md](product/WORKFLOWS.md).

## Licensing

EnAbleton is licensed, not sold: [../LICENSE](../LICENSE). Sale terms, the
no-refund policy and the support channel are in [TERMS.md](TERMS.md). Data
handling is in [PRIVACY.md](PRIVACY.md). Upstream MIT notices are preserved in
[../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

Assets for this tag include the Python wheel, source distribution and SHA-256
checksums. This is a prerelease: the licence, the support address and the
governing-law line may change before a stable release.
