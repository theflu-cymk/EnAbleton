# EnAbleton beta read/write access

This extension expands the 1.8.1 server rather than enabling an unrestricted
Python interpreter inside Live. Every bridge command runs on Live's main
thread. Writes are explicit; installing the extension never changes a song.
Tool count: 234 (156 upstream, 78 additions). Recipes are retained, and every
upstream 1.8.1 tool is present; see [TOOL_CATALOG.md](TOOL_CATALOG.md) for the
generated list and the annotated reference at <https://abletonmcp.com/tools/>.

| Area | Read | Write |
| --- | --- | --- |
| Main, returns, regular tracks | Device trees, all nested parameters and formatted values | Named parameter batches with readback, rollback and Undo |
| Nested rack chains | Name, mute/solo, devices, mixer volume/pan/sends | Name/mute/solo and mixer controls |
| Song | Exposed tempo, swing, loop, metronome, time signature | Allowlisted scalar properties |
| Tracks and scenes | Names, colors, mute/solo/arm where applicable | Supported scalar properties |
| Session and Arrangement clips | Properties; complete MIDI notes and note IDs | Properties, note-ID modifications, and verified insert/delete |
| Existing upstream coverage | Routing, transport, meters, browser, rack macros, pads, take lanes, offline sets | Existing creation/deletion, recording, routing, note-generation and device controls |

## Target schema

```json
{
  "track_type": "master",
  "track_index": 0,
  "expected_track_name": "Master",
  "device_path": [0, 0, 4],
  "expected_device_name": "Limiter"
}
```

Read the tree first. Paths alternate device index, chain index, device index.
The example means device 0, its chain 0, then device 4 in that chain. Nested
paths support up to eight rack levels. `track_type` is `track`, `return` or
`master`; the master ignores `track_index`.

Chain mixers use a path to the parent rack, a `chain_index`, and
`expected_chain_name`. `volume`, `pan`, and `send:N` use the inspected native
range, not an assumed dB-to-normalized conversion. Automated controls are
refused rather than overridden.

Clip targets use `clip_view=session|arrangement` and `clip_index` in the
corresponding collection. Writes require track and clip name guards;
Arrangement writes also require `expected_start_time` in arrangement beats.
MIDI note times remain in the clip's own coordinate system. Offset loop
regions do not truncate the new full-range reader. Note-ID edits retain the
clip, its other notes and their expression data; edited notes get new IDs
because Live edits them by remove/re-add. Insert and delete use separate guarded
commands; edits never rewrite MPE curves. Read back after every edit.
Runtime API differences can still fail; use Live Undo if rollback reports
incomplete.

## Boundaries

There is no promise of read/write access to literally every part of Live.
Preferences, arbitrary UI actions, plug-in window controls, audio-to-MIDI
conversion, and hidden third-party plug-in parameters remain outside this
bridge. Track reordering and direct Arrangement automation are not added.
Group creation and moving tracks into a group are absent from the Live API
itself, and Arrangement clip extent has no writable property, so those two are
reported rather than faked. Guarded writes do cover track and clip deletion,
Session clip length and audio Warp state.
Session envelope tools keep their existing documented behavior. Audio
measurements, rendered true peak and perceived sound require separate checks.

The access command wrappers are tested with fake Live objects and through MCP
transport. A real Live restart is required to load EnAbleton beta. Until readbacks from
that version are available, do not claim the new controls are runtime-verified.
No tests modify the user's current set.

Primary API references:
- https://docs.cycling74.com/apiref/lom/track/
- https://docs.cycling74.com/apiref/lom/clip/
- https://docs.cycling74.com/apiref/lom/deviceparameter/
- https://docs.cycling74.com/apiref/lom/chain/

## Clip extent and units (Live Object Model)

`Clip.end_time` is get-only, but the Arrangement edge follows `loop_end` and
`end_marker`, both of which are get/set. Units depend on Warp: beats while the
clip is warped, seconds for unwarped audio, so a write made after disabling
Warp must be expressed in seconds. Live exposes no group-creation call, and
`Track.group_track` stays read-only.

### Moving, splitting and deleting Arrangement clips

`start_time` is get-only in the Live Object Model, so a clip cannot be moved by
assignment. Three guarded bridge commands fill that gap:

- `move_arrangement_clip` duplicates at the destination beat with
  `duplicate_clip_to_arrangement`, deletes the original, then verifies the new
  start and end. It refuses a destination that would overwrite another clip on the
  track, and requires `expected_start_time` plus an optional `expected_clip_name`.
- `split_arrangement_clip` duplicates at `split_at`, sets `end_marker` on the left
  half and `start_marker` on the right, then checks both edges.
- `delete_arrangement_clip_guarded` deletes only when the clip still starts at the
  guarded beat and still carries the guarded name.

All three refuse unwarped audio, where markers are seconds rather than beats. Warp
it, or render at project tempo and place the render. `start_marker` and `end_marker`
are also writable through `write_access_object`, validated from 0 to the clip length
in the clip's own units. Each destructive command runs inside one Undo step and
reports failure explicitly instead of presenting a partial edit as success.
