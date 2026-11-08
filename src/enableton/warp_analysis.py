"""Bounded, dependency-free warp diagnostics. Estimates are explicitly heuristic."""

import bisect
import hashlib
import json
import math
from pathlib import Path
import statistics
import wave

from .numbers import finite

MAX_SECONDS = 120
MAX_FILE_BYTES = 512 * 1024 * 1024
RATE = 200  # onset-envelope frames per second


def timing_fingerprint(timing):
    keys = (
        "track_name",
        "clip_name",
        "file_path",
        "warping",
        "warp_mode",
        "looping",
        "loop_start",
        "loop_end",
        "start_marker",
        "end_marker",
        "pitch_coarse",
        "pitch_fine",
        "arrangement_start",
        "arrangement_end",
        "warp_markers",
        "sample_length",
        "sample_rate",
        "clip_identity",
    )
    return hashlib.sha256(
        json.dumps(
            {k: timing[k] for k in keys if k in timing}, sort_keys=True, allow_nan=False
        ).encode()
    ).hexdigest()


def validate_markers(markers):
    if not isinstance(markers, list) or not 2 <= len(markers) <= 20000:
        raise ValueError("Need 2..20000 marker pairs including Live's hidden terminal marker")
    rows = []
    for marker in markers:
        b = finite(marker["beat_time"], "beat_time")
        s = finite(marker["sample_time"], "sample_time")
        if rows and (b <= rows[-1][0] or s <= rows[-1][1]):
            raise ValueError("Warp marker beat and source coordinates must strictly increase")
        rows.append((b, s))
    return rows


def source_to_beat(seconds, markers):
    rows = validate_markers(markers)
    i = max(0, min(len(rows) - 2, bisect.bisect_right([s for b, s in rows], seconds) - 1))
    b0, s0 = rows[i]
    b1, s1 = rows[i + 1]
    return b0 + (seconds - s0) * (b1 - b0) / (s1 - s0)


def beat_to_source(beat, markers):
    rows = validate_markers(markers)
    i = max(0, min(len(rows) - 2, bisect.bisect_right([b for b, s in rows], beat) - 1))
    b0, s0 = rows[i]
    b1, s1 = rows[i + 1]
    return s0 + (beat - b0) * (s1 - s0) / (b1 - b0)


def pcm_window(path, start_seconds=0, max_seconds=60):
    """Sample source energy without phase-cancelling stereo; no normalization."""
    start = finite(start_seconds, "start_seconds")
    limit = finite(max_seconds, "max_seconds")
    if start < 0 or not 0 < limit <= MAX_SECONDS:
        raise ValueError("Invalid window; maximum 120 seconds")
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Need an existing absolute local audio file <=512 MiB")
    if path.suffix.lower() not in (".wav", ".wave"):
        raise ValueError(
            "This analyzer currently supports PCM WAV only; other formats are reported unsupported, never guessed"
        )
    with wave.open(str(path), "rb") as audio:
        sr = audio.getframerate()
        channels = audio.getnchannels()
        width = audio.getsampwidth()
        total = audio.getnframes()
        if not 8000 <= sr <= 192000 or not 1 <= channels <= 8 or width not in (1, 2, 3, 4):
            raise ValueError("Supported PCM: 8/16/24/32-bit, 8–192 kHz, 1–8 channels")
        first = round(start * sr)
        if first >= total:
            raise ValueError("Window begins after end of source")
        count = min(round(limit * sr), total - first, 16_000_000 // channels)
        audio.setpos(first)
        hop = max(1, round(sr / RATE))
        rate = sr / hop
        energy = []
        first_values = []
        last_values = []
        peak = 0.0
        remaining = count
        scale = 128 if width == 1 else 2 ** (width * 8 - 1)
        while remaining > 0:
            n = min(hop, remaining)
            raw = audio.readframes(n)
            frames = len(raw) // (width * channels)
            if not frames:
                break
            # <=64 evenly spaced frames per 5 ms block limits CPU on long files.
            positions = range(0, frames, max(1, frames // 64))
            squares = []
            for frame in positions:
                for ch in range(channels):
                    offset = (frame * channels + ch) * width
                    value = (
                        (raw[offset] - 128) / scale
                        if width == 1
                        else int.from_bytes(raw[offset : offset + width], "little", signed=True)
                        / scale
                    )
                    squares.append(value * value)
                    peak = max(peak, abs(value))
            energy.append(math.sqrt(sum(squares) / max(1, len(squares))))
            for frame in (0, frames - 1):
                vals = []
                for ch in range(channels):
                    offset = (frame * channels + ch) * width
                    vals.append(
                        (raw[offset] - 128) / scale
                        if width == 1
                        else int.from_bytes(raw[offset : offset + width], "little", signed=True)
                        / scale
                    )
                if not first_values:
                    first_values = vals
                last_values = vals
            remaining -= frames
    analyzed = (count - remaining) / sr
    return {
        "energy": energy,
        "envelope_rate": rate,
        "sample_rate": sr,
        "channels": channels,
        "source_duration_seconds": total / sr,
        "start_seconds": first / sr,
        "analyzed_seconds": analyzed,
        "partial": first > 0 or first + count < total,
        "reaches_source_end": first + count >= total,
        "boundary_jump_relative_to_sampled_peak": max(
            (abs(a - b) for a, b in zip(first_values, last_values)), default=0
        )
        / max(peak, 1e-12),
        "peak_sample_estimate": peak,
        "measurement_note": "Block energy uses decimated PCM probes, not full-sample peak, true peak or LUFS.",
    }


def extract_onsets(energy, rate):
    if not energy or max(energy) < 1e-7:
        return []
    flux = [0.0] + [max(0.0, energy[i] - energy[i - 1]) for i in range(1, len(energy))]
    floor = max(flux) * 0.07
    peaks = []
    # Include an attack at the source's first block instead of losing a beat at zero.
    if energy[0] > max(energy) * 0.1:
        peaks.append({"time": 0.0, "strength": energy[0]})
    for i in range(1, len(flux) - 1):
        neighborhood = flux[max(0, i - 15) : min(len(flux), i + 16)]
        threshold = max(floor, statistics.median(neighborhood) * 2.5)
        if flux[i] > threshold and flux[i] >= flux[i - 1] and flux[i] > flux[i + 1]:
            row = {"time": i / rate, "strength": flux[i]}
            if peaks and row["time"] - peaks[-1]["time"] < 0.065:
                if row["strength"] > peaks[-1]["strength"]:
                    peaks[-1] = row
            else:
                peaks.append(row)
    maximum = max((p["strength"] for p in peaks), default=1)
    return [{"time": p["time"], "strength": p["strength"] / maximum} for p in peaks[:5000]]


def tempo_candidates(onsets, hint=None):
    if hint is not None:
        hint = finite(hint, "tempo_hint")
        if not 20 <= hint <= 999:
            raise ValueError("tempo_hint outside 20..999")
    if len(onsets) < 6:
        return {
            "bpm": None,
            "confidence": "insufficient_events",
            "candidates": [],
            "half_double_ambiguous": True,
        }
    times = [p["time"] for p in onsets]
    strength = [p["strength"] for p in onsets]
    # Event-train autocorrelation. Keep half/double-time alternatives visible.
    candidates = []
    for step in range(120, 401):
        bpm = step / 2
        period = 60 / bpm
        score = 0.0
        weight = 0.0
        for i, t in enumerate(times):
            expected = t + period
            j = bisect.bisect_left(times, expected)
            options = [k for k in (j - 1, j) if i < k < len(times)]
            if not options:
                continue
            k = min(options, key=lambda k: abs(times[k] - expected))
            error = abs(times[k] - expected)
            w = math.sqrt(strength[i] * strength[k])
            weight += w
            score += w * max(0, 1 - error / 0.035)
        candidates.append({"bpm": bpm, "score": score / max(weight, 1e-9)})
    candidates.sort(key=lambda r: r["score"], reverse=True)
    separated = []
    for row in candidates:
        if all(abs(row["bpm"] - r["bpm"]) > 3 for r in separated):
            separated.append(row)
        if len(separated) == 6:
            break
    best = separated[0]
    if hint:
        near = [
            r
            for r in separated
            if abs(r["bpm"] - hint) / hint < 0.04 and r["score"] >= best["score"] - 0.1
        ]
        if near:
            best = min(near, key=lambda r: abs(r["bpm"] - hint))
    confidence = (
        "high"
        if best["score"] > 0.8 and len(onsets) >= 16
        else "medium"
        if best["score"] > 0.5
        else "low"
    )
    ambiguous = confidence == "low" or any(
        abs(r["bpm"] / best["bpm"] - ratio) < 0.035 and r["score"] >= best["score"] - 0.12
        for r in separated
        for ratio in (0.5, 2)
    )
    hint_relation = None
    if hint:
        for ratio, label in (
            (0.5, "hint_is_half_time"),
            (1, "hint_matches"),
            (2, "hint_is_double_time"),
        ):
            if abs(hint - best["bpm"] * ratio) / hint < 0.04:
                hint_relation = label
                if ratio != 1:
                    ambiguous = True
    return {
        "bpm": best["bpm"],
        "confidence": confidence,
        "confidence_is": "heuristic regularity label, not a calibrated probability",
        "candidates": separated,
        "half_double_ambiguous": ambiguous,
        "tempo_hint_relation": hint_relation,
        "equivalent_tempos": [best["bpm"] / 2, best["bpm"], best["bpm"] * 2],
    }


def analyze_file(path, start_seconds=0, max_seconds=60, tempo_hint=None):
    window = pcm_window(path, start_seconds, max_seconds)
    onsets = extract_onsets(window.pop("energy"), window["envelope_rate"])
    tempo = tempo_candidates(onsets, tempo_hint)
    bpm = tempo["bpm"]
    downbeats = []
    if bpm:
        period = 60 / bpm
        for anchor in sorted(onsets, key=lambda p: p["strength"], reverse=True)[:20]:
            score = sum(
                p["strength"]
                * max(
                    0,
                    1
                    - abs(
                        (p["time"] - anchor["time"]) / (period * 4)
                        - round((p["time"] - anchor["time"]) / (period * 4))
                    )
                    * 8,
                )
                for p in onsets
            )
            candidate = {"source_seconds": start_seconds + anchor["time"], "score": score}
            if all(
                abs(candidate["source_seconds"] - r["source_seconds"]) > period * 0.5
                for r in downbeats
            ):
                downbeats.append(candidate)
        downbeats.sort(key=lambda r: r["score"], reverse=True)
    for p in onsets:
        p["time"] += window["start_seconds"]
    return {
        "path": str(Path(path)),
        "audio": window,
        "tempo": tempo,
        "onsets": onsets,
        "downbeat_candidates": downbeats[:4],
        "downbeat_limit": "Strong periodic attacks only; not identification of musical beat one. Confirm by listening.",
        "warp_mode_guidance": {
            "drums": "Beats; check transient preservation by ear",
            "monophonic_pitched": "Tones; inspect sustained notes",
            "noise_or_texture": "Texture",
            "mixed_music": "Complex or Complex Pro; compare artifacts and CPU",
            "repitch": "Re-Pitch changes pitch with tempo; use deliberately",
        },
        "limitations": [
            "PCM WAV only; unsupported formats fail explicitly",
            "Tempo/downbeat detection is heuristic and may fail on syncopated, tonal or sparse material",
            "No automatic quantization; intentional swing/triplets are not timing errors",
            "Analysis may cover only part of the source",
        ],
    }


def audit_timing(
    timing,
    audio=None,
    grid_beats=0.25,
    groove="straight",
    tolerance_ms=25,
    project_bpm=140,
    expected_bars=None,
):
    grid = finite(grid_beats, "grid_beats")
    bpm = finite(project_bpm, "project_bpm")
    tol = finite(tolerance_ms, "tolerance_ms")
    if not 0.03125 <= grid <= 4 or not 20 <= bpm <= 999 or not 1 <= tol <= 250:
        raise ValueError("Invalid grid, tempo or tolerance")
    if groove not in ("straight", "triplet", "swing"):
        raise ValueError("groove must be straight, triplet or swing")
    result = {
        "fingerprint": timing_fingerprint(timing),
        "issues": [],
        "review": [],
        "segments": [],
        "warping": timing.get("warping"),
        "musical_alignment_verified": False,
        "limits": "Structural checks and heuristic transient alignment; no guarantee of correct musical downbeats.",
    }
    if not timing.get("warping"):
        result["review"].append(
            "Unwarped audio: marker map is inactive; evaluate absolute playback timing instead"
        )
        return result
    try:
        rows = validate_markers(timing["warp_markers"])
    except (KeyError, ValueError) as error:
        result["issues"].append(str(error))
        return result
    previous = None
    for i, ((b0, s0), (b1, s1)) in enumerate(zip(rows, rows[1:])):
        tempo = 60 * (b1 - b0) / (s1 - s0)
        segment = {
            "start_beat": b0,
            "end_beat": b1,
            "source_bpm": tempo,
            "hidden_terminal_segment": i == len(rows) - 2,
        }
        if not 5 <= tempo <= 999:
            result["issues"].append("Segment BPM outside Live range at beat " + str(b0))
        if previous and abs(math.log2(tempo / previous)) > 0.12 and i != len(rows) - 2:
            result["review"].append("Abrupt local stretch change at beat " + str(b0))
        result["segments"].append(segment)
        previous = tempo
    if timing.get("looping"):
        length = timing["loop_end"] - timing["loop_start"]
        if length <= 0:
            result["issues"].append("Loop has nonpositive length")
        if expected_bars is not None:
            bars = finite(expected_bars, "expected_bars")
            if bars <= 0:
                raise ValueError("expected_bars must be positive")
            beats_per_bar = (
                timing.get("signature_numerator", 4) * 4 / timing.get("signature_denominator", 4)
            )
            if abs(length - bars * beats_per_bar) > 0.01:
                result["review"].append("Loop length differs from requested bar count")
    if audio:
        estimate = audio.get("tempo", {})
        if estimate.get("bpm") and estimate.get("confidence") == "high":
            local = statistics.median(r["source_bpm"] for r in result["segments"])
            error = min(
                abs(local - estimate["bpm"] * factor) / max(local, 1e-9) for factor in (0.5, 1, 2)
            )
            result["tempo_map_comparison"] = {
                "median_marker_source_bpm": local,
                "estimated_source_bpm": estimate["bpm"],
                "relative_error_after_half_double": error,
            }
            if error > 0.04:
                result["review"].append(
                    "Source tempo estimate differs from median marker mapping; inspect before changing"
                )
        aligned = []
        for onset in audio.get("onsets", []):
            beat = source_to_beat(onset["time"], timing["warp_markers"])
            if not timing["start_marker"] <= beat <= timing["end_marker"]:
                continue
            step = grid * 2 / 3 if groove == "triplet" else grid
            if groove == "swing":
                base = math.floor(beat / (grid * 2)) * grid * 2
                choices = [base, base + grid * 4 / 3, base + grid * 2]
                nearest = min(choices, key=lambda t: abs(t - beat))
            else:
                nearest = round(beat / step) * step
            aligned.append(
                {
                    "source_seconds": onset["time"],
                    "clip_beat": beat,
                    "nearest_grid_beat": nearest,
                    "offset_ms": (beat - nearest) * 60 / bpm * 1000,
                    "strength": onset["strength"],
                }
            )
        strong = [r for r in aligned if r["strength"] >= 0.3]
        result["transient_alignment"] = {
            "grid_beats": grid,
            "groove": groove,
            "tolerance_ms": tol,
            "strong_events": len(strong),
            "outside_tolerance": sum(abs(r["offset_ms"]) > tol for r in strong),
            "events": aligned,
            "interpretation": "Off-grid events are review candidates, not automatically wrong notes or warp markers",
        }
        if timing.get("looping"):
            a = beat_to_source(timing["loop_start"], timing["warp_markers"])
            b = beat_to_source(timing["loop_end"], timing["warp_markers"])
            window = audio.get("audio", {})
            if (
                abs(window.get("start_seconds", -1) - a) < 0.01
                and abs(window.get("analyzed_seconds", 0) - (b - a)) < 0.01
            ):
                jump = window.get("boundary_jump_relative_to_sampled_peak", 0)
                result["loop_seam"] = {
                    "boundary_jump_estimate": jump,
                    "click_risk_candidate": jump > 0.2,
                    "audition_required": True,
                }
            else:
                result["review"].append(
                    "Loop seam not checked: analyzed window does not exactly cover loop source interval"
                )
    return result


def compare_reference(candidate_beats, reference_beats, max_offset_beats=1):
    limit = finite(max_offset_beats, "max_offset_beats")
    if not 0 <= limit <= 16:
        raise ValueError("max_offset_beats outside 0..16")
    a = [finite(v, "candidate beat") for v in candidate_beats]
    b = sorted(finite(v, "reference beat") for v in reference_beats)
    if not a or not b or max(len(a), len(b)) > 5000:
        raise ValueError("Need 1..5000 event positions per sequence")
    results = []
    for i in range(-round(limit * 32), round(limit * 32) + 1):
        offset = i / 32
        errors = []
        for beat in a:
            at = bisect.bisect_left(b, beat + offset)
            near = b[max(0, at - 1) : min(len(b), at + 1)]
            errors.append(min(abs(v - beat - offset) for v in near))
        results.append((statistics.median(errors), offset))
    error, offset = min(results, key=lambda row: (row[0], abs(row[1])))
    return {
        "suggested_offset_beats": offset,
        "median_nearest_event_error_beats": error,
        "limits": "Nearest-event alignment only; does not prove matching instrument roles, phrase structure or downbeats.",
    }


def plan_moves(timing, moves, max_shift_beats=0.125):
    cap = finite(max_shift_beats, "max_shift_beats")
    if not 0 < cap <= 4:
        raise ValueError("max_shift_beats must be in (0,4]")
    if not timing.get("warping"):
        raise ValueError("Repair requires a warped audio clip")
    rows = validate_markers(timing["warp_markers"])
    existing = {b: s for b, s in rows}
    if not isinstance(moves, list) or not 1 <= len(moves) <= 64:
        raise ValueError("Provide 1..64 explicit marker moves")
    mapping = {}
    normalized = []
    for move in moves:
        old = finite(move["beat_time"], "beat_time")
        new = finite(move["new_beat_time"], "new_beat_time")
        if old not in existing or old in mapping:
            raise ValueError("Unknown or duplicate marker target")
        if old in (rows[0][0], rows[-1][0]):
            raise ValueError("First and hidden terminal anchors are preserved")
        if abs(new - old) > cap:
            raise ValueError("Move exceeds explicit maximum shift")
        mapping[old] = new
        normalized.append({"beat_time": old, "new_beat_time": new})
    after = [{"beat_time": mapping.get(b, b), "sample_time": s} for b, s in rows]
    validate_markers(after)
    for a, b in zip(after, after[1:]):
        tempo = 60 * (b["beat_time"] - a["beat_time"]) / (b["sample_time"] - a["sample_time"])
        if not 5 <= tempo <= 999:
            raise ValueError("Proposed segment outside Live 5..999 BPM range")
    ordered = sorted(
        [m for m in normalized if m["new_beat_time"] < m["beat_time"]], key=lambda m: m["beat_time"]
    )
    ordered += sorted(
        [m for m in normalized if m["new_beat_time"] >= m["beat_time"]],
        key=lambda m: m["beat_time"],
        reverse=True,
    )
    return {
        "before_fingerprint": timing_fingerprint(timing),
        "moves": ordered,
        "after_markers": after,
        "max_shift_beats": cap,
        "original_preserved": True,
        "limits": "Explicit existing-marker moves only; no inferred automatic beat-one correction.",
    }
