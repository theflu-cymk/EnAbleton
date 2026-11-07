# Remix workflow: implementation plan and acceptance criteria

Build one complete short-section loop before adding more style presets. Reuse the
existing Live bridge, native devices, PCM scanner and bundled PyAV. Do not introduce
a second DAW-control layer, hidden UI automation or mandatory model services.

1. **Improve the musical plan.** Add explicit bar-root overrides, scored root
   alternatives, vocal activity windows, phrase roles, concrete FX/chop events and
   a small bass palette. Preserve source note timing and pitches unless requested.
2. **Bind real sources.** Read only selected clip targets; capture notes, Warp maps,
   file identity and source ranges. Reject stale bindings before applying changes.
3. **Render repeatably.** Use continuous gain, pitch-preserving time stretch, proper
   file-edge fades and actual vocal windows. Cache immutable assets by source and
   recipe fingerprints. Regenerate changed assets, reusing unchanged audio.
4. **Build in Live.** Create named owned lanes, native instruments, kit-mapped MIDI,
   source audio and automation. Journal partial work. Re-running must reuse owned
   tracks, reject unexpected user edits and never overwrite source tracks.
5. **Preview and compare.** Capture a bounded section with monitoring off and no
   other armed tracks. Verify the playhead after starting, restore transport/mixer
   state, measure the rendered file and provide level-matched A/B audio.
6. **Verify and document.** Test musical rules, real audio DSP, stale rejection,
   rebuild/no-duplicate behavior, interrupted operations and preview restoration.
   Exercise MCP transport, lint, formatting and packaged resources. Test the
   selected song on new owned lanes while preserving original clips and media.

Acceptance: a selected short riff and optional vocal can become a reusable plan,
rendered assets and a verified new-track build; a changed MIDI/pulse plan rebuilds
without duplicating tracks; reference/variant WAVs can be compared at matched
loudness. Tests must distinguish synthetic/fake-Live checks from actual Live
readback and musical listening. Do not label a passing test as a good-sounding mix.

Deferred specialist features: automatic polyphonic transcription/stem extraction,
semantic lyric recognition, a dedicated Max for Live realtime envelope device,
certified metering, and automatic full-song mastering. Existing stems/MIDI and
explicit activity/root corrections remain supported inputs.

Implemented adapters now cover all six stages. Conservative MIDI cleanup and
shared stem timing were added during integration. Regression tests cover Warp
seam normalization, source preservation, float-valued native note readback,
exclusive auto-arm restoration, infinite gain endpoints, browser/device identity,
rebuild reuse and recording-file release before analysis. The development catalog
and distribution-resource checks include the new modules and tools.
