# Audio problem scan and repair suggestions

`enableton scan-audio` and the read-only MCP tools `scan_audio_problems` and
`scan_clip_audio_problems` inspect a local integer PCM WAV and return timestamped
review candidates with targeted repair recipes. They never normalize, overwrite,
upload, start playback, insert effects, or automatically smooth the source.

```powershell
uv run enableton scan-audio "F:\stems\bass.wav" --start-seconds 20 --max-seconds 30
uv run enableton scan-audio "F:\stems\bass.wav" --report "F:\reports\bass-scan.json"
```

JSON goes to stdout. Only explicit `--report` writes a file; its parent must exist
and an existing report is never overwritten. Exit codes: 0 no findings in window,
1 review candidates, 2 unsupported/invalid input, scan failure or report-write error.
Silence uses null dBFS rather than non-JSON infinity. No findings is not a clean bill
of health. Audition the result at matched loudness before choosing processing.

To scan a Live clip, call `scan_clip_audio_problems` with `target` containing
`track_index`, `clip_index`, `clip_view` (`session` or `arrangement`), plus available
`expected_track_name`, `expected_clip_name` and Arrangement `expected_start_time`.
The current source timing determines the window; timing is checked again afterwards.
These are source-file timestamps, not Arrangement positions. Clip fades, devices,
automation, pitch and the sound of Warp playback are not rendered. For those, scan
a separately rendered PCM WAV. A clip scan does not require a new Remote Script.
Restart the MCP server after updating the Python package to expose the new tools.

## Evidence and bounds

- Reads every sample in the reported window: sample peak, RMS, signed DC mean,
  integer rail-sample counts. These are not LUFS or true peak.
- Review heuristics: adjacent-sample change above 0.35 full scale (10 ms event
  debounce), rail runs (possible overload, not proof of clipping), mean DC above
  0.01 full scale, 10–500 ms near-silent blocks bracketed by signal, and adjacent
  10 ms RMS blocks differing by at least 12 dB. Intentional transients, rests,
  gates and bright waveforms can trigger findings. Thresholds are original
  engineering starting points, not perceptual guarantees.
- Integer PCM WAV only, 8/16/24/32 bits, 8–192 kHz, 1–8 channels. Float WAV,
  compressed formats and unavailable media fail explicitly; export a PCM copy.
- Maximum 120 seconds, 512 MiB file, 4 million interleaved channel samples, 25
  seconds worker time. `coverage` reports the actual window and partial status.
  Choose subsequent windows explicitly; this does not silently scan the whole song.
- Up to 24 examples per finding code; total candidate counts are preserved.
  Timestamps are quantized to sample boundaries or 10 ms blocks as appropriate.
- Hum/hiss spectra, stereo correlation, aliasing, separation artifacts and the
  cause of pumping/gating are not assessed. No audio audition has occurred.
- File size/mtime are checked before and after reading; changed files or clip
  timing invalidate the scan. No previews or writes are generated.

## Choosing a repair

Each finding references a recipe. Edit clicks call for fades/crossfades; isolated
internal clicks call for local de-click; suspected gaps call for interpolation or
replacement; level mismatches call for clip gain before gentle compression. DC
findings call for a longer-window check before DC removal. Rail runs call for
audition before de-clip or replacement. Compression is not a continuity repair.
The fade/compression values in recipes are original starting points, not copied
presets. Equal-power crossfades are not universal: correlated material can rise in
level at the midpoint. Use the curve that preserves the transition.

Primary references: [Ableton clip fades](https://help.ableton.com/hc/en-us/articles/209069969-Create-Fades-on-Clip-Edges-to-avoid-clicks),
[iZotope De-click](https://help.izotope.com/docs/rx-plug-in-pack/De-click.html),
[iZotope Spectral Repair](https://downloads.izotope.com/docs/rx6/35-spectral-repair/index.html).
