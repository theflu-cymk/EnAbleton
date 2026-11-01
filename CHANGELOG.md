# Changelog

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
