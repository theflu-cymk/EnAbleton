# EnAbleton v0.1.0-beta.1

First versioned, packaged release of the EnAbleton MCP extension layer.

## Included

- 191 MCP tools: 156 pinned upstream 1.8.1 tools plus 35 additions.
- 13 native bass recipes and 47 searchable production references.
- Artist/tutorial catalogs, mastering plans, MIDI phrases and modulation.
- Guarded nested device/Main/return/chain control and full-range MIDI reads/edits.
- Warp marker inspection, heuristic tempo/downbeat/groove diagnostics and reference alignment.
- Duplicate-only warp repair previews, source/target guards, backups and recovery journals.
- Namespaced Python CLI, dependency lock, complete catalogs, CI and installation/release guides.

## Validation

91 unit tests and read-only MCP registry/catalog checks passed locally on Windows with Python 3.12. Built wheel/sdist resources and temporary bridge installation are checked before publishing. A real local drum loop was used during analyzer development; estimates remain heuristic. CI does not run Ableton.

## Beta limits

The added analyzer accepts integer PCM WAV. Musical downbeats and sonic quality require listening. Live marker repair is capability-gated and needs runtime readback; not every Live version is certified. GUI-only controls and hidden plug-in internals are unavailable. Installation never edits the user's set.

## Install

Clone this private repository, check out `v0.1.0-beta.1`, run `uv sync --locked`, then follow [the installation guide](https://github.com/theflu-cymk/EnAbleton/blob/v0.1.0-beta.1/docs/INSTALLATION.md). Select only the EnAbleton bridge on port 9877. No PyPI publication is configured.

Assets include the Python wheel, source distribution and SHA-256 checksums. This is a prerelease. Tag version `v0.1.0-beta.1` corresponds to Python version `0.1.0b1`; the bridge protocol remains `1.8.1-ext.5`.
