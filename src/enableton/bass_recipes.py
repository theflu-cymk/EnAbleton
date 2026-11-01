"""Original, editable starting patches derived from documented synthesis methods.

Numbers are engineering starting points, not transcriptions of artist presets.
All parameter values use Live's native API range, not displayed Hz/dB/ms.
"""

from copy import deepcopy

SOURCES = {
    "operator": {
        "title": "Ableton Live 12 instrument reference: Operator, Analog, Wavetable",
        "url": "https://www.ableton.com/en/manual/live-instrument-reference/",
        "supports": "FM topology, modulator level and envelopes, integer coarse/fractional fine tuning, detune, wavetable scanning",
    },
    "effects": {
        "title": "Ableton Live 12 audio effect reference",
        "url": "https://www.ableton.com/en/manual/live-audio-effect-reference/",
        "supports": "Auto Filter vowel/formant and cutoff modulation, Saturator, Roar, EQ, Utility",
    },
    "roar": {
        "title": "Ableton: Roar",
        "url": "https://www.ableton.com/en/packs/roar/",
        "supports": "Multiple distortion stages, filtering, modulation, feedback and compression",
    },
    "brostep": {
        "title": "Ableton: Get the Drop",
        "url": "https://www.ableton.com/en/blog/get-drop-sound-skrillex-ableton-live/",
        "supports": "Producer tutorial showing distorted bass sound design in Live",
    },
    "tearout": {
        "title": "NIMDA: public Dubstep/Tearout tutorial index",
        "url": "https://www.patreon.com/nimda_uk/sitemap",
        "supports": "Topics include FM8, screech/noise oscillators and unconventional source material. Public titles only; gated lessons were not accessed.",
    },
    "machinegun": {
        "title": "Letsynthesize: public tutorial index",
        "url": "https://www.patreon.com/cw/letsynthesize/sitemap",
        "supports": "Topics include tearout FM, scream/screech and machine-gun bass. Public titles only; no claim to reproduce gated recipes.",
    },
}


def device(name, parameters, category="instruments", preset=None):
    return {"name": name, "category": category, "preset": preset, "parameters": parameters}


def operator(**overrides):
    values = {
        "Algorithm": 0,
        "Volume": 0.18,
        "A Coarse": 1,
        "A Fine": 0,
        "Osc-A On": 1,
        "Osc-B On": 1,
        "Osc-C On": 1,
        "Osc-D On": 1,
        "Osc-A Wave": 0,
        "Osc-A Level": 1,
        "Osc-B Level": 0,
        "Osc-C Level": 0,
        "Osc-D Level": 0,
        "Ae Attack": 0.03,
        "Ae Decay": 0.4,
        "Ae Sustain": 0.75,
        "Ae Release": 0.18,
        "Filter On": 0,
        "Spread": 0,
        "Osc-A Retrig": 1,
    }
    values.update(overrides)
    return device("Operator", values)


def fx(name, **values):
    return device(name, values, "audio_effects")


def hp():
    return fx(
        "EQ Eight",
        **{
            "1 Filter On A": 1,
            "1 Filter Type A": 1,
            "1 Frequency A": 0.29,
            "2 Gain A": 0,
            "3 Gain A": 0,
        },
    )


RECIPES = {
    "clean_sub": {
        "style": "dubstep",
        "role": "sub",
        "method": "Single sine carrier, phase retrigger, mono image, short click-reducing edges.",
        "chain": [
            operator(**{"Volume": 0.24, "Ae Attack": 0.08, "Ae Sustain": 1, "Ae Release": 0.2}),
            fx("Utility", **{"Stereo Width": 0}),
        ],
        "movement": {
            "shape": "duck",
            "target": "volume",
            "note": "Feed real kick hit positions; duck envelopes are rhythmic gain automation, not a compressor sidechain.",
        },
        "sources": ["operator", "effects"],
    },
    "dubstep_wobble": {
        "style": "dubstep",
        "role": "midbass",
        "method": "Harmonic FM into saturation and a moving low-pass filter.",
        "chain": [
            operator(**{"B Coarse": 2, "Osc-B Level": 0.48, "Be Decay": 0.4, "Be Sustain": 0.32}),
            fx("Saturator", **{"Drive": 0.57, "Output": 0.8, "Dry/Wet": 0.7}),
            fx("Auto Filter", **{"Type": 0, "Frequency": 0.55, "Resonance": 0.3, "LFO Amount": 0}),
            hp(),
        ],
        "movement": {
            "shape": "wobble",
            "device": "Auto Filter",
            "parameter": "Frequency",
            "low": 0.35,
            "high": 0.76,
            "cycle_beats": 1,
        },
        "sources": ["operator", "effects"],
    },
    "brostep_growl": {
        "style": "brostep",
        "role": "midbass",
        "method": "Serial FM with different modulator envelopes; vowel filtering turns timbre changes into a growl.",
        "chain": [
            operator(
                **{
                    "B Coarse": 2,
                    "C Coarse": 3,
                    "D Coarse": 1,
                    "Osc-B Level": 0.72,
                    "Osc-C Level": 0.52,
                    "Osc-D Level": 0.24,
                    "Be Decay": 0.36,
                    "Be Sustain": 0.2,
                    "Ce Attack": 0.08,
                    "Ce Decay": 0.3,
                    "Ce Sustain": 0.15,
                }
            ),
            fx("Saturator", **{"Drive": 0.65, "Output": 0.6, "Dry/Wet": 0.8}),
            fx("Auto Filter", **{"Type": 9, "Formant": 0.42, "Morph": 0.25, "Pitch": -7}),
            hp(),
        ],
        "movement": {
            "shape": "yoi",
            "device": "Auto Filter",
            "parameter": "Formant",
            "low": 0.12,
            "high": 0.85,
            "cycle_beats": 1,
        },
        "sources": ["operator", "effects", "brostep"],
    },
    "tearout_fm": {
        "style": "tearout",
        "role": "midbass",
        "method": "High-ratio serial FM, fast modulator decays, staged distortion and a clean low-end split.",
        "chain": [
            operator(
                **{
                    "Volume": 0.14,
                    "B Coarse": 2,
                    "C Coarse": 7,
                    "D Coarse": 11,
                    "Osc-B Level": 0.8,
                    "Osc-C Level": 0.6,
                    "Osc-D Level": 0.3,
                    "Ae Decay": 0.34,
                    "Ae Sustain": 0.65,
                    "Be Decay": 0.28,
                    "Be Sustain": 0.12,
                    "Ce Decay": 0.24,
                    "Ce Sustain": 0.1,
                    "De Decay": 0.2,
                    "De Sustain": 0.05,
                }
            ),
            fx(
                "Roar",
                **{
                    "Drive": 0.62,
                    "Shaper 1 Amt": 0.42,
                    "Shaper 2 Amt": 0.25,
                    "Fb Amt": 0.06,
                    "Fb Gate On": 1,
                    "Output": 0.54,
                    "Dry/Wet": 0.65,
                },
            ),
            hp(),
        ],
        "movement": {
            "shape": "growl",
            "device": "Operator",
            "parameter": "Osc-B Level",
            "low": 0.45,
            "high": 0.83,
            "cycle_beats": 1,
        },
        "sources": ["operator", "roar", "tearout", "machinegun"],
    },
    "metallic_screech": {
        "style": "tearout",
        "role": "response",
        "method": "Inharmonic FM using Fine tuning, resonant band-pass motion, distortion and low-cut cleanup.",
        "chain": [
            operator(
                **{
                    "Volume": 0.12,
                    "B Coarse": 1,
                    "B Fine": 500,
                    "C Coarse": 3,
                    "C Fine": 166,
                    "D Coarse": 11,
                    "Osc-B Level": 0.84,
                    "Osc-C Level": 0.64,
                    "Osc-D Level": 0.38,
                    "Filter On": 1,
                    "Filter Type": 2,
                    "Filter Freq": 0.62,
                    "Filter Res": 0.42,
                    "Ae Decay": 0.3,
                    "Ae Sustain": 0.5,
                }
            ),
            fx("Roar", **{"Drive": 0.6, "Shaper 1 Amt": 0.45, "Output": 0.52, "Dry/Wet": 0.6}),
            hp(),
        ],
        "movement": {
            "shape": "sweep",
            "device": "Operator",
            "parameter": "Filter Freq",
            "low": 0.45,
            "high": 0.8,
            "cycle_beats": 2,
        },
        "sources": ["operator", "effects", "tearout"],
    },
    "wavetable_reese": {
        "style": "dubstep",
        "role": "midbass",
        "method": "Two detuned wavetable oscillators form beating movement; saturation and low cutting separate the sub.",
        "chain": [
            device(
                "Wavetable",
                {
                    "Osc 1 On": 1,
                    "Osc 1 Pos": 0.66,
                    "Osc 1 Detune": 0.495,
                    "Osc 1 Gain": 0.65,
                    "Osc 2 On": 1,
                    "Osc 2 Pos": 0.66,
                    "Osc 2 Detune": 0.505,
                    "Osc 2 Gain": 0.65,
                    "Sub On": 0,
                    "Filter 1 Freq": 0.7,
                    "Amp Attack": 0.06,
                    "Amp Release": 0.24,
                    "Volume": 0.25,
                },
            ),
            fx("Saturator", **{"Drive": 0.59, "Output": 0.74, "Dry/Wet": 0.7}),
            hp(),
        ],
        "movement": {
            "shape": "wobble",
            "device": "Wavetable",
            "parameter": "Osc 1 Pos",
            "low": 0.45,
            "high": 0.75,
            "cycle_beats": 4,
        },
        "sources": ["operator", "effects"],
    },
    "808_sub": {
        "style": "dubstep",
        "role": "sub",
        "method": "Sine bass with a short pitch drop and decaying amplitude; 808 Shaper adds controlled harmonics.",
        "chain": [
            operator(
                **{
                    "Volume": 0.2,
                    "Ae Attack": 0.04,
                    "Ae Decay": 0.62,
                    "Ae Sustain": 0.15,
                    "Ae Release": 0.22,
                    "Pe On": 1,
                    "Pe Init": 12,
                    "Pe Peak": 12,
                    "Pe Decay": 0.2,
                    "Pe Sustain": 0,
                }
            ),
            device(
                "Saturator",
                {"Drive": 0.54, "Output": 0.8, "Dry/Wet": 0.65},
                "audio_effects",
                "808 Shaper.adv",
            ),
            fx("Utility", **{"Stereo Width": 0}),
        ],
        "movement": {
            "shape": "pluck",
            "device": "808 Shaper",
            "parameter": "Drive",
            "low": 0.5,
            "high": 0.58,
            "cycle_beats": 1,
        },
        "sources": ["operator", "effects"],
    },
    "yoi_bass": {
        "style": "brostep",
        "role": "response",
        "method": "FM harmonics through a scanning vowel filter; brief repeated envelopes make talking accents.",
        "chain": [
            operator(
                **{
                    "B Coarse": 2,
                    "Osc-B Level": 0.58,
                    "C Coarse": 5,
                    "Osc-C Level": 0.3,
                    "Ae Decay": 0.35,
                    "Ae Sustain": 0.5,
                }
            ),
            fx("Saturator", **{"Drive": 0.6, "Output": 0.65, "Dry/Wet": 0.75}),
            fx("Auto Filter", **{"Type": 9, "Formant": 0.3, "Morph": 0.25, "Pitch": -5}),
            hp(),
        ],
        "movement": {
            "shape": "yoi",
            "device": "Auto Filter",
            "parameter": "Formant",
            "low": 0.1,
            "high": 0.9,
            "cycle_beats": 0.5,
        },
        "sources": ["operator", "effects", "brostep"],
    },
}


# Artist research supplies context, not commercial presets or exact track settings.
from .artist_methods import DATA as ARTIST_DATA

SOURCES.update(deepcopy(ARTIST_DATA["sources"]))
for patch_id, patch in ARTIST_DATA["patches"].items():
    variant = deepcopy(RECIPES[patch["base"]])
    for device_name, overrides in patch["overrides"].items():
        matches = [d for d in variant["chain"] if d["name"] == device_name]
        if len(matches) != 1:
            raise ValueError("Ambiguous original patch device: " + device_name)
        matches[0]["parameters"].update(overrides)
    variant.update(
        method=patch["method"],
        movement=deepcopy(patch["movement"]),
        artists=[ARTIST_DATA["artists"][patch["artist"]]["name"]],
        provenance="Original artist-informed adaptation; all numeric settings are our own audition starting points, not artist presets or measured track settings.",
        artist_evidence_scope=ARTIST_DATA["artists"][patch["artist"]]["scope"],
    )
    variant["sources"] = list(dict.fromkeys(variant["sources"][:2] + patch["sources"]))
    for field in ["role", "style"]:
        if field in patch:
            variant[field] = patch[field]
    RECIPES[patch_id] = variant


SOURCES["aulart_square_fm"] = {
    "title": "Steve Angstrom / Aulart: stock Operator square-wave FM",
    "url": "https://www.aulart.com/blog/create-unique-rhythmic-sounds-in-ableton/",
    "supports": "Dual-pair B-to-A routing, Square D waveforms, FM-level modulation, high sustain and animated filtering. Numeric settings below are original adaptations.",
}
RECIPES["riddim_square_fm"] = {
    "style": "dubstep",
    "role": "midbass",
    "method": "Square D carrier/modulator at 1:1 in a B-to-A pair, high sustained modulation and a driven low-pass; separate sub required. Original riddim-oriented adaptation, not a track recreation.",
    "chain": [
        operator(
            **{
                "Algorithm": 6,
                "Osc-A Wave": 18,
                "Osc-B Wave": 18,
                "B Coarse": 1,
                "Osc-B Level": 0.75,
                "Osc-C Level": 0,
                "Osc-D Level": 0,
                "Volume": 0.53,
                "Ae Attack": 0.12,
                "Ae Decay": 0.4,
                "Ae Sustain": 0.95,
                "Ae Release": 0.28,
                "Be Attack": 0.03,
                "Be Decay": 0.4,
                "Be Sustain": 1,
                "Be Release": 0.28,
                "Filter On": 1,
                "Filter Type": 0,
                "Filter Circuit - LP/HP": 1,
                "Filter Drive": 0.25,
                "Filter Freq": 0.53,
                "Filter Res": 0.28,
            }
        ),
        fx("Roar", **{"Drive": 2 / 3, "Output": 0.7, "Dry/Wet": 0.6}),
        hp(),
    ],
    "movement": {
        "shape": "pluck",
        "device": "Operator",
        "parameter": "Filter Freq",
        "low": 0.3828125,
        "high": 0.6875,
        "cycle_beats": 0.5,
        "note": "Default builder motion is periodic; manually align FM-level/cutoff gestures to MIDI attacks for a retriggered result.",
    },
    "sources": ["operator", "effects", "aulart_square_fm"],
    "provenance": "Documented square-wave FM topology with original patch values. Algorithm 6 is displayed Alg. 7; silent C/D pair. Parameter readback is not audio audition.",
}


def get_recipe(name):
    if name not in RECIPES:
        raise ValueError("Unknown recipe. Choose: " + ", ".join(RECIPES))
    result = deepcopy(RECIPES[name])
    result["id"] = name
    result.setdefault(
        "provenance",
        "Original starting patch informed by sources, not an artist preset or guaranteed sonic match",
    )
    result["sources"] = [dict(id=key, **SOURCES[key]) for key in result["sources"]]
    result["parameter_units"] = (
        "Live API native values; 0..1 controls may be nonlinear, not Hz/dB/ms"
    )
    return result
