# Compatibility and limitations

- The development host is Windows with Live 12.2.5 Suite. Upstream 1.8.1 is
  pinned; capabilities vary by Live edition/version and device availability.
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
- Note-ID modifications preserve clips/identities but do not add/delete notes
  or edit MPE expression curves. Upstream tools have separate write semantics.
- Tests with synthetic audio/fake Live objects establish software behavior,
  not perceptual quality or a full Ableton compatibility certification.
- The server controls Live locally. It does not provide a native hosted-Grok
  connection or a network-authenticated remote control service.
- Commercial audio, presets, tutorial media and user sets are excluded.
