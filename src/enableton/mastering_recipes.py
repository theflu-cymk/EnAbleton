"""Source-grounded mastering plans; displayed units, never raw Live API settings."""

from copy import deepcopy
import math

SOURCES = {
    "live_fx": {
        "url": "https://www.ableton.com/en/manual/live-audio-effect-reference/",
        "supports": "Native device capabilities: M/S EQ, detector filtering, multiband dynamics, oversampling and true-peak limiting.",
    },
    "live_audio": {
        "url": "https://www.ableton.com/en/manual/audio-fact-sheet/",
        "supports": "Render precision and final bit-depth reduction/dither.",
    },
    "izotope": {
        "url": "https://www.izotope.com/community/blog/an-introduction-to-limiters-and-how-to-use-them",
        "supports": "Final peak control and checking distortion with level-matched comparisons.",
    },
    "spotify": {
        "url": "https://support.spotify.com/us/artists/article/loudness-normalization/",
        "supports": "Playback normalization and platform-specific true-peak delivery guidance; checked 2026-10-28.",
    },
}


def technique(device, trigger, settings, procedure, back_off, sources):
    return dict(
        device=device,
        use_when=trigger,
        starting_settings=settings,
        procedure=procedure,
        back_off_when=back_off,
        sources=sources,
    )


RECIPES = {
    "ms_tonal_cleanup": technique(
        "EQ Eight in M/S mode; Utility for mono audition",
        "Stereo ambience or sides consume headroom or mask the centered kick/sub.",
        {
            "side_low_cut_hz": [60, 120],
            "broad_eq_db": [-1, 1],
            "initial_state": "Bypass all filters until a specific problem is heard.",
        },
        [
            "Compare mid, side and full stereo at matched loudness.",
            "If needed, remove only unnecessary side lows; preserve the centered fundamental.",
            "Check mono after every change; use broad small corrections before narrow boosts.",
        ],
        "Bass weight or width collapses, or the mono balance gets worse.",
        ["live_fx"],
    ),
    "selective_band_control": technique(
        "Multiband Dynamics; a dedicated dynamic EQ for true dynamic bell/shelf cuts",
        "Only particular bass notes or harsh midrange bursts overload an otherwise balanced mix.",
        {
            "low_band_crossover_hz": [70, 120],
            "high_band_crossover_hz": [2500, 5000],
            "downward_ratio": [1.2, 1.6],
            "gain_reduction_db": [0.5, 2],
            "attack_ms": [10, 40],
            "release_ms": [80, 200],
        },
        [
            "Start with unity dynamics and no upward compression; move crossovers around the actual problem.",
            "Compress only the offending band and match output level.",
            "For isolated narrow resonances, use a dedicated dynamic EQ or repair the source; static EQ Eight is not dynamic EQ.",
        ],
        "Crossover coloration, pumping, dulled snares, or newly raised noise.",
        ["live_fx"],
    ),
    "sub_aware_glue": technique(
        "Glue Compressor with internal detector EQ",
        "The mix needs slight cohesion but full-band compression pumps on long sub notes.",
        {
            "ratio": 2,
            "attack_ms": 30,
            "release": "Auto or audition 0.1–0.3 seconds",
            "detector_highpass_hz": [60, 120],
            "gain_reduction_db": [0.5, 1.5],
            "makeup": "Manual and loudness matched",
        },
        [
            "Filter the detector rather than cutting the audible bass.",
            "Set threshold from observed gain reduction on the loudest drop.",
            "Check the kick still has impact and the bass recovers between hits; bypass if cohesion does not improve.",
        ],
        "Kick/sub surges escape control, groove flattens, or the drop breathes unnaturally.",
        ["live_fx"],
    ),
    "staged_peak_control": technique(
        "Saturator or Glue soft clip, followed by a separate Limiter in True Peak mode",
        "Sparse drum spikes force excessive final limiting; keep this optional on already distorted tearout.",
        {
            "initial_clip_drive_db": 0,
            "clip_peak_shaving_trial_db": [0.5, 1.5],
            "final_limiter_gain_reduction_trial_db": [0.5, 2],
            "limiter_lookahead_ms": [3, 6],
            "ceiling": "Set by delivery profile, then verify the rendered file.",
        },
        [
            "Start with the clipper bypassed; inspect isolated spikes and audition very small peak shaving.",
            "Enable available high-quality/oversampling modes after inspecting the actual device; compare at equal loudness.",
            "Follow with a separate true-peak limiter; soft clip and true peak are alternative modes on one Live Limiter, not simultaneous modes.",
            "Set final drive by audible tolerance and external meters, not by an assumed LUFS target.",
        ],
        "Crackling sub, papery transients, harsher cymbals, or no benefit at matched loudness.",
        ["live_fx", "izotope"],
    ),
    "stereo_translation": technique(
        "Utility, EQ Eight, external correlation/spectrum meter",
        "Wide bass texture or aggressive M/S processing changes the drop across playback systems.",
        {
            "width_percent": 100,
            "optional_bass_mono_hz": [70, 120],
            "default": "No automatic widening or forced bass mono.",
        },
        [
            "Audition stereo, mono, left and right; bypass each width change at matched loudness.",
            "Use bass mono only when it solves an observed problem; it can alter cancellation and level.",
            "Prefer fixing individual wide bass layers over forcing the whole master.",
        ],
        "Center energy weakens, mono loses instruments, or width shifts when limiting.",
        ["live_fx"],
    ),
    "section_consistency": technique(
        "Pre-limiter Utility gain automation plus external loudness meter",
        "Half-time sections, fakeouts or transitions hit the limiter differently from the main drop.",
        {
            "automation_trial_db": [-0.5, 0.5],
            "measurement": "Full-track integrated LUFS plus section short-term loudness and peak/GR observations",
        },
        [
            "Measure the full song and compare corresponding musical sections with references at equal loudness.",
            "Make small pre-limiter gain changes only if needed; preserve intentional breakdown/drop contrast.",
            "Recheck limiter gain reduction after automation; do not flatten every section to equal LUFS.",
        ],
        "Builds lose anticipation or half-time loses its intended weight.",
        ["izotope"],
    ),
    "delivery_qc": technique(
        "Final true-peak limiter, external BS.1770 loudness/true-peak meter, Live export",
        "Preparing release or comparison renders.",
        {
            "intermediate": "32-bit float, no dither",
            "final_pcm": "24-bit or requested destination format; dither once on final bit-depth reduction",
            "normalize_export": False,
        },
        [
            "Measure the final render, not only the input or Live sample-peak meter.",
            "Check starts, tails, clicks, mono balance and loudest drops; audition a representative lossy encode when applicable.",
            "Resample before the final limiting stage where feasible, then verify delivered-rate peaks.",
            "Keep a less-limited alternative and level-match it against the loud version.",
        ],
        "Rendered/encoded overs, damaged transients or final format mismatch.",
        ["live_audio", "spotify"],
    ),
}

PROFILES = {
    "transparent": {
        "goal": "Preserve impact and contrast; loudness determined by listening, not a fixed target.",
        "chain": ["ms_tonal_cleanup", "sub_aware_glue", "stereo_translation", "delivery_qc"],
        "ceiling_dbtp": -1.0,
    },
    "tearout_dense": {
        "goal": "Optional staged peak control for dense bass music; no universal competitive LUFS target.",
        "chain": [
            "ms_tonal_cleanup",
            "selective_band_control",
            "sub_aware_glue",
            "staged_peak_control",
            "stereo_translation",
            "section_consistency",
            "delivery_qc",
        ],
        "ceiling_dbtp": -1.0,
    },
    "spotify_delivery": {
        "goal": "Platform-specific delivery review; -14 LUFS is a playback reference, not a universal submission threshold.",
        "chain": ["ms_tonal_cleanup", "staged_peak_control", "delivery_qc"],
        "ceiling_dbtp": -1.0,
    },
}


def catalog(recipe=None):
    if recipe is not None and recipe not in RECIPES:
        raise ValueError("Unknown mastering recipe")
    return deepcopy(
        {
            "recipes": {recipe: RECIPES[recipe]} if recipe else RECIPES,
            "profiles": PROFILES,
            "sources": SOURCES,
            "units": "Displayed Hz, dB, ms, ratio and percent; not raw Live API values. Numeric ranges are original audition starting points, not source-prescribed settings.",
            "execution": "Read-only recipes. No devices, routing, automation, gain or export settings are changed. No audio is measured or auditioned.",
        }
    )


def plan(profile="tearout_dense", measured_lufs=None, measured_true_peak_dbtp=None):
    if profile not in PROFILES:
        raise ValueError("Unknown mastering profile")
    for name, value in [
        ("measured_lufs", measured_lufs),
        ("measured_true_peak_dbtp", measured_true_peak_dbtp),
    ]:
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(name + " must be a finite number or omitted")
    result = deepcopy(PROFILES[profile])
    result["profile"] = profile
    if profile == "spotify_delivery" and (measured_lufs is None or measured_lufs > -14):
        result["ceiling_dbtp"] = -2.0
    result["ceiling_note"] = (
        "Original -1 dBTP audition ceiling for general profiles. Spotify profile uses -2 dBTP conservatively when loudness is unknown or above -14 LUFS; verify current destination requirements."
    )
    result["steps"] = [dict(id=k, **deepcopy(RECIPES[k])) for k in result.pop("chain")]
    result["measurements"] = {
        "origin": "Caller supplied, not measured or verified by MCP",
        "integrated_lufs": measured_lufs,
        "true_peak_dbtp": measured_true_peak_dbtp,
    }
    result["peak_review"] = (
        "Measure the final render with a true-peak meter."
        if measured_true_peak_dbtp is None
        else (
            "Reported true peak exceeds the suggested ceiling; reduce final output and remeasure."
            if measured_true_peak_dbtp > result["ceiling_dbtp"]
            else "Reported peak is within the suggested ceiling; this does not certify the render or encoded version."
        )
    )
    result["execution"] = catalog()["execution"]
    result["sources"] = deepcopy(SOURCES)
    result["required_checks"] = [
        "Level-matched reference and bypass comparisons",
        "Full-song integrated LUFS, section loudness, final true peak",
        "Mono and small-speaker audition",
        "Manual mapping from displayed controls to inspected native API parameters before any future application",
    ]
    return result
