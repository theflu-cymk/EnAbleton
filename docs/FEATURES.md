# Additions and abilities — v0.1.0-beta.1

There are 191 MCP tools: 156 from pinned upstream 1.8.1 and 35 additions.
The generated [tool catalog](TOOL_CATALOG.md) includes every tool and annotation.

| Area | Added capabilities | Practical limits |
| --- | --- | --- |
| Bass recipes | 13 original native patches: sub, 808, wobble, FM, Reese, YOI and riddim variants | Available instruments required; numeric starting points are not artist presets |
| Rhythm and movement | Deterministic bass phrases, call/response, triplets, plucks, wobble, ducking and Drive envelopes | Session automation; kick-time ducking is not an audio-reactive compressor |
| Production reference | 47 source-linked entries, artist-method catalogs, tutorial blueprints | Read-only evidence and original adaptations; no automatic learning across chats |
| Mastering | Seven techniques and conditional dense-tearout/transparent/delivery plans | No automatic mastered export, LUFS measurement or sound-quality guarantee |
| Nested devices | Read trees and parameters; guarded writes on regular tracks, returns and Main | Hidden third-party controls are unavailable |
| Rack mixers | Chain volume, pan, sends, mute/solo and names | Uses inspected native units; automated controls are refused |
| Object access | Allowlisted song, scene, track, clip and chain properties | Not arbitrary Python or unrestricted object writes |
| MIDI editing | Complete-range reads and existing-note-ID edits in Session and Arrangement | Does not transcribe audio or rewrite MPE curves |
| Warp inspection | Every marker, hidden terminal marker, source seconds, beat coordinates and loop boundaries | Coordinates alone do not establish correct musical downbeats |
| Warp analysis | BPM candidates, confidence labels, half/double-time, attack-based downbeats, groove alignment, drift, loop seams, reference offsets | Heuristic PCM WAV analysis, bounded windows; review/audition needed |
| Warp repair | Expiring previews, fingerprint checks, backups, explicit interior-marker moves on a duplicate, original-preservation checks | No automatic in-place fix, insertion/deletion or replacement of originals |
| Reliability | Capability/version handshake, bounded workers/cache/batches, failure journals, duplicate IDs, installer rollback | Live runtime behavior still needs explicit readback; timeouts are not proof of failure |

## Native bass patches

The full settings, sources and movement suggestions are returned by
`bass_design_catalog`. Use `preview_bass_design` before `create_native_bass`.
Device availability is checked before building; failures can leave a named
partial new track for inspection instead of hiding incomplete work.

## Existing upstream capabilities

Transport, tempo, recording/resampling, track/clip creation and deletion,
routing, scenes, browser search/loading, return/Main device loading, exposed
device parameters, rack macros, drum pads, take lanes, MIDI generators,
meter reads, offline saved-set inspection and other controls are retained.
Upstream semantics matter: **add_notes_to_clip replaces note content** and
**duplicate_to_arrangement overwrites overlapping destination content**.

## Verification status

The project includes tests for recipe determinism, parameter rollback,
automation bounds, nested access, note identities, source analysis, stale
previews, duplicate preservation, timeouts and installation recovery. A
read-only MCP transport suite verifies the complete registry and catalogs.
Real-loop analysis was exercised during development. The beta does not claim
every feature has been manually auditioned in every Live version.

See [ACCESS.md](ACCESS.md), [WARP.md](WARP.md), and [LIMITATIONS.md](LIMITATIONS.md).
