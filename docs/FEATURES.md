# Additions and abilities — v0.1.0-beta.1

The first beta shipped 191 MCP tools. The current development catalog has 234:
156 from pinned upstream 1.8.1 and 78 additions.
The generated [tool catalog](TOOL_CATALOG.md) includes every tool and annotation.

| Area | Added capabilities | Practical limits |
| --- | --- | --- |
| Bass recipes | 13 original native patches: sub, 808, wobble, FM, Reese, YOI and riddim variants | Available instruments required; numeric starting points are not artist presets |
| Rhythm and movement | Deterministic bass phrases, call/response, triplets, plucks, wobble, ducking and Drive envelopes | Session automation; kick-time ducking is not an audio-reactive compressor |
| Production reference | 50 reference entries (45 with primary sources), artist-method catalogs, tutorial blueprints | Read-only evidence and original adaptations; no automatic learning across chats |
| Mastering | Seven techniques and conditional dense-tearout/transparent/delivery plans | No automatic mastered export, LUFS measurement or sound-quality guarantee |
| Nested devices | Read trees and parameters; guarded writes on regular tracks, returns and Main | Hidden third-party controls are unavailable |
| Rack mixers | Chain volume, pan, sends, mute/solo and names | Uses inspected native units; automated controls are refused |
| Object access | Allowlisted song, scene, track, clip and chain properties | Not arbitrary Python or unrestricted object writes |
| MIDI editing | Complete-range reads, note-ID edits, and verified insert/delete in Session and Arrangement | Does not transcribe audio or rewrite MPE curves |
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

## Unreleased arrangement import, racks and drafts

`create_arrangement_audio_clip` imports a file onto a free Arrangement beat and
removes that import if its length overlaps another clip or it does not land on
the requested beat. `inspect_rack` and `map_rack_blend_macro` read nested
Dry/Wet, Mix and Amount parameters and map them to one macro when this Live
build exposes `RackDevice.macro_map`. Serum aliases translate friendly names
onto configured Live parameter strings and still write native values.
`guide_song_draft`, `plan_song_draft`, `refine_song_draft` and
`apply_song_draft` sketch a 4/4 house, hip-hop, pop or melodic Session draft;
dubstep, riddim and half-time stay on the half-time remix guide. Applying a
draft writes tracks, clips and notes as one undo step and does not rename a
locator that already sits on a section beat. `describe_tool_families` groups
those tools with the existing names. Drum pitches in a draft are General MIDI
guesses.

## Unreleased song workflow and Live lint

[Live lint](LIVE_LINT.md) reads the running set directly and returns structured
findings, confidence, locations, fix availability and CI-style exit codes. Lint
rules run independently of disabled cleanup steps. Explicit metadata fixes have
name/start guards, readback and re-linting. Musical/destructive repairs remain
reported until verified helpers exist. The [workflow](SONG_INITIATION.md) retains
configurable song folders and snapshot planning. These are CLI additions; the
released MCP tool catalog remains 191 tools.

## Unreleased remix creation

[The reusable workflow](REMIX_WORKFLOW.md) now covers a complete bounded loop:
guided musical plans, conservative transcription cleanup, shared timing for
aligned stems, cached pitch-preserving renders, repeatable owned-track builds,
kit-aware half-time drums, held mono sub roots, vocal activity windows, phrase
variation and bounded Live capture. A/B files use measured integrated loudness
or an explicit RMS fallback. Source clips/media remain intact.

Synthetic audio and fake-Live tests are distinct from actual Live readback.
Windows capture releases the recording track before analysis and restores
transport, mixer and arm states. Stem separation artifacts, semantic lyric timing,
polyphonic transcription, musical audition and mastering remain separate tasks.
