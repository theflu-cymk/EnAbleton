# Changelog

## Unreleased

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
