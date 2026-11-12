# Changelog

## Unreleased

- Add `enableton setup`, a read-only first-run check. It prints the resolved
  User Library, whether the installed Remote Script still matches its manifest,
  the entry for an optional `--client`, and the exact commands that remain. It
  builds, copies and launches nothing; exit 0 means installed and matching, 1
  means a command is still needed.
- Add `enableton uninstall`, which moves the installed Remote Script into a
  timestamped backup, lists locally modified or missing files, and never
  deletes a Live set. `install`, `doctor` and `uninstall` now discover the
  User Library when `--user-library` is omitted and fail with the checked
  paths instead of guessing when none or several exist.
- Add `enableton client-config claude-desktop|cursor`, which prints one
  `mcpServers.EnAbleton` entry launched by the interpreter running this
  installation and names the file the client reads on stderr. `--output` writes
  a new file only; an existing client configuration is never edited or merged.
- Add the MVP product documents (`docs/product/`), the producer agent profile
  and the shared Copilot instructions, adopted from the reviewed handoff bundle.
- `enableton` with no arguments shows nine preparation steps for the open set:
  adopt, name, label, voice, level, lock, frame, map and check. `all` runs them
  in order. A direct English request is printed for the assistant. The command
  writes by default. `--plan` previews. `prepare-tracks`, `assign-instruments`,
  `repair-audio`, `align-tracks` and `lint` remain as aliases. `uv tool install
  --from . enableton` installs the command for any directory.
- `prepare-tracks`, `assign-instruments`, `repair-audio`, `align-tracks`, and
  `song-init` write when they run. `--plan` previews. MCP `apply_*` tools write
  unless `confirm` is false.
- Add `align-tracks` to the startup menu. Arrangement audio that is already
  warped gets Beats for drums and percussion, Tones for bass, and Complex Pro
  (or Complex) for tonal and full-mix layers. Re-Pitch stays. Warp markers,
  clip starts, polarity, EQ, sends, automation, racks, and groups stay. It
  does not start playback.
- Add `assign-instruments` and `repair-audio`. MIDI tracks that have notes and
  no instrument get a stock placeholder chosen from their content, so the part
  can be heard and then replaced. Arrangement audio is scanned for the first 30
  seconds of each source file: unity clip gain is lowered when samples hit full
  scale, and Utility's DC switch is enabled when this Live build exposes it.
  Three or more level jumps load one gentle Compressor (2:1, makeup off) when
  the track does not already have one. Clicks, gaps, and sparse jumps stay
  reported. Both commands write when run. Neither command starts playback.
- Add `prepare-tracks` for a new song. Working tracks are renamed from their
  content and colored by role. Each one is duplicated first; the copy is muted,
  disarmed and named `ORIGINAL | ...`, and folded when it is a group. Notes,
  Warp and faders stay. The command writes when run.
- Retire the AbletonMCP control surface. Install from main; `v0.1.0-beta.1` is
  not the install target. The generated script names itself EnAbleton in Live's
  log and status bar (bridge protocol `1.8.1-ext.15`, still accepting `ext.1`
  through `ext.14`). Fully quit Live after installing so the renamed script loads.
- Fix Arrangement audio import so a new Live clip wrapper is not deleted as a
  different clip, and remove an import that does not land on the requested beat
  (bridge protocol `1.8.1-ext.14`). Song-draft tracks, clips and notes are one
  undo step, and an existing locator is left in place. Rack readback omits
  values that are not JSON. This bridge's replies end with a newline, and
  arrangement audio import waits up to 60 seconds. Fully quit Live and select
  only EnAbleton after installing.
- Add Arrangement audio import, rack inspection and blend-macro mapping (bridge
  protocol `1.8.1-ext.13`). Serum parameter aliases resolve friendly names onto
  configured Live parameters and write native values. A 4/4 song-draft guide
  plans, revises and applies Session sketches without starting playback;
  dubstep, riddim and half-time stay on the half-time remix guide.
  `describe_tool_families` groups the new tools with the existing names.
- Add guarded Arrangement clip move, split and delete commands plus writable
  `start_marker`/`end_marker` (bridge protocol `1.8.1-ext.9`). `start_time` is
  get-only, so a move is a duplicate at the destination followed by a delete.
- Add the default initial-preparation preset behind `enableton initiate`: it asks
  prepare or lint, then runs the nine preparation steps. `check` stays off.
  Song-folder creation stays off unless `prep workspace` is called.
- Add role-based layer naming and colours (`NN Label`, one colour per role) as a
  registered step, and make render-first, reference-aligned Warp removal the default.
- Correct clip extent units: `loop_end` and `end_marker` are settable, and unwarped
  audio measures them in seconds rather than beats.
- Add guarded Live writers for track and clip deletion, Session clip resizing and
  audio Warp state (`set_access_warp`, bridge protocol `1.8.1-ext.8`), plus track
  monitoring state and clip `warp_mode` through `set_clip`.
- Let planners insert notes without IDs and reconcile clips by note ID with readback.
- Make `song-init --apply` apply every supported change and report platform limits as
  skipped steps; `--strict` restores all-or-nothing preflight.
- Widen the writable surface to mute/solo/arm, loop bounds, gain, pitch, looping, Warp,
  signature, swing, loop and metronome; report grouping and Arrangement extent as
  Live API limits instead of planning them.
- Add note insert/delete bridge commands and MCP tools, the `LiveAdapter` apply path
  and a repeatable live smoke check for the widened adapter.
- Add conservative MIDI cleanup proposals and shared stem timing bindings; preserve source clips and pitch classes.

- Extend remix creation to an end-to-end short-section loop: guarded clip/file
  bindings, cached pitch-preserving audio, repeatable owned-track builds, actual
  kit mapping, calibrated gain automation, vocal windows, root overrides and
  phrase events. Add isolated Live resampling with verified state restoration,
  measured loudness/peak checks, matched A/B WAVs and partial-build inspection.
  Recipe 1.1.0 accepts 1.0.0 inputs; no new dependency or automatic mastering.

- Add a reusable half-time remix workflow: three source-linked style profiles,
  guided planning, exact-source MIDI/held-root generation, continuous pulse-gain
  evaluation and explicit feedback revisions. Three read-only MCP tools and CLI
  commands produce plans without silently editing Live or claiming live MIDI/audio
  linkage. Preserve source offsets, honest capability limits and recipe versions.

- Add read-only PCM audio problem scans via CLI and MCP: bounded full-sample
  measurements, timestamped review candidates and targeted repair recipes.
  Clip-source scans recheck timing; unsupported defects stay explicit.

- Remove the duplicate MCP custom-dispatch compatibility preflight while retaining
  a fresh complete version/capability guard on every operation (three calls to two).

- Batch all live-capture metadata and freshness checks; add scoped Python captures,
  bridge timing metrics, bounded read-failure isolation and timeout retry suppression.
  Preserve original readback/guard behavior; no permission or Live-thread changes.

- Replace folder-only initiation claims with real `enableton lint CONFIG --live`:
  read-only Live capture, independent YAML rule configuration, structured findings,
  coverage/errors, selected scopes and exit codes; explicit metadata-only fixes
  perform guarded readback and re-linting. Unsupported musical repairs stay visible.

- Add a YAML song-initiation runner scaffold with 16 registered planners,
  ordered dry-run projection, capability preflight, selection and step reports.
- Add user-defined song folders, root/name CLI overrides, safe reuse, manifests
  and config/report storage. Snapshot CLI does not write to Ableton.
- Document supported MCP building blocks and missing Live adapter helpers.

Changes follow Semantic Versioning; prereleases are explicitly labeled.

## [0.1.0-beta.1] - 2026-11-01

First packaged EnAbleton release, extracted from the locally developed
AbletonMCPEXT extensions. Python version: `0.1.0b1`.

### Added

- Pinned upstream Ableton Live MCP 1.8.1 plus 35 extensions (191 tools total).
- 13 native bass recipes and 47 searchable production references.
- Artist-method/tutorial catalogs, rhythmic phrases, bass modulation and
  seven mastering techniques with provenance and verification limits.
- Guarded nested device, Main/return, chain-mixer and object access.
- Full-range Session/Arrangement MIDI inspection and note-ID edits.
- Complete warp-marker inspection and bounded source-audio diagnostics.
- Duplicate-only warp repair previews with stale-target checks and journals.
- Namespaced Python package, CLI, lock file, generated catalogs, installer
  backups/rollback, CI, licensing and installation/release documentation.

### Known limitations

- The added audio analyzer accepts integer PCM WAV only.
- Tempo/downbeat results require musical/audible confirmation.
- Live-side marker repair is capability-gated; beta tests do not certify every
  Live build or audio quality. See docs/LIMITATIONS.md.
- Existing local installations are not silently migrated to EnAbleton.
