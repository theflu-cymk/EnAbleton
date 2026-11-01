# Warp analysis and reversible repair — EnAbleton beta

The tools distinguish measured source samples, marker-coordinate checks,
heuristic tempo/downbeat suggestions, and audible verification. A report does
not certify that every transient or musical downbeat is correctly placed.
Installing these tools does not change the current song.

## Workflow

1. Read `get_audio_clip_timing` with current track/clip names and Arrangement
   start guards. It includes all markers, including Live's hidden final marker,
   source path, source sample length/rate, available modes, loop/start/end
   coordinates and a bridge-lifetime clip identity.
2. Call `audit_warp_clip` for structural and optionally source-audio analysis.
   For many clips use `batch_warp_audit`: it returns per-clip failures and
   explicitly labels skipped audio/window/time budgets. It never recolors clips.
3. Choose a straight, triplet, or 2:1 swing grid. Off-grid attacks are review
   candidates, not automatically incorrect performance or bad warp markers.
4. Compare candidate and reference event positions with
   `compare_warp_reference`. Both arrays must use the same beat coordinate
   system. This estimates a constant offset; it does not identify drum roles.
5. Make explicit small marker moves with `preview_warp_repair`. Supply an
   empty Arrangement destination on the same track. The preview validates
   source identity, shift limits, source order and valid segment BPM. It does
   not edit Live and expires in ten minutes.
6. `apply_warp_repair` consumes that preview token once, saves a timing backup,
   rechecks the source file and clip fingerprint, then asks Live to duplicate
   the original into the free destination and move existing interior markers.
   Original anchors, source times and the original clip are preserved.
7. Readback checks every marker, placement, optional warp mode and original
   fingerprint. Failed repairs attempt to remove only the new preview. An
   operation ID in the preview name and local result journal support inspection
   after lost connections. Never blindly retry an uncertain write.
8. Audition the original and duplicate at matched levels. Playback never starts
   automatically; neither clip replaces the other automatically.

## Implemented analysis

- Bounded PCM WAV energy/onset extraction without stereo phase cancellation.
- BPM candidates with heuristic confidence and half/double-time alternatives.
- Candidate downbeats derived from periodic strong attacks. These are not
  semantic beat-one detection and require listening.
- Marker order, segment BPM and abrupt local stretch-change reports. Live's
  hidden terminal marker is treated as a mapping anchor rather than a visible
  transient that needs quantizing.
- Source tempo versus median warp-map tempo comparison, allowing half/double
  relationships. Source BPM different from project BPM alone is not an error.
- Transient-to-grid offsets for straight, triplet and 2:1 swing patterns.
- Explicit requested loop bar-count checking with the clip's time signature.
- Loop seam discontinuity estimate only when the analyzed source window
  exactly spans the loop. Click/artifact assessment still needs listening.
- Per-material warp-mode audition guidance, not automatic mode selection.

## Robustness and limits

Audio decoding runs in a subprocess capped at 25 seconds, 120 seconds of audio,
512 MiB input and a channel/sample budget. It supports integer PCM WAV;
compressed/float WAV and other formats fail explicitly rather than returning
fabricated tempo. Analysis uses decimated PCM probes, not full-sample peaks,
LUFS or true peak. Long source files are analyzed in windows; later sections
and tempo automation are not inferred.

Analysis caching uses source path, size, nanosecond modification time, analysis
window and hint. Cache size and preview counts are bounded. Repair previews
also retain source file metadata and a marker/target fingerprint. Changed
files, changed clips, stale previews, crossing markers, excessive moves,
unsupported marker APIs and occupied preview destinations are refused.

Only existing interior marker moves are executable; marker insertion/deletion
and destructive in-place correction are deliberately not implemented. The
actual Python marker-move API is capability-gated and verified after each
operation. Fake-Live and synthetic-audio tests do not certify real Live API
behavior or audio quality. A full Live restart loads the extension; reconnect
the MCP client to update its tool schemas.

`installer.py` validates and compiles staged files, refuses locally
modified Remote Script files, backs up the bridge/runtime, atomically replaces
individual files, verifies hashes, and restores prior files after failures.
The runtime version is centralized in `bridge_version.py`.

Primary reference: [Cycling '74 Clip API](https://docs.cycling74.com/apiref/lom/clip/),
including marker coordinate interpolation, the hidden last marker, supported
warp modes and marker-move semantics. Numeric detection thresholds here are
original heuristics, not Ableton-recommended universal settings.
