# YAML song-initiation workflow (unreleased scaffold)

The workflow now has a real, read-only Live linter as well as the configurable
cleanup-planner skeleton. Use `enableton lint CONFIG --live` (or
`enableton song-init CONFIG --live`) to audit the running set. Workspace creation,
Live lint and applying fixes are separate stages. Disabled cleanup steps do not
disable lint rules. See [Live lint commands, rules and limitations](LIVE_LINT.md).

The legacy snapshot runner still supports folder creation and pure planner
projection. Full musical cleanup is not automatically implemented: explicit
`--fix` currently supports guarded names/colors, with re-linting. MIDI, grouping,
Warp and trimming repairs remain reported until verified helpers exist.

## Files

- `examples/song-init/initiation.yaml`: complete, commented configuration.
- `schemas/song-init.schema.json`: JSON Schema 2020-12 for editor integration.
- `examples/song-init/snapshot.example.json`: synthetic normalized input, no user media.
- `src/enableton/song_init.py`: registry, schema checks, runner, folder process support,
  adapter contract, CLI, ordered dry-run projection and before/after reports.
- `src/enableton/song_processes.py`: pure modular correction planners.
- `docs/prompts/SONG_INITIATION_PROMPT.md`: reusable expanded implementation prompt.

## Commands

Preferred live audit:

```powershell
uv run enableton lint "F:\ableton songs\In Hell\configs\initiation.yaml" --live
```

A lint run reads actual MIDI, Warp maps and group metadata; it does not change
notes or create a folder. Explicit `--report` saves findings. Exit codes are 0 for
no threshold-level findings, 1 for findings and 2 for incomplete/operational errors.
The `lint` configuration is documented in [LIVE_LINT.md](LIVE_LINT.md).

Applying the workflow to the running set is explicit:

```powershell
uv run enableton song-init "F:\ableton songs\In Hell\configs\initiation.yaml" --live --apply --only names,colors
```

`--live` alone still lints. The Live adapter writes track/clip names and colours,
song tempo and time signature, and note edits by ID for the quantize, overlap and
velocity steps. The adapter writes track and clip names, colours, mute/solo/arm, clip looping and
loop bounds, song tempo/signature/swing/loop/metronome, track and clip deletion,
Session clip length, audio Warp state (including `warp_mode` via `set_clip`), track
monitoring state, and note edits. Unsupported changes no
longer abort a run: the step is recorded as `reported` with the platform reason and
everything else is applied; `--strict` restores all-or-nothing preflight. Only
grouping and Arrangement clip extent remain impossible, because Live exposes no
group-creation call and no writable Arrangement length.

Legacy snapshot planning and workspace commands:

Run from the repository after `uv sync --locked`. Config path comes before flags.

```powershell
# Default is dry-run: no folders, files, logs or Live changes are written.
uv run enableton song-init examples/song-init/initiation.yaml --snapshot examples/song-init/snapshot.example.json --dry-run --song-root "D:\Music\Songs" --song-name "My New Song"

# Select one step or a subset, retaining YAML order.
uv run enableton song-init examples/song-init/initiation.yaml --snapshot examples/song-init/snapshot.example.json --only names,colors

# Actually create only the user-chosen song workspace. No Ableton connection.
uv run enableton song-init examples/song-init/initiation.yaml --snapshot examples/song-init/snapshot.example.json --only workspace --apply --song-root "D:\Music\Songs" --song-name "My New Song"
```

A full `--apply` applies every change the adapter can perform and records the rest
per step as `skipped`, naming the platform limit; add `--strict` to refuse before
any write or folder instead. Do not use the example snapshot to target a real set;
its IDs are fictional. There is no silent fallback from an unsupported write to UI
automation.

## Configuration schema

`schemaVersion` is integer `1`. The optional `lint` section independently configures diagnostic rules, scope and thresholds.
Unknown root/step/selector/predicate keys are errors.
Each enabled process validates its own parameters before any writes.

| Field | Meaning |
| --- | --- |
| `song` | Optional workspace settings; required when the folder step is selected. |
| `song.name` | Human-readable song name, including spaces/Unicode. |
| `song.root` | Absolute parent folder chosen by the user. Not hardcoded in the runner. |
| `song.folderName` | Optional single safe folder name (internal spaces preserved); otherwise slugified from `name`. |
| `song.onExists` | `error`, or `reuse` for the same song's workspace; never clear/overwrite it. |
| `song.subfolders` | Optional safe single-component names; defaults below. |
| `defaults.processes` | Per-process parameter maps, merged with step params; step params win. |
| `steps` | Ordered objects with required `id`, `process`, boolean `enabled`, object `params`. |
| `target.trackIds` | Stable track IDs from the adapter snapshot, not display positions. |
| `target.clipIds` | Stable clip IDs; also limits track selection to tracks containing those clips. |
| `target.types` | Track types (`audio`, `midi`, `group`); selectors intersect. Empty list selects none. |
| `when.hasAudio`, `when.hasMidi` | Boolean existence predicates on the current projected/current state. |
| `when.minTracks` | Minimum track count. No Python expressions or arbitrary `eval`. |

`--song-root` and `--song-name` override YAML, including folder-step params.
After the workspace step, subsequent planners receive `state["workspace"]`
with the resolved path and song name, in both projected dry runs and actual runs.

Selected step IDs must exist; disabled steps remain disabled even with `--only`.
Unknown processes fail validation even if disabled, catching configuration typos.

### Workspace behavior

For root `D:\Music\Songs` and name `My New Song`, create:

```text
D:\Music\Songs\my-new-song\
  song.json                 # Name, schema version and UTC creation time
  audio\                    # Optional prepared audio copies, not automatic moves
  midi\
  originals\                # Original MIDI/audio backups when an adapter provides them
  exports\
  reports\<run-id>.json      # Before/after state, intended changes, notices, failures
  configs\<run-id>.yaml      # Resolved config used for an applied run
```

Reserved Windows names, absolute/traversing `folderName` values, unrelated
non-empty existing folders, and symlink paths escaping the configured root are
rejected. Reuse never deletes existing content. UTC timestamps and unique run IDs
avoid overwriting reports. Reports/configs are written only during apply after a
workspace exists; runs without a folder step return their logs to the caller.
A filesystem failure can leave a partial folder; it is not an atomic transaction.

**Creating this folder does not Save As the Live set or Collect All and Save.**
Those require explicit, verified helpers. No source media is moved or deleted.
If collection is implemented, copy referenced media into this workspace, keep a
manifest and preserve the original source paths until relinking is verified.

## Registry and extension point

Planners receive normalized current state, merged params and a target selector.
They return a `Result(changes=[...], notices=[...])`. They must not perform writes,
including during planning. `change.before` carries the target snapshot for stale
state checks. `change.kind` chooses the adapter operation; it is not arbitrary
code, a shell command or a raw Live attribute setter.

```python
from enableton.song_init import Result, register

@register("audit_tempo")
def audit_tempo(state, params, target):
    # A real implementation compares MIDI metadata and measured audio evidence.
    return Result(notices=["Check shared stem timing before choosing a tempo."])
```

Import the module once to register it, then add:

```yaml
- id: tempo-audit
  process: audit_tempo
  enabled: true
  params: {}
```

New write kinds need a corresponding guarded adapter capability. Do not claim
support simply by adding a registry entry. Add tests for the planner and adapter.

## Runner and adapter pattern

```python
from enableton import song_processes  # Explicit registration
from enableton.song_init import load_config, run_pipeline

config = load_config("initiation.yaml")
report = run_pipeline(config, your_verified_mcp_adapter, dry_run=True)
# Explicit apply, after a reviewed plan and verified adapter capabilities:
# report = run_pipeline(config, your_verified_mcp_adapter, dry_run=False)
```

Implement three adapter methods:

1. `snapshot()` reads and normalizes current session, track and clip state.
2. `supports(change)` declares each supported change kind without side effects.
3. `apply(change)` re-resolves stable IDs, re-reads the target, checks the captured
   state/identity/name/start guards, performs a small operation and verifies it.

For lint, `--live` performs this normalization directly; no hand-written snapshot is required.

The normalized state shape is documented by the example JSON: `session` contains
`tempo`, `numerator`, `denominator` and optional `key`; tracks have unique `id`,
`name`, `type`, optional explicit `role`, `devices`, `clips`, `has_automation`,
`armed`, `live_input`, group/return/master flags. Clips have unique IDs, `type`,
`name`, `view`, musical `start_beats` / `end_beats`, audio path/availability/frames
and Warp metadata, or MIDI `notes` with pitch, start_time, duration, velocity and
optional extended fields. Preserve an immutable `source_name` for custom naming.
This is **not** the upstream compact snapshot's unmodified JSON format.

Dry-run plans and projects ordered changes entirely in memory. It never calls
`adapter.apply`, creates folders or writes report files. Actual execution takes a
fresh state before every step, skips failed `when` predicates, and stops at the
first error. All selected write kinds are preflighted before local or Live writes.
A concurrently edited set can still invalidate a step; fail on stale state.
Before/after logs are not an Undo implementation. A failing writer may have made
partial changes; log the actual after-state, preserve backups and stop.

Default naming, color assignment and velocity clamping prefer idempotence.
Partial-strength quantization converges over repeated runs and velocity `scale`
is not idempotent. Use tolerance/review/run provenance to avoid repeated processing;
never advertise the whole pipeline as automatically idempotent.

## Process-to-MCP / Live capability map

Tool names and wire commands differ. This table describes available building
blocks, not an assertion that the snapshot CLI currently executes them.

| Registered process | Planner/default behavior | Existing MCP / Live building blocks | Required adapter/helper |
| --- | --- | --- | --- |
| `create_song_folder` | Implemented local workspace; dry-run has zero writes | Local filesystem only | Included; does not save/relink a Live project |
| `cleanup_unused` | Audit stub; collection/save off; never deletes files | Current snapshot, sample paths, project inventory | Missing project-wide reference inventory, copy/relink and reliable save helper |
| `rename_tracks` | Strip numbered defaults; `{type}_{name}`; preserve role | `get_track_info`, `set_track_name`, guarded `write_access_object` | Re-resolve IDs; prevent stale/duplicate target matches |
| `fix_midi_overlaps` | Same-pitch `trim`; optional `shortest_wins`, `longest_wins`, monophonic | `get_access_notes`; new Session clip + `add_notes_to_clip` + Arrangement duplicate | Verified writer; edits use remove/re-add because `apply_note_modifications` failed on Live 12.2.5, so edited note IDs change |
| `quantize_timing` | Grid/strength/tolerance; default 1/16, .75, .03 beats | MIDI reads; `quantize_clip` for supported Session cases; replacement clip path | Custom target/tolerance writer; audio-transient/groove alignment is a separate process |
| `normalize_clip_names` | Role, session BPM and actual Warp state; no native-BPM guesses | `set_clip_name`, Arrangement name tool, guarded clip property writer | Preserve source provenance; refresh indexes |
| `remove_empty_tracks` | Disabled example; only known no clips/devices/automation/input | Track/device/clip reads; guarded `delete_track` | Re-checks emptiness at write time; returns/groups/master protected |
| `remove_empty_clips` | Disabled example; zero notes or zero audio frames only | Clip/MIDI reads; guarded `delete_clip` / `delete_arrangement_clip` | Distinguishes missing/quiet audio from empty; refuses when the slot changed |
| `fix_clip_lengths` | Explicit extend or nearest+allowTrim | Session `loop_end` write; Arrangement reads | Session clips resize; Arrangement extent has no writable length and is reported |
| `color_tracks_by_type` | Role-to-Live-color-index map | `write_access_object` track color | Optional clip-color adapter; preserve hierarchy |
| `set_default_warp` | Disabled example; Warp state/mode request | `get_audio_clip_timing`; guarded `set_access_warp` for both views | Base tempo is read-only in Live and is reported, not written |
| `normalize_velocities` | Clamp 40..112; optional scale | Extended MIDI reads + verified replacement writer | Role-aware dynamics can be added; do not flatten all drums to max velocity |
| `check_missing_samples` | Report only; checks availability/path | Audio file paths, local filesystem; Live availability if exposed | No deletion or automatic relinking |
| `organize_groups` | Report-only; optional planned grouping | Track/device reads | Live has no group-creation API, so the step is reported as skipped |
| `set_session_defaults` | Fill missing values only; force opt-in | Session read, `set_tempo`, `set_time_signature`, song property writer | Validated key mapping; Live always already has tempo, so this is not BPM detection |
| `trim_overlapping_clips` | Report only | Arrangement clip reads/delete/duplicate | Guarded trim/rebuild and preserved originals; avoid overwriting neighboring clips |

### Lessons incorporated from the current production work

- Source MIDI tempo metadata and audio transients can reveal a session-tempo
  mismatch. Do not quantize a whole song before fixing its timing basis.
- Equal source lengths plus MP3 encoder padding can differ from Live's independent
  Auto-Warp guesses. Decode/verify shared sample starts and preserve stem phase.
- Group, return and Main tracks may reject Arrangement clip enumeration. Treat
  that as a track-kind limitation, not proof of an empty/deletable track.
- `add_notes_to_clip` in pinned upstream 1.8.1 **replaces**, rather than appends.
- The in-place `modify_access_notes` helper failed at runtime on this Live build.
  A new adapter must use verified APIs or prepare original/clean Session clips
  and replace Arrangement copies only after note-count/content readback.
- Unwarped duplicate placement did not reliably honor prepared source offsets;
  cached `clip.length` also differed from intended ranges. Verify actual Arrangement
  bounds and playback-source positions; use tested working media when needed.
- Do not force every MIDI part to the full song length. Short sketches, real
  rests, pickup notes, chord polyphony and audio tails need separate treatment.

## Validation

Unit tests cover folder/path containment, reuse, no-write dry runs, capability
preflight before folder creation, failure logs, ordered projection, selections,
extensions, MIDI overlap strategies, quantize tolerance and default idempotence.
They use synthetic data, not Live. A new Live adapter requires integration tests
and a saved recoverable test set before production use.
