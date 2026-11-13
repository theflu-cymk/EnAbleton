# Third-party notices and provenance

EnAbleton is an independently maintained extension layer, not an official
Ableton product and not a repackaging of artist presets.

## Ableton Live MCP

Dependency: `mcp-server-ableton-live==1.8.1`.
Source: https://github.com/wstierhout/ableton-live-mcp
License: MIT. Copyright 2025 Siddharth Ahuja and 2026 wstierhout.
Its source-derived Remote Script is generated locally from that exact package,
with EnAbleton mixins and command dispatch added. The upstream cache is never
modified. The license is preserved in `src/enableton/licenses/ableton-live-mcp-MIT.txt`
and in the distributed wheel. The root `LICENSE` is EnAbleton's own end-user
licence and grants nothing in the upstream package; upstream notices are kept
in this file and in `src/enableton/licenses/`.

## Production references

Recipe entries retain primary-source links, evidence boundaries and original
adaptation labels. Artist names identify references; no endorsement is implied.
No commercial samples, factory presets, tutorial media or user sets are bundled.

## Other dependencies

Python transitive dependencies and integrity hashes are recorded in `uv.lock`.
Their licenses remain with their distributions. GitHub Actions are pinned to
immutable commit revisions and are not vendored into this repository.
