# Compatibility and limitations

- The development host is Windows with Live 12.2.5 Suite. Upstream 1.8.1 is
  pinned; capabilities vary by Live edition/version and device availability.
  Only Windows is supported for this beta: macOS is untested and unsupported,
  and Linux is not supported. Editions and individual 12.x builds are
  unverified; the Live 12 floor is the only enforced compatibility claim.
- Live calls are refused when the running session reports a build below Live
  12.0, before any command is sent. The generated bridge reports the build it is
  running inside; `doctor` shows it. Only that floor is claimed: editions and
  individual 12.x builds are unverified. A bridge that cannot report a build is
  shown as unverified, not refused.
- Beta warp analysis supports integer PCM WAV, uses bounded/decimated energy
  measurements, and reports uncertain/partial results explicitly. Its source
  peak estimate is not full-sample peak, true peak or LUFS.
- Tempo, downbeats, groove alignment and loop seam risks are heuristic. A
  source BPM different from the project BPM is not itself a clash when warped.
- Warp repair moves existing interior markers on a free duplicate. It preserves
  anchors and originals, but the real Python API remains capability-gated and
  needs runtime readback. No original is automatically replaced or auditioned.
- Direct Arrangement automation, track reordering, plug-in windows, Preferences,
  audio-to-MIDI conversion and hidden plug-in controls are not added.
- Added envelope tools operate on Session clips. Their linear curves use
  bounded hold-step approximation. Audio clip coordinate units differ when
  Warp is off; inspect timing before editing.
- Note-ID edits preserve the clip and its other notes; edited notes get new IDs
  because Live edits them by remove/re-add. Insert and delete are separate guarded
  commands. None rewrite MPE expression curves. Upstream tools have separate write
  semantics.
- Live exposes no API to create a group track or move tracks into one, and
- Arrangement clip extents are settable through `loop_end`/`end_marker` (beats when warped, seconds when unwarped); `end_time` is read-only.
  clip resizing writes `loop_end`.
- Measured against Live 12.2.5 on the development host: `RackDevice` exposes
  neither `insert_chain` nor `delete_chain`, and a rack or Drum Rack loaded from
  the browser reports no chains, so `insert_chain`, `delete_chain` and
  `insert_device_to_chain` refuse with that message; add chains in Live itself.
  A deleted `CuePoint` handle is dead, and reading its `time` raises a
  Boost.Python argument error, so `delete_cue_point` moves the playhead with a
  separate command, verifies the cue count and reports the position recorded
  before the toggle. An EQ Eight keeps its preset name on load, so EQ
  bands are matched by device class `Eq8`.
- Tests with synthetic audio/fake Live objects establish software behavior,
  not perceptual quality or a full Ableton compatibility certification.
- The server controls Live locally. It does not provide a native hosted-Grok
  connection or a network-authenticated remote control service.
- Commercial audio, presets, tutorial media and user sets are excluded.
