"""Caption-grounded learning from BassTi, with clearly separated adaptations."""

from copy import deepcopy
from .bass_patterns import phrase

SOURCE = {
    "title": "BassTi — The Last TEAROUT Tutorial You Need (2026 Step-By-Step)",
    "url": "https://www.youtube.com/watch?v=FGXP_8URE5w",
    "evidence": "English auto-generated captions and public description; video controls and audio were not directly inspected",
    "limits": "Auto-captioned product names can be wrong. Exact filter frequencies, gains and time offsets were not inferred.",
}

OBSERVATIONS = [
    {"time": "02:18", "seconds": 138, "method": "Triplet-grid rhythm underpins the gun pattern."},
    {
        "time": "02:52",
        "seconds": 172,
        "method": "The sub is cleaned, dispersed and processed with a tuned Corpus Kick Tight preset.",
    },
    {
        "time": "03:31",
        "seconds": 211,
        "method": "A kick-derived transient is low-cut, frequency-shifted, distorted and shortened with transient shaping.",
    },
    {
        "time": "04:02",
        "seconds": 242,
        "method": "The body layer uses sample-following modulation to move a filter-table position.",
    },
    {
        "time": "04:38",
        "seconds": 278,
        "method": "A separate noise layer supplies heavily processed upper-frequency texture.",
    },
    {
        "time": "06:24",
        "seconds": 384,
        "method": "Sub, transient, body and noise feed a shared processing group.",
    },
    {
        "time": "07:26",
        "seconds": 446,
        "method": "Parallel low/high lanes allow the low foundation and upper texture to be treated separately.",
    },
    {
        "time": "08:52",
        "seconds": 532,
        "method": "A parallel self-ring-modulated high-frequency lane is blended with the main signal.",
    },
    {
        "time": "09:43",
        "seconds": 583,
        "method": "A short whole-signal delay changes timing feel; the exact millisecond value is not stated.",
    },
]


def gun_blueprint(bars=4, root_midi=29, seed=0):
    base = phrase("tearout_triplet", bars, root_midi, "sub", seed)
    layers = []
    for role, duration, pitch, velocity in [
        ("sub", None, root_midi, None),
        ("transient", 0.055, 36, 116),
        ("body", None, root_midi + 12, None),
        ("noise", 0.09, 60, 65),
    ]:
        notes = deepcopy(base["notes"])
        for note in notes:
            note["pitch"] = pitch
            if duration is not None:
                note["duration"] = min(duration, note["duration"])
            if velocity is not None:
                note["velocity"] = velocity
        layers.append({"role": role, "length": base["length"], "notes": notes})
    return {
        "source": SOURCE,
        "caption_observations": OBSERVATIONS,
        "original_example_material": {
            "style": "tearout_triplet",
            "layers": layers,
            "note": "Original synchronized MIDI example, not a transcription of the tutorial pattern",
        },
        "native_adaptations": {
            "sub": "Operator sine or a cleared 808 sample; optional 808 Shaper, mono Utility, carefully tuned Corpus.",
            "transient": "Short kick-derived hit into EQ Eight, Shifter, Saturator and transient shaping with Drum Buss.",
            "body": "Existing FM recipe or sample; Auto Filter envelope follower for audio-reactive movement. A drawn envelope is only a rhythmic approximation.",
            "noise": "Short filtered noise or textured sample; separate low-cut and restrained distortion.",
            "bus": "An Audio Effect Rack can provide separate low/high processing lanes; audition and gain-match their recombination.",
        },
        "not_equivalent": [
            "Native Shifter ring modulation is not identical to self-ring modulation.",
            "No exact native Disperser or third-party spectral/filter-table chain is claimed.",
        ],
        "execution": "Read-only blueprint and MIDI material. Does not create tracks, bus routing, followers, parallel racks, render audio or alter the song.",
        "executable_now": "Use style=tearout_triplet with create_bass_phrase or phrase_style=tearout_triplet with create_native_bass.",
    }
