# Live-set linting

`enableton lint` reads the **running Ableton set** and evaluates diagnostic rules.
It is separate from workspace creation and from cleanup planners. Disabled
`steps` never silently disable lint checks; `lint.rules` controls the checks.

```powershell
# Read the running set; no set or filesystem writes by default.
uv run enableton lint "F:\ableton songs\In Hell\configs\initiation.yaml" --live

# Save a diagnostic report explicitly. The parent must exist; no overwrite.
uv run enableton lint "F:\ableton songs\In Hell\configs\initiation.yaml" --live --report "F:\ableton songs\In Hell\reports\lint-review.json"

# Explicit supported fixes: names/colors only, then collect again and re-lint.
uv run enableton lint "F:\ableton songs\In Hell\configs\initiation.yaml" --live --fix

# Selected rules or capture IDs, as listed in a fresh report.
uv run enableton lint "F:\ableton songs\In Hell\configs\initiation.yaml" --live --rules midi_overlaps,midi_grid --track track:3

# Offline lint is also supported; it cannot apply Live fixes.
uv run enableton lint examples/song-init/initiation.yaml --snapshot examples/song-init/snapshot.example.json
```

`enableton song-init CONFIG --live` defaults to the same lint mode. Legacy
`--snapshot --dry-run` still plans the configured correction steps; legacy
`--snapshot --only workspace --apply` creates a folder. Neither legacy operation
certifies that the live song has been cleaned. `--apply`/`--only` are workflow
options; lint uses `--fix`/`--rules`/`--track`/`--clip`.

## Results and exit codes

Every finding has a rule, code, severity, track/clip ID and name, view/start,
evidence, confidence, and explicit `autofixable`/`fix` fields. Note diagnostics
include counts and bounded examples rather than dumping an entire MIDI file.
The report records track/clip/note counts, capture errors, checked/disabled/
not-evaluated rules, and limitations. No failed read is treated as empty content.

- **0**: no finding meets `failOn` (default `warning`). Status can be `review`
  when informational findings remain; `passed` means no findings.
- **1**: findings meet the configured threshold.
- **2**: invalid config, connection/capture failure, incomplete data, or no
  assessed checks. `failOn: none` cannot hide incomplete capture.

Capture-local IDs are locators, not permanent Live object handles. Reports and
fixers must not reuse indexes after tracks/clips move. Fixes always collect again,
check current names and Arrangement starts, use existing guarded property writes,
verify readback and re-lint. Ambiguous duplicate track names block automatic fixes.

No-write behavior covers Live and disk. Only explicit `--report` writes a new JSON
file during lint. Workspace creation is a separate explicit apply. A failing fix
batch can leave partial metadata changes; inspect/rerun lint before retrying.

## Rules

| Rule | What it checks | Default / automatic fix |
| --- | --- | --- |
| `track_naming` | Blank, generic numbered/default names; duplicate track names | Warning. Safe nonblank-target rename supported. |
| `clip_naming` | Blank/default clip names | Info. Guarded nonblank-target rename supported. Blank-name writes need a corrected bridge helper. |
| `missing_samples` | Actual referenced audio availability | Error. No deletion or speculative relinking. |
| `midi_validity` | Pitch, finite times (negative pickup notes allowed), positive duration, velocity range | Error. No automatic note replacement. |
| `midi_overlaps` | Same-pitch overlap; bass role optionally monophonic | Warning. Other chord polyphony preserved. `monophonicTrackIds` allows explicit track selection. |
| `midi_grid` | Starts outside a configurable grid tolerance | Info/heuristic. Swing, pickups, triplets and fast fills can be intentional. |
| `midi_dynamics` | At least 90% maximum velocity in a part with 8+ notes | Warning/heuristic. No automatic flattening/clamping. |
| `harmonic_layering` | Sustained semitone/minor-ninth rubs inside pitched MIDI clips | Info/heuristic. Not proof of a wrong note or key; no automatic retuning. Drums excluded. |
| `empty_content` | Empty MIDI clips, zero-frame audio, possibly unused tracks | Info. Missing media is not empty; automation/live inputs prevent safe deletion assumptions. |
| `clip_boundaries` | Invalid ranges; non-bar endpoints | Invalid ranges are errors. Non-bar ends are info; no equal-length forcing or tail trimming. |
| `arrangement_overlaps` | Overlaps on the same Arrangement track | Warning. No destructive trim. |
| `warp_maps` | Monotonic coordinates and explicit filename-BPM consistency | Invalid maps error; half/double interpretations info; differing maps require review. |
| `stem_sync` | Explicitly declared linked stems: starts, ends, Warp state/maps | Warning. No groups configured -> `not_evaluated`, never assumed pass. |
| `instrument_assignments` | MIDI notes with no loaded device | Warning; check external routing before choosing an instrument. |
| `track_colors` | Configured role palette | Info; guarded color fix supported. |
| `session_settings` | Valid tempo; optional explicitly verified `expectedTempo` | Never guesses BPM/key or overrides the session. |
| `organization` | Several related ungrouped tracks | Info; actual `get_group_info` reads, no routing/reordering writes. |

Example overrides:

```yaml
lint:
  failOn: warning
  includeSession: false
  # target: {trackIds: ['track:3'], clipIds: ['track:3:arrangement:0']}
  rules:
    midi_grid:
      enabled: true
      severity: info
      params: {gridBeats: 0.25, toleranceBeats: 0.04}
    midi_overlaps:
      params:
        monophonicRoles: [bass]
        # monophonicTrackIds: ['track:3']  # Only after confirming this is a single voice.
    stem_sync:
      params:
        groups: [] # Explicitly linked full stems only; independent loops are not a group.
    harmonic_layering:
      severity: info
      params: {minOverlapBeats: 0.5}
```

Selectors intersect. Unknown target/rule IDs fail, rather than silently linting
nothing. `ORIGINAL` Session clips are protected even with `--include-session`.
Session-only clip presence prevents falsely classifying a track as unused.

## Boundaries of the implementation

This is structural/timing/metadata lint with real readback, not audio audition or
musical ground truth. The collector reads complete exposed MIDI and Warp state;
it uses group metadata so frozen tracks are not mistaken for groups. It captures
consistency failures if tracks are reordered/renamed or Arrangement coverage
changes while reading. The capture is not an atomic lock against concurrent editing.

`--fix` currently implements only names/colors supported by the installed bridge.
It does **not** erase notes, rewrite chords, quantize, flatten voices, trim loops,
delete tracks, regroup/reorder, collect assets or save an `.als`. Current note-ID
editing failed on this user's Live build; automation and source offsets also
cannot be safely preserved by a generic replacement. Such fixes require a tested
preserve-original MIDI helper and fuller automation/routing access. Their findings
remain visible after metadata fixes, with an appropriate exit status.

Key/chord correctness, cross-track harmony and phase-safe stem alignment require
verified musical/time context. A semitone-rub finding is a review hint, not license
to snap every note into a guessed scale. Arbitrary edited loops are never compared
as if they were synchronized full stems.

## Extension

`src/enableton/song_lint.py` has a separate `@rule(name, default_severity)` registry.
A rule is a pure `(state, params) -> findings` function. Add evidence and confidence,
set `fix=None` unless a guarded live writer is actually supported, register the
rule, configure it under `lint.rules`, and test both positive and intentional
counterexamples. Read failures must produce incomplete coverage, not a pass.

## Capture performance

Metadata, clip reads and consistency checks now use bounded bridge batches.
Reports expose `captureMetrics` and `captureScope`. Scoped Python captures use
`collect_live(connection, track_indices=[...])`; CLI `--track` still filters lint
findings after capture. See [Performance](PERFORMANCE.md) for scope and limits.
