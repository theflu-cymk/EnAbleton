# Prompt for Ableton MCP song-initiation workflow

You are working on an Ableton Live MCP project. Create a YAML-driven song-initiation
pipeline that normalizes and cleans a Live set, or selected tracks/clips, by running
an ordered list of modular correction processes. Like an npm build script for sets,
one command runs a configurable sequence of fixes. New processes are added by
registering a function and adding a step to the config.

## Requirements

- Config format: `initiation.yaml` or `song-init.yaml`.
- Schema: `schemaVersion`, optional `song`, optional `defaults`, and ordered `steps`.
- Each step: unique `id`, registered `process`, boolean `enabled`, object `params`,
  optional `target` and optional declarative `when` predicates.
- Python process registry: string names to callables. Prefer explicit imports;
  never evaluate YAML as Python or load arbitrary code from it.
- Runner: load and validate YAML; execute enabled steps in order; support a single
  step/subset by ID; dry-run with intended changes and no filesystem/Live writes;
  before/after state logs per step; prefer idempotent operations.
- Each process receives normalized state/Live-MCP adapter context plus params and
  targets, and returns a change list or executes through a guarded adapter.
- Preflight capabilities before apply. Stop on errors or stale targets, preserve
  originals and report partial changes honestly. Do not silently skip unsupported
  required operations or pretend every Live property is writable.
- Extension documentation: write process -> register it -> add a YAML step -> test.

## User-defined song folder (required addition)

Add a first-class `create_song_folder` process. The user chooses the parent
location and song name in YAML or with `--song-root` and `--song-name` overrides.
Do not hardcode a drive, username or song root.

```yaml
song:
  name: 'My New Song'
  root: 'D:\Music\Songs'       # User-defined absolute parent location
  # folderName: 'my-new-song'  # Optional; otherwise derive a safe slug
  onExists: reuse             # error | reuse; never clear an existing directory
  subfolders: [audio, midi, originals, exports, reports, configs]
steps:
  - id: workspace
    process: create_song_folder
    enabled: true
    params: {}
```

The folder process must:

1. Validate path/name, reject traversal/reserved names and symlink escapes, and
   use a single song folder under the selected root.
2. Create the workspace only on apply. Dry-run must not mkdir, save manifests,
   copy files, create logs or modify Ableton.
3. Reuse only the same song's folder, or fail clearly according to onExists.
   Never overwrite/delete an unrelated existing folder or original media.
4. Create configurable standard subfolders, a song manifest, resolved config copies
   and per-run before/after reports. Log source-media paths and any verified copies.
5. Preserve source files. Asset collection is copy-first and separately configurable.
6. State clearly that creating this directory does not automatically Save As the
   `.als` file, Collect All and Save, or relink audio; those need verified helpers.
7. Allow a new process to access the resolved workspace through context without
   requiring every process to invent its own filesystem location.

## Base processes (implement or adapt from existing work)

1. `cleanup_unused`: audit unused assets; optional collection/save. Never delete
   files based only on their absence from the current set.
2. `rename_tracks`: configurable naming such as `{type}_{name}`, strip numbered
   defaults, preserve reliable source/role names.
3. `fix_midi_overlaps`: `shortest_wins`, `longest_wins` or `trim`; same-pitch default;
   monophonic cleanup opt-in so legitimate chords remain polyphonic.
4. `quantize_timing`: grid, strength and tolerance; notes already inside tolerance
   remain untouched. Validate tempo/audio timing before mass quantization.
5. `normalize_clip_names`: consistent names, actual Warp status and correctly
   labeled source-vs-session tempo where that metadata is known.

## Additional registered processes

- `remove_empty_tracks`: no clips/devices; protect returns, groups, Main, live
  inputs and automation; selection and deletion guards required.
- `remove_empty_clips`: genuinely empty MIDI or zero-length audio; missing or
  quiet samples are not automatically empty.
- `fix_clip_lengths`: report/snap to bar boundaries, preserve meaningful short
  parts and tails; destructive trimming must be explicit.
- `color_tracks_by_type`: role/prefix-to-color mapping.
- `set_default_warp`: consistent Warp mode/base tempo only when evidence supports
  it; preserve shared multitrack timing/phase and original maps.
- `normalize_velocities`: clamp/scale to a range; allow per-role settings.
- `check_missing_samples`: report/flag missing audio, no automatic deletion.
- `organize_groups`: group by role where supported; otherwise an explicit stub
  identifying the new grouping/routing helpers needed.
- `set_session_defaults`: fill missing tempo/key/time signature only; distinguish
  defaults from measured BPM/key and require opt-in for overriding existing values.
- `trim_overlapping_clips`: report or guarded correction of same-track Arrangement
  overlaps; preserve originals and neighboring material.

## Output

Produce:

1. Schema description and complete commented example config with the base
   processes, `create_song_folder`, and at least five suggested processes.
2. Python registry pattern.
3. Runner skeleton with YAML loading, ordered execution, dry-run, per-step logs,
   selection, capability preflight and a configurable resolved song workspace.
4. Short extension instructions.
5. A process-to-MCP/Live API mapping; clearly flag stubs and missing helpers.
6. Usage examples showing two different user-chosen folder roots, a dry run and
   folder-only apply. Include tests for no-write dry runs, containment/reuse,
   target guards, ordered steps and unsupported-operation handling.

Prefer existing Ableton MCP tools. Keep processes small. Preserve the distinction
between pure planners, a snapshot-only runner skeleton and verified live writers.
Never use UI accessibility automation on a Live installation known to crash from it.

## Required Live lint stage

Workspace creation is preparation, not successful set cleanup. Provide a command
that reads the running Live set directly and reports real findings independently
of whether cleanup steps are enabled. Findings need rule/code, severity, track/clip
locations, evidence, confidence and truthful fix availability. Return exit 0 for
no threshold-level findings, 1 for findings and 2 for incomplete/failed audits.
Report unchecked capabilities explicitly. A lint must not write to Live; report
files require an explicit destination. Fixes are a separate opt-in, preserve
originals, recheck target state, verify and re-lint. Do not claim MIDI/harmonic
repairs or sorting merely because folders/configs exist.
