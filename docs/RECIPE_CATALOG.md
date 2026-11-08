# Production recipe catalog

50 reference entries, 45 with primary sources. These include executable patch references and read-only methods; availability and evidence labels matter.

| Reference | Category | Status | Summary |
| --- | --- | --- | --- |
| Clean Sub | Sound design | MCP ready | Single sine carrier, phase retrigger, mono image, short click-reducing edges. |
| Dubstep Wobble | Sound design | MCP ready | Harmonic FM into saturation and a moving low-pass filter. |
| Brostep Growl | Sound design | MCP ready | Serial FM with different modulator envelopes; vowel filtering turns timbre changes into a growl. |
| Tearout Fm | Sound design | MCP ready | High-ratio serial FM, fast modulator decays, staged distortion and a clean low-end split. |
| Metallic Screech | Sound design | MCP ready | Inharmonic FM using Fine tuning, resonant band-pass motion, distortion and low-cut cleanup. |
| Wavetable Reese | Sound design | MCP ready | Two detuned wavetable oscillators form beating movement; saturation and low cutting separate the sub. |
| 808 Sub | Sound design | MCP ready | Sine bass with a short pitch drop and decaying amplitude; 808 Shaper adds controlled harmonics. |
| Yoi Bass | Sound design | MCP ready | FM harmonics through a scanning vowel filter; brief repeated envelopes make talking accents. |
| Ms Tonal Cleanup | Mastering | Reference | Stereo ambience or sides consume headroom or mask the centered kick/sub. |
| Selective Band Control | Mastering | Reference | Only particular bass notes or harsh midrange bursts overload an otherwise balanced mix. |
| Sub Aware Glue | Mastering | Reference | The mix needs slight cohesion but full-band compression pumps on long sub notes. |
| Staged Peak Control | Mastering | Reference | Sparse drum spikes force excessive final limiting; keep this optional on already distorted tearout. |
| Stereo Translation | Mastering | Reference | Wide bass texture or aggressive M/S processing changes the drop across playback systems. |
| Section Consistency | Mastering | Reference | Half-time sections, fakeouts or transitions hit the limiter differently from the main drop. |
| Delivery Qc | Mastering | Reference | Preparing release or comparison renders. |
| Wobble envelope | Movement | MCP ready | Smooth repeating filter or FM movement. |
| Growl envelope | Movement | MCP ready | Fast attack and uneven decay for growl articulation. |
| Yoi envelope | Movement | MCP ready | Repeated asymmetric vowel gestures. |
| Pluck envelope | Movement | MCP ready | Short decay gesture for percussive bass. |
| Sweep envelope | Movement | MCP ready | One gradual movement across the clip. |
| Machinegun envelope | Movement | MCP ready | Repeated gate-shaped bursts for gun articulation. |
| Duck envelope | Movement | MCP ready | Kick-timed gain reduction with hold and recovery. |
| Tearout phrases | Rhythm | MCP ready | Original seeded MIDI calls, responses and matching sub rhythm. |
| Tearout Triplet phrases | Rhythm | MCP ready | Original seeded MIDI calls, responses and matching sub rhythm. |
| Brostep phrases | Rhythm | MCP ready | Original seeded MIDI calls, responses and matching sub rhythm. |
| Dubstep phrases | Rhythm | MCP ready | Original seeded MIDI calls, responses and matching sub rhythm. |
| Halftime phrases | Rhythm | MCP ready | Original seeded MIDI calls, responses and matching sub rhythm. |
| Four-layer tearout gun | Layering | Reference | Combine sub, transient, body and noise with synchronized triplet rhythm. |
| Fast preset-led tearout workflow | Tutorial | Limited evidence | AYJINPLATES describes a fast workflow using Serum presets, distorted bass, clean low end and drums. |
| Resampling and call-response editing | Workflow | Reference | Print moving mid-bass material, select useful moments and arrange purposeful contrasts. |
| Sub MIDI overlap inspection | Workflow | MCP ready | Find overlapping sub notes and inspect note register and fundamental frequency. |
| Vocal-space wobble | Sound design | MCP ready | Original restrained FM wobble for answering a vocal hook; inspired by songwriting contrast, not a verified ALLEYCVT patch. |
| Robot FM bounce | Sound design | MCP ready | Original short FM burst with contrasting articulation for a robotic call; no exact Subtronics preset is reproduced. |
| Pitch-hook stab | Sound design | MCP ready | Original percussive pitched bass answer for a concise hook/fakeout arrangement; not the Laserbeam or SEE YOU DROP patch. |
| Shadow Reese | Sound design | MCP ready | Original darker detuned wavetable bass for a witch-house/darkwave study; VULPER synth choices are undocumented. |
| ALLEYCVT — hook/drop dialogue | Workflow | Reference | Let the vocal idea and bass phrase develop together while preserving a clear lead role. |
| ALLEYCVT — contrast and revision | Workflow | Reference | Compare a sparse vocal-led sketch and a heavier drop before committing to the arrangement. |
| Subtronics — tonal-delay laboratory | Sound design | Reference | Explore pitch from short delay feedback, then reshape the printed mid-bass texture. |
| Subtronics — register and dynamics contrast | Rhythm | Reference | Answer a forceful mid-bass gesture with a quieter or differently voiced event. |
| Ray Volpe / Volpetron — vocal-hook fakeout | Rhythm | Reference | Build anticipation by repeating a small vocal hook before releasing into the bass drop. |
| Ray Volpe / Volpetron — write drop two first | Workflow | Reference | Start with the most intense section, then design a catchier first drop around its core motif. |
| VULPER — dark-space production study | Layering | Reference | Original darkwave/witch-house exercise pairing a restrained detuned bass with a separate atmospheric layer. |
| VULPER — source and attribution notes | Tutorial | Limited evidence | Identify the requested artist while keeping undocumented production claims out of the library. |
| Riddim square-wave FM — Operator setup | Sound design | MCP ready | A concrete B-to-A Square D FM voice with sustained harmonic density, driven filtering and a separate sub. |
| 808 Shaper — rising Drive per note | Movement | Reference | Raise saturation during each 808 note, reset at its end, and apply a coordinated output trim. |
| Punchy midrange — linked FM, cutoff and vowels | Movement | Reference | Use contrasting note-aligned timbral gestures instead of running every modulation at the same free-running phase. |
| Found-sound layering — door, snap, demon and laser | Layering | Reference | Give separate layers a body, crack or attack role instead of stacking full-range sounds on every hit. |

Detailed steps, sources and limits are preserved in `data/recipes.json` and returned by `search_production_recipes`. Artist-informed entries are original adaptations, not copied artist presets.
