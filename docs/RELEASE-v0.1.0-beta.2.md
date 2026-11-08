# EnAbleton v0.1.0-beta.2 (draft)

Draft notes for the next beta. This tree is not tagged yet: Python version
`0.1.0b1`, bridge protocol `1.8.1-ext.7`.

## Included

- 204 MCP tools: 156 pinned upstream 1.8.1 controls plus 48 EnAbleton additions.
- Guarded Live writes for track and clip deletion, Session clip resizing, audio Warp
  state (warping, warp_mode, gain, pitch coarse/fine), track monitoring state and clip
  `warp_mode` via `set_clip`.
- Note lifecycle by ID in Session and Arrangement: full-range reads, in-place
  modification, verified insert and verified delete.
- Song-initiation `--apply` now applies every supported change per step and records
  platform limits as skipped steps with a reason; `--strict` keeps all-or-nothing
  preflight.
- Carried from beta.1: bass recipes, production references, mastering plans, nested
  device and rack control, warp diagnostics, duplicate-only warp repair, the remix
  workflow, audio problem scans and live lint.

## Validation

- 225 unit tests pass; `ruff check` and `ruff format --check` are clean.
- MCP transport verification: 204 tools, no Live mutations.
- Release check: `bridge_protocol 1.8.1-ext.7`, 8 installed files verified,
  `song_modified: false`.
- Live smoke run on Windows with Ableton Live 12.2.5: 22/22 checks on a scratch track
  that the run created and deleted; the user's tracks and tempo were unchanged.
  Warp writes are covered by unit tests and capability checks; they need the ext.7
  script activation (restart Live) for on-Live confirmation.

## Limits

Live exposes no group-creation API and no writable Arrangement clip extent. Audio base
tempo, Warp on MIDI clips and hidden plug-in parameters stay unavailable. EnAbleton
does not automate the GUI and does not certify every Live version. See
[LIMITATIONS.md](LIMITATIONS.md) and [ACCESS.md](ACCESS.md).

## Install

Follow [INSTALLATION.md](INSTALLATION.md), then restart Live so the ext.7 bridge loads.
No PyPI publication is configured; assets are the wheel, sdist and checksums.
