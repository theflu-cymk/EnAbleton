# EnAbleton v0.2.0 — Melody-to-Beat Matching

Status: proposed roadmap; no matching features are implemented by this document.
Target prerelease: **v0.2.0-beta.1**. Python version: **0.2.0b1**.
Planning baseline: v0.1.0-beta.1 (191 tools, 13 bass patches, 47 references).
The existing release and running Live installation remain unchanged.

## Outcome

Turn “make this melody fit that drum beat” into an inspectable workflow:
identify the clips and musical section, analyze their timing and phrase structure,
propose a few distinct fits, explain the changes, and apply a selected version
without overwriting the original. Timing, musical phrasing, and harmonic changes
are separate choices. A computed score is not proof that a melody sounds good.

Example request:

> Match the Serum melody to the kick and snare from bar 33 up to bar 49. Keep
> its pitches and main motif, preserve the triplet pickups, and make three
> versions: tightly locked, syncopated, and more spacious. Preview first.

The first release should make this reliable for MIDI melodies and MIDI drum
references, and useful for MIDI melodies matched to clearly percussive audio.
Extracting a reliable melody from an arbitrary full mix is a separate problem.

## Scope and priorities

### P0 — Required for the next prerelease

1. **Musical timeline and target capture.** Record track/clip identities, names,
   start/loop offsets, selected section, clip/source coordinates, current meter,
   tempo information and source-file identity. Convert bars to quarter-note beats
   correctly. Support pickups and loops that begin away from source beat zero.
   Do not assume the current tempo describes a tempo-automated section; refuse
   unsupported tempo/meter maps or require a confirmed stable subsection.
2. **Reference beat map.** Read MIDI drum hits with configurable kick/snare/hat
   note mappings. For audio drums, extend bounded onset analysis and report
   likely beat anchors with confidence and manual corrections. Do not equate
   every transient with a kick or every strong attack with musical beat one.
3. **MIDI melody analysis.** Report onset/duration/velocity patterns, phrase length,
   repetition, pitch range, contour, rests, polyphony and overlap. Identify possible
   loop-length drift without deciding that every nonstandard phrase is wrong.
4. **Groove-aware timing fit.** Offer constant offset, explicit tempo-ratio scaling,
   phrase-boundary alignment and strength-limited local timing adjustments. Handle
   half/double-time, straight eighths/sixteenths, triplets and extracted/custom
   swing offsets. Keep note order and preserve intentional pickups and rests.
5. **Three explained candidates.** Generate “locked”, “syncopated”, and “space /
   call-and-response” options. Preserve pitches by default. Report changed notes,
   maximum timing movement, rhythm changes and remaining uncertainties.
6. **Non-destructive application and A/B.** Preview as data first. Write only a
   selected candidate into an explicitly free destination/slot; preserve the
   original and its device chain. Never launch playback, replace a clip, duplicate
   an audible full track, or clone hidden Serum settings implicitly. Audition is
   a separate explicit action with captured state and a restoration path.

### P1 — Required before a stable v0.2.0

- **Optional harmonic fit.** Prefer a user-confirmed key/chord progression or an
  explicit reference MIDI progression. Treat inferred key as evidence with
  alternatives, not a fact; Live's default C-major metadata is not sufficient.
  Offer minimal pitch corrections, chord-tone emphasis on strong beats, range
  limits and smaller leaps while preserving contour and motif identity.
- **Articulation-aware duration edits.** Separate lead, bass, arpeggio and pad
  behavior. Preserve intentional legato/chord overlaps; trim accidental overlaps
  per voice rather than flattening all polyphony into one monophonic line.
- **Section development.** Add opt-in 4/8/16-bar variation, fills, phrase endings
  and call/response gaps. Respect explicit “keep these notes”/locked regions.
- **Project-level preview report.** Show bar/beat placement, rhythmic anchors,
  candidate differences, harmony assumptions and analysis coverage before apply.
- **Drum-request intake.** Incorporate the agreed questions: section, full kit vs
  one-shot, groove, layer/replace, timing feel, sound/intensity, variation and
  playback. Infer already-known answers from Live; ask only for missing choices.

### P2 — Optional/stretch work, not a beta release blocker

- Broader local audio decoding through a pinned, bounded decoder while retaining
  explicit format errors and source-window coverage reports.
- Local monophonic pitch tracking for isolated bass/lead/vocal stems, with octave
  error flags and a separate transcription confidence report.
- Polyphonic chord estimation and full-mix stem separation only after a dedicated
  evaluation/licensing/dependency decision. No automatic heavy-model downloads
  and no cloud audio uploads by default.
- A small interactive before/after piano-roll and beat-map viewer. Keep the
  reference website separate from live control unless deliberately integrated.

## Matching engine design

Use a shared event representation: clip-relative beat, source seconds where
applicable, MIDI note ID/voice, duration, velocity/strength, role, confidence,
locked status and provenance. Preserve mappings back to the original clip.

Apply the least invasive transform that satisfies the request:

1. Diagnose beat-one/offset errors before altering individual notes.
2. Resolve half/double-time ambiguity and any explicitly requested phrase length.
3. Align phrase starts, endings and selected accents to reference anchors.
4. Adjust internal notes with a configurable strength and maximum movement.
5. Optionally alter durations; optionally alter pitches in a separate stage.

Do not silently shorten a 71-beat phrase to 64 beats or transpose it into F minor.
Show the proposed interpretation and alternatives first. Sparse, syncopated and
polyrhythmic references may be genuinely ambiguous and should remain so.

Rank candidates with separate, inspectable components rather than one opaque
“musical quality” number:

- Timing agreement with selected kick/snare anchors.
- Phrase/downbeat alignment and loop drift.
- Preserved inter-note rhythm, contour, motif and locked events.
- Desired note density, rests and call/response space.
- Harmonic compatibility only when an explicit/evidence-backed harmony target exists.
- Edit cost: how many notes changed, how far they moved and how many pitches changed.

Weights and constraints belong to the request/profile. Hat subdivisions should
not automatically overpower kick/snare anchors. Scores are diagnostics, not
calibrated probabilities or perceptual mastering measurements.

## Proposed MCP surface

Names are provisional; generate the final catalog from the actual registry.

| Tool | Responsibility | Effect |
| --- | --- | --- |
| `analyze_melody_clip` | MIDI motif, phrasing, register, articulation and drift | Read-only |
| `extract_reference_beat_map` | MIDI/audio reference events and confidence | Read-only |
| `compare_melody_to_beat` | Diagnose offset, groove and phrase mismatch | Read-only |
| `preview_melody_fit` | Ranked candidates, assumptions and change diffs | Read-only |
| `preview_harmonic_fit` | Optional constrained pitch alternatives | Read-only |
| `apply_melody_fit` | Apply a reviewed candidate to a free destination | Write |
| `audition_melody_fit` | Explicit playback/selection with state capture | Write |
| `restore_fit_audition` | Restore the captured playback/mute/selection state | Write |
| `export_fit_report` | Local JSON/Markdown evidence and candidate report | Local file write |

Reuse existing nested device inspection, note-ID reads, version/capability checks,
preview-token handling and backup/journal primitives. Avoid multiple overlapping
APIs that expose the same operation with different semantics.

## Robustness work bundled with matching

- **Stable identity and concurrency:** fingerprint source/reference clips and the
  musical timeline together. Refuse apply if either changes. Add request IDs and
  duplicate-operation detection. Serialize related musical writes.
- **Preservation:** original clips stay intact. Preserve loop/start/end bounds,
  note probability, velocity and articulation where supported. If MPE/expression
  cannot be preserved, block apply or clearly limit the preview; do not drop it.
- **Transactions:** preflight the entire plan and destination before writing;
  save a local source/candidate backup, apply in one Undo group where possible,
  and verify readback. Document partial-failure and restoration behavior.
- **Timeouts:** never automatically replay an uncertain write. Return operation
  IDs and a way to inspect whether a candidate already exists.
- **Bounded work:** windowed decoding, cancellation/progress, bounded caches,
  per-clip failure reports and resumable batches. Label skipped regions explicitly.
- **Privacy:** keep audio and reports local by default; no telemetry or preference
  learning without explicit opt-in. Distribute only synthetic/licensed fixtures.
- **Compatibility:** probe actual APIs before offering writes. Publish a Windows
  Live 12.2.5 test record and record other versions separately, without claiming
  that Python CI proves Live runtime compatibility.
- **Release hygiene:** preserve dependency locks, licenses and existing recipes;
  generate tool catalogs, smoke-test wheel/sdist installation and keep published
  tags immutable.

## Delivery milestones

| Milestone | Deliverable | Exit condition |
| --- | --- | --- |
| M1: timeline and fixtures | Shared event/timeline types, target snapshots, coordinate tests, reference corpus | Correct round trips for offset loops, pickups and 3/4, 4/4, 6/8 fixtures; ambiguous maps refused |
| M2: rhythm matcher | MIDI beat maps, melody analysis, constant/ratio/groove transforms | Known offsets and half/double cases recovered; triplets/swing and locked notes preserved |
| M3: candidate workflow | Three candidate profiles, diffs, scoring and local reports | Deterministic seeded output with explained tradeoffs and no writes during preview |
| M4: guarded apply | Original-preserving candidate application, journals and A/B restoration | Stale targets, occupied destinations and injected failures leave originals unchanged |
| M5: audio references and harmony | Bounded drum-audio matching and opt-in harmonic constraints | Coverage/confidence visible; uncertain beat-one/key not silently resolved |
| M6: release qualification | Real Live checks, documentation, packaged prerelease | Acceptance gates below pass; limitations and deferred work published |

No calendar estimate is committed until M1 exposes the remaining Live API and
analysis dependencies. Ship the P0 workflow first rather than hiding it behind
unvalidated full-mix transcription.

## Acceptance gates

These are proposed release targets, not claims about the current implementation.

### Automated

- Preserve all original clip/note data in synthetic failure/stale-target tests.
- Recover known constant offsets within one timeline tick for exact MIDI fixtures.
- Recover 70/140 and 75/150 relationships or explicitly report ambiguity.
- In controlled quantized fixtures, align selected anchors within 1/960 beat;
  use separate, measured tolerances for human/audio performances.
- Preserve triplet/custom-groove offsets unless the request explicitly changes them.
- Preserve all locked notes, note order and bounds; produce no unintended overlaps
  in monophonic fixtures. Keep intended chord/legato overlap fixtures intact.
- Keep pitches unchanged in rhythm-only mode; enforce explicit scale/chord/range
  constraints only when harmonic editing is enabled.
- Verify previews cannot write, expired tokens cannot apply, changed references
  invalidate candidates, and identical requests/seeds reproduce identical plans.
- Keep the complete existing regression, transport, packaging and CI checks green.

### Real Live and listening

- Verify MIDI-to-MIDI matching, MIDI-to-drum-audio matching, offset Arrangement
  clips, Session candidates, half-time sections, triplets, swing and an ambiguous
  source on the supported host. Record which APIs were actually exercised.
- Verify original preservation, Undo, interrupted operations and audition-state
  restoration in Live; do not substitute fake-Live tests for these checks.
- Audition at least six synthetic/owned examples covering a lead, bassline, arp,
  chordal part, syncopated phrase and sparse/ambiguous reference. Use a repeatable
  human rubric for groove, phrase fit, motif preservation and audible artifacts.
- For every example, publish an honest result: improved, unchanged, worse or
  insufficient evidence. Do not force a success label from a timing score.

## Version and documentation changes

Begin with `v0.2.0-beta.1` / `0.2.0b1`; progress through further beta/RC tags before
stable `v0.2.0`. Keep upstream and bridge-protocol versions distinct. If bridge
commands change, bump the protocol deliberately and provide upgrade/rollback
steps. Update README, installation guide, feature/tool catalogs, changelog,
limitations and the recipe/reference library where new sourced methods are added.
