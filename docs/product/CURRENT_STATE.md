# Current product and architecture assessment

This assessment describes the checked-out repository, not a prior release
snapshot. Claims below are tied to the listed files. It does not certify a
running Ableton installation or current behavior on a Live host.

## Verified current state

| Area | Evidence in this checkout |
| --- | --- |
| Product shape | Python MCP server/extension over the pinned `mcp-server-ableton-live` package; `src/enableton/server.py`, `pyproject.toml`, README. The Live-side script is generated from the pinned upstream package by `src/enableton/bridge_builder.py`. |
| Versions | `pyproject.toml` and `src/enableton/__init__.py` report EnAbleton `0.1.0b1`; `src/enableton/bridge_version.py` reports upstream `1.8.1` and protocol `1.8.1-ext.15`. README says 242 tools (156 upstream, 86 additions), and `docs/TOOL_CATALOG.md` is generated from `0.1.0b1` with those counts. These versions are distinct. |
| Installer and setup | CLI `install` and `doctor` require `--user-library`; `install` supports reviewed replacement. `installer.py` validates a generated manifest, verifies hashes, backs up an existing install and attempts rollback. Installation reports `song_modified: false`. `INSTALLATION.md` gives a manual Live restart and Control Surface selection. |
| Diagnostics and configuration | `doctor` checks installation/running-version state. The CLI has no first-run configurator or uninstall command; no port-selection option is present in the CLI. `INSTALLATION.md` documents loopback port 9877. These are gaps against the requested UX, not claims about every upstream mechanism. |
| MCP clients | `INSTALLATION.md` names Claude Desktop and Cursor among compatible stdio clients; `examples/mcp.json` is a static JSON example and currently includes a sample absolute path. `enableton client-config claude-desktop\|cursor` now prints a per-installation entry and a new-file `--output` target; it does not edit client settings (see `CHANGELOG.md`). |
| Existing capabilities | Source and catalogs cover guarded track/clip/device operations, arrangement/song workflows, warp inspection/repair, installation and diagnostics. `docs/FEATURES.md` and `docs/TOOL_CATALOG.md` describe limits and tool effects. The supplied three launch workflows still need end-to-end product definitions and acceptance evidence. |
| Tests and build | `tests/unit/` contains unit tests for installation, integrity, Live adapters, workflows and package behavior; `tests/integration/test_transport.py` covers MCP transport. `AGENTS.md` specifies unit, transport and Ruff commands for code changes and wheel/resource checks before release. This planning task does not run code or Live tests. |
| Release/docs assets | Root README, `CHANGELOG.md`, `docs/INSTALLATION.md`, `docs/RELEASING.md`, `docs/LIMITATIONS.md`, `LICENSE`, `SECURITY.md`, notices and generated catalog are present. README contains a quick-start section; installation docs contain troubleshooting. No EULA, privacy policy, refund policy, support email/contact or demo video was found in the repository. |
| Repository state | At inspection, `git status --short` showed no existing changes; recent history includes commits through 2026-11-09. No root/docs MISSION or SPEC file was found. |

## Important discrepancies and unknowns

- `docs/RELEASE-v0.1.0-beta.2.md` is explicitly a draft and describes 204
  tools/protocol `ext.8`; current README, generated tool catalog and protocol
  source identify `0.1.0b1`, 242 tools and `ext.15`. Treat beta.2 as stale
  planning material, not evidence of current release status.
- `docs/INSTALLATION.md` identifies Windows Live 12 as the current
  development-host baseline, and `docs/LIMITATIONS.md` names Live 12.2.5 Suite.
  This is not a compatibility matrix or an approved product promise.
- The repository includes automated/fake-Live tests, but these documents do not
  establish that each current workflow has been tested by a producer, read back
  in a current Live session or auditioned.
- The static example client config is not evidence that Claude Desktop or Cursor
  configuration generation exists.
- The requested User Library discovery, first-run experience, port selection,
  uninstall UX and explicit unsupported-version rejection need implementation
  assessment and tested acceptance criteria. Current CLI help alone does not
  prove every internal behavior.
- Privacy material must account for the tool-catalog entry describing an
  optional Replicate-backed audio question tool that uploads a local audio file.
  Review current tool behavior and data flows before adopting any privacy copy.

## Architecture boundary for kickoff

Today the product boundary is a local MCP process plus a generated Live Remote
Script communicating over a local bridge. Setup crosses three owners:

1. Python package/CLI and installer (local machine and User Library path).
2. Live Remote Script and Control Surface activation (Live process, protocol,
   supported Live APIs).
3. MCP client configuration and connection (client-specific stdio config).

The launch work should make these boundaries observable and recoverable rather
than hiding them behind a broad “connected” state. The installer cannot prove
the selected script has loaded until Live reports the expected version; a
successful fake-Live test cannot prove actual Live compatibility or sound.
