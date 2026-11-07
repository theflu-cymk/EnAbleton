# Reusable half-time remix workflow

Recipe version **1.1.0**, config schema **1** (1.0.0 inputs migrate additively). The package exposes a guided planner,
MIDI/pulse generator, guarded Live builder and explicit feedback loop. Planner
functions are read-only; the session tools render audio and edit owned lanes. The recipe
works with original riff audio, reconstructed MIDI, or a hybrid.

## Start guided, or supply a config

Ask EnAbleton: **“Guide me through a rock-to-dubstep flip. Keep the recognizable
riff and chorus singing, use held sub roots, and start with a short preview.”**

`guide_halftime_remix_workflow(answers={})` returns small groups of missing choices.
Supply answers progressively; the assistant can obtain source notes and timing
through the existing scoped Live reads. Defaults are suggestions, not answered
questions. Once the clip-relative offset and sources are known, the guide returns
a build plan. The session tools below bind sources, build and preview it. Automatic
transcription and stem extraction remain separate inputs.

## Complete short-section build loop

The [implementation plan](REMIX_V2_PLAN.md) defines the bounded first milestone.
Start with four or eight drop bars. The session functions are:

- `prepare_remix_session(config, sources, project_dir)` reads selected clips and
  source files, fingerprints them, renders immutable audio and saves a journal.
  It never edits Live. Use an empty absolute directory outside the source repo.
- `build_remix_session(project_dir)` rechecks sources, resolves native devices,
  maps actual occupied drum pads, and creates or updates its named owned tracks.
  New tracks start muted. Existing source tracks, global tempo and meter remain.
- `preview_remix_session(project_dir, bars=8)` temporarily isolates owned lanes,
  records Live Resampling, extracts the exact section and restores original track
  arm/mute/solo, loop and playhead state. It seeks before recording, verifies the
  running playhead and punches in before the preview starts. Leave at least one
  bar before the preview window. Stop playback and Session clips first.
- `compare_remix_previews(project_dir, reference, variant)` writes attenuation-only
  matched A/B WAVs using measured integrated LUFS, or a labeled RMS fallback.
- `plan_remix_midi_cleanup(target, policy)` proposes duplicate/fragment/overlap
  cleanup, gentle nearby-grid correction and optional lowest monophonic voice or
  octave register. It returns notes for a separate copy and preserves originals.
  Drum transcriptions need a separate policy: short hits are often intentional.
- `inspect_remix_session(project_dir)` reports stale bindings, owned track identity,
  partial build errors and uncertain creates without mutating the set.

Equivalent CLI commands:

```powershell
uv run enableton remix-prepare C:\Music\RemixLab --config config.json --sources sources.json
uv run enableton remix-build C:\Music\RemixLab
uv run enableton remix-preview C:\Music\RemixLab --bars 8
uv run enableton remix-compare C:\Music\RemixLab reference.wav variant.wav
uv run enableton remix-inspect C:\Music\RemixLab
```

`sources` maps `riff_midi`, `riff`, `vocal`, `rock_context` to objects containing a
guarded `target` (track/clip indices, Session/Arrangement view, expected names and
Arrangement start). Audio bindings optionally specify `source_start`: clip beats
when warped, seconds when unwarped. Without it, Arrangement sources are aligned to
the requested section; select a clip covering the whole range. Supply the MIDI
clip-relative `source_section_start_beat` explicitly. Flatten looping transcriptions
if the selected range extends outside their loop braces.

Aligned stems can specify `timing_reference` (another guarded audio target) to use
one correct Warp map despite inconsistent automatic import maps. The stem keeps
its own file identity and original timing snapshot. A measured
`source_offset_seconds` within +/-2 seconds can correct a known constant offset.
Verify source alignment first; equal file lengths alone do not prove alignment.

The renderer decodes the selected source window, follows its Warp-map slopes with
pitch-preserving atempo processing, and writes continuous-gain audio with short
boundary fades and normalized overlap-add at Warp seams. Pitched or non-unity clip-gain sources require a prior bounce;
Live track effects are not baked into raw source renders. Real-time preview captures
the actual new device chains. More than 128 nonredundant Warp intervals or a section
over 120 seconds requires a shorter selection or bounce. A/B sources must have the
same duration. Rendering uses existing bundled PyAV; no new dependency is required.

Immutable source/render assets are cached separately. A pulse change regenerates
riff gain processing while unchanged vocal audio remains cached. Edit the owned
**Session** `RMX | Pulse Input` clip, then prepare with `refresh_pulses=true` (CLI:
`--refresh-pulses`) and rebuild. Source MIDI pitch/timing changes are picked up by
preparing the bound transcription again. The renderer preserves the original
audio's pitch; changed transcription pitches do not retune recorded guitar audio.
Use MIDI rebuild mode or explicitly bounced/re-pitched audio for that decision.

Rebuilds retain their tracks and respect the original section boundaries. A new
section start/length needs a new project directory. Unexpected renamed tracks,
device-chain changes or output MIDI edits are refused rather than overwritten.
Edit the source transcription to keep rebuild inputs intentional. Partial content
writes are checked against the journal on retry. A lost track-create reply remains
an uncertain create; inspect it before retrying. Build/preview is not a blind
transactional rollback and does not silently delete uncertain tracks.

## Musical and audio review additions

- `root_overrides` maps absolute bar numbers (strings) to source-register MIDI
  pitches before the sub octave shift. Root alternatives expose duration/velocity
  support and `needs_root_review`, not calibrated chord-recognition confidence.
- `vocal_regions` contains ordered `{start,end}` drop-relative beat windows. The
  optional inference is level-based activity detection, not words/lyrics. Explicit
  windows take precedence. Bass audio/automation ducks around these regions;
  phrase answers avoid occupied vocal windows.
- `phrase_variation` and `bass_palette` generate call/response roles and native
  filter-depth gestures. `wobble`, `growl`, `smooth`, `riff` are editable starting
  gestures, not artist presets. Reverse-tail FX and optional chop answers become
  actual rendered audio, rather than just lane labels.
- Utility gain automation is calibrated through the bridge's displayed-dB setter
  and readback; native normalized values are not assumed to be linear amplitude.
  Audio assets use sample-continuous gain; MIDI-device automation remains a bounded
  approximation. Native smooth LFOs handle the filter motion.
- Preview metrics include sample peak/RMS, FFmpeg loudnorm input LUFS/true peak,
  a labeled approximate low-band correlation check, and existing problem scanning.
  If the audio filter cannot return loudness metadata, the result says unavailable.
  None of these measurements proves the hook, vocal placement or mix sounds good.

Source audio, journals, previews and A/B files stay in the private project folder.
Use Live Save/Collect All and Save for portable sets; no automatic mastering or
unsupported save API is implied. Actual Live compatibility/musical evaluation will
be tested on the user's selected new song; synthetic and fake-Live tests are kept
distinct from those results.

The three MCP functions are:

- `guide_halftime_remix_workflow(answers)` — guided source/style/section decisions.
- `plan_halftime_remix_workflow(config)` — exact MIDI events, pulse recipes, layer
  roles, alignment decisions and verification requirements.
- `refine_halftime_remix_workflow(config, feedback)` — a revised config and plan
  with an explicit iteration history and explanations.

The Python functions have the same names without `_workflow`, in
`enableton.remix_workflow`. `pulse_gain_at()` evaluates continuous gain in linear
amplitude. It is not a normalized Live mixer fader value.

```powershell
uv run enableton remix-guide
uv run enableton remix-plan examples/remix/rock-flip.json --output my-plan.json
uv run enableton remix-refine examples/remix/rock-flip.json --feedback smoother vocal_masked --output revision.json
```

Outputs are JSON. `--output` creates a new file and refuses to overwrite one.
For `remix-refine`, save the returned `config` member as the next input config;
the wrapper also contains the revised plan and explanations. You can instead
pass that complete wrapper to the CLI, which extracts its `config` member.

## What the recipe keeps distinct

Keep the project grid and rebuild the slow backbeat; merely lowering tempo or
holding notes is insufficient. The documented Native Instruments example uses
140 BPM with the main snare on beat three. Formal cut time (2/2 notation) and
half-speed playback are separate decisions. This planner intentionally supports
4/4 and does not silently rewrite meter or transpose the source.
[NI tutorial](https://blog.native-instruments.com/how-to-make-dubstep/),
[Ableton: Choosing a Tempo](https://cdn-resources.ableton.com/resources/uploads/makingmusic/MakingMusic_DennisDeSantis.pdf).

Select the recognizable hook and give it a new rhythm foundation. Source stems,
MIDI cleanup and sample chopping are established remix building blocks; the
Ableton demonstration uses newer Suite features, so the guide requests existing
stems/MIDI when the installed version or connector cannot produce them.
[Ableton / Side Brain](https://www.ableton.com/en/blog/a-step-by-step-guide-to-remixing-a-track/).

Riddim sound design can be economical: Dan Larsson's course outline includes
a single-LFO patch and different reverb/filter variations. Our repeating rhythms
and occasional triplet offsets are original exercises, not claims that every
riddim track follows one pattern. Resampling is an optional way to develop a
palette of phrases from a synth performance.
[W. A. Production](https://www.waproduction.com/videos/view/riddim-bass),
[ICON / Kompany](https://www.iconcollective.edu/bass-resampling-with-serum).

## Reusable creation stages

1. **Sources and alignment.** Identify the riff, isolated singer and rock lead-in.
   Read actual source paths, source/clip offsets and Warp maps. Keep originals.
   Beat zero in source MIDI is clip-relative; `source_section_start_beat` is the
   point within that clip aligned to the new drop. The example's source beat 96
   aligns to Arrangement beat 100 because its source clip starts at beat 4.
2. **Harmony.** Keep existing pitches. The riff can retain all notes or the lowest
   note at each onset, explicitly reported. For each bar the sub chooses the
   lowest sounding note on the barline, otherwise the first upcoming note, else
   the latest prior note. Those are heuristics; a passing note or inversion can
   require a musical correction. Each sub note lasts exactly four beats.
3. **Low end.** Put one clean, mono root under a separate harmonic bass/riff layer.
   Avoid driving entire low chords into distortion. Default sub transposition is
   one octave; any further octave fitting to the requested register is reported.
   High-pass the mid layer by ear, using the suggested Hz as starting points.
4. **Groove and motion.** Build snare-on-three drums with the actual kit's pad map.
   The planner suggests GM pitches 36 kick, 38 snare, 42 closed hat; these are not
   guaranteed to match arbitrary racks. Pulse gain and filter motion can change
   while the root holds. Make deliberate answers and phrase variations.
5. **Vocals and entrance.** Keep complete sung lines when they carry the chorus.
   Place chops/wet answers in gaps. Try a small pre-drop reduction in density,
   low end or gain; use FX as punctuation. Preserve the lead-in's timing and pitch.
6. **Build and verify.** Read fresh target identities, create new lanes, check
   actual parameter units/routing, then verify notes, clip boundaries, envelopes,
   active meters and original backup states. Audition the lead-in and full drop
   at matched loudness. Check mono low end, snare clarity and vocal intelligibility.
7. **Refine one problem.** Feed explicit listening feedback back into the recipe,
   compare versions, and keep the version that better expresses the intended hook.

## Lessons from The Red session

- Real riff audio preserves identity; MIDI can carry sections whose progression
  differs from the intro. Do not force one intro loop over every later phrase.
- We built native Operator/sub/drums and sampled riff layers. The captured session
  verified note counts, arrangement positions, device settings and active meters.
  It did not establish a mastered, listened-to, exact reference match.
- External Gate input routing was unavailable through this session's connector,
  even after sidechain was enabled. This is a connector/session finding, not a
  claim that Ableton Gate lacks sidechain support. The usable fallback is a shared
  pulse recipe and rendered gain or copied automation. Editing MIDI afterward
  does not automatically regenerate rendered audio.
- Continuous gain edges matter. `pulse_gain_at()` supplies raised-cosine attack
  and release ramps. A renderer must also fade the start/end of the whole clip
  and handle overlap properly. A nonzero floor is not an end-of-clip fade.
- Filter movement should use a smooth native LFO or properly smoothed processing;
  sparse automation steps are not a sample-smooth envelope. Never treat a raw
  0..1 parameter as Hz/dB/ms without inspecting its displayed mapping.
- Holding a note while pulsing its timbre is different from compressing an uneven
  level. Clicks, gaps and stepped modulation need targeted repairs. Distortion
  aliasing needs suitable anti-aliasing/oversampling, not a faster compressor.
- The note-ID modification command failed in this installation. New Session clips
  with complete note sets, followed by verified Arrangement duplication, worked.
  Preserve a full-length destination before setting loop braces; in this session,
  writing braces while nonlooped shortened the Arrangement region.
- Starting transport resumed a different marker; verify song time after starting.
  A meter spot-check is not a full-pass true-peak or integrated loudness scan.
  Live's save API was unavailable: use Live Save and Collect All and Save.

## Iteration and extension

Supported feedback keys: `too_guttural`, `too_busy`, `vocal_masked`,
`kick_sub_clash`, `weak_transition`, `clicks`, `more_riddim`, `smoother`.
These are transparent rules based on user feedback, not automatic audition or
self-training. `kick_sub_clash` produces gain-dip instructions at generated kick
times; a real kick clip requires its actual event positions. `vocal_masked`
produces a duck-depth suggestion, not automatic syllable detection.

Profiles and source provenance live in packaged `remix_recipes.json`. Override
validated controls under `overrides`, including pulse/kick patterns, motion speed,
gain edges and filter ranges. Use deterministic configs, config fingerprints,
versioned recipes and explicit feedback histories to compare improvements.
Change schema/recipe versions deliberately when semantics change.

The current adapter builds the plan in Live and regenerates cached audio. A
dedicated Max for Live realtime MIDI-envelope device remains optional future work. A live sidechain request
is only a request until current routing has been verified. No hidden plug-in
controls or specific paid instruments are required by the planner.

## Aligning a continuous stem to an existing arrangement

Use a vocal phrase or another clear musical onset as the anchor. Inspect the
stem's current source trim and Arrangement position before editing. Verify the
source tempo from multiple onsets where possible. A filename BPM is a hint.

For a constant tempo change, render a pitch-preserving copy at target BPM divided
by source BPM. For example, 96 to 120 BPM uses a 1.25 playback rate. Carry the
existing source trim into the render or map it into the new file. Keep the
original media and an undo path. When placing a pre-stretched copy, inspect Warp
and the start marker so Live does not apply a second stretch or shift the onset.

Check the new clip's position, trim, and duration, then compare an early and a
late phrase against the arrangement. A constant offset calls for a placement
adjustment. Drift or structural differences call for separate section alignment
or verified warp anchors. A matching BPM alone does not verify phrase alignment.
