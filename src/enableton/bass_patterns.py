"""Deterministic musical generators; no Live or network dependencies."""

import math
import random

SHAPES = ("wobble", "growl", "yoi", "pluck", "sweep", "machinegun", "duck")


def finite(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(name + " must be a finite number")
    return float(value)


def curve_points(
    shape,
    start,
    end,
    low=0.0,
    high=1.0,
    cycle_beats=1.0,
    resolution=0.0625,
    events=None,
    release_beats=0.5,
    hold_beats=0.0625,
):
    if shape not in SHAPES:
        raise ValueError("Unknown shape: " + str(shape))
    start, end = finite(start, "start"), finite(end, "end")
    low, high = finite(low, "low"), finite(high, "high")
    cycle = finite(cycle_beats, "cycle_beats")
    resolution = finite(resolution, "resolution")
    release = finite(release_beats, "release_beats")
    hold = finite(hold_beats, "hold_beats")
    if end <= start or end - start > 128 or not low <= high or not 0.125 <= cycle <= 32:
        raise ValueError("Invalid bounds, value range, or cycle (1/32 note to 8 bars)")
    if not 1 / 960 <= resolution <= 4 or not 0.015625 <= release <= 8 or not 0.015625 <= hold <= 4:
        raise ValueError("Invalid resolution, release, or hold")
    events = [] if events is None else [finite(t, "event time") for t in events]
    if len(events) > 256 or any(t < start or t >= end for t in events):
        raise ValueError("At most 256 event times, all inside clip bounds")
    # Bound transport and Live insert_step workload even for long clips.
    step = max(min(resolution, cycle / 8), (end - start) / 1024)
    if shape not in ("duck", "sweep") and step > cycle / 4:
        raise ValueError("Movement would be undersampled; shorten the clip or slow the cycle")
    count = max(1, int(math.ceil((end - start) / step)))
    times = {start + (end - start) * i / count for i in range(count + 1)}
    if shape == "duck":
        if not events:
            raise ValueError("duck requires actual kick event times")
        for event in events:
            times.update(
                t for t in [event, event + hold, event + hold + release] if start <= t <= end
            )
    if len(times) > 1800:
        raise ValueError("Too many curve points; use fewer kick events or a coarser resolution")
    points = []
    for t in sorted(times):
        phase = ((t - start) / cycle) % 1
        if shape == "wobble":
            v = (1 - math.cos(2 * math.pi * phase)) / 2
        elif shape == "growl":
            v = min(1, phase / 0.12) * math.exp(-3 * max(0, phase - 0.12))
        elif shape == "yoi":
            v = (phase / 0.2) if phase < 0.2 else ((1 - phase) / 0.8) ** 2
        elif shape == "pluck":
            v = math.exp(-6 * phase)
        elif shape == "sweep":
            v = min(1, (t - start) / (end - start))
        elif shape == "machinegun":
            # Brief fades avoid hard zero-crossing assumptions and DC-like clicks.
            v = min(1, phase / 0.08, max(0, (0.62 - phase) / 0.08))
        else:
            v = 1.0
            for event in events:
                age = t - event
                if 0 <= age < hold:
                    v = 0.0
                elif hold <= age < hold + release:
                    v = min(v, (age - hold) / release)
        points.append({"time": t, "value": low + (high - low) * max(0, min(1, v))})
    return points


def phrase(style="tearout", bars=4, root_midi=29, role="call", seed=0):
    if style not in ("tearout", "tearout_triplet", "brostep", "dubstep", "halftime"):
        raise ValueError("style must be tearout, tearout_triplet, brostep, dubstep, or halftime")
    if role not in ("call", "response", "sub"):
        raise ValueError("role must be call, response, or sub")
    if isinstance(bars, bool) or not isinstance(bars, int) or not 1 <= bars <= 32:
        raise ValueError("bars must be an integer in 1..32")
    if isinstance(root_midi, bool) or not isinstance(root_midi, int) or not 12 <= root_midi <= 84:
        raise ValueError("root_midi must be an integer in 12..84")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    rng = random.Random(seed)
    notes = []
    length = bars * 4
    for bar in range(bars):
        base = bar * 4
        if style == "halftime":
            events = [(0.3, 1.7), (2.5, 1.1)]
        elif style == "tearout_triplet":
            events = [
                (0, 0.22),
                (1 / 3, 0.2),
                (2 / 3, 0.2),
                (4 / 3, 0.3),
                (7 / 3, 0.25),
                (8 / 3, 0.2),
                (10 / 3, 0.2),
            ]
        elif style == "tearout":
            events = [(0.25, 0.45), (0.875, 0.2), (1.25, 0.2), (2.3, 0.45), (3, 0.2), (3.5, 0.2)]
        elif style == "brostep":
            events = [(0.25, 0.65), (1.25, 0.4), (2.3, 0.6), (3.5, 0.3)]
        else:
            events = [(0.3, 1.3), (2.3, 1.2)]
        for k, (offset, duration) in enumerate(events):
            if role == "call" and k >= (len(events) + 1) // 2:
                continue
            if role == "response" and k < (len(events) + 1) // 2:
                continue
            pitch = root_midi if role == "sub" else root_midi + (24 if role == "response" else 12)
            if role == "response" and k % 3 == 0:
                pitch += 1  # Explicit chromatic metallic accent, not a scale-constrained melody.
            notes.append(
                {
                    "pitch": pitch,
                    "start_time": base + offset,
                    "duration": min(duration, length - base - offset),
                    "velocity": (100 if role == "sub" else 112) + rng.randint(-8, 5),
                    "mute": False,
                }
            )
    return {
        "length": length,
        "notes": notes,
        "style": style,
        "role": role,
        "seed": seed,
        "timing": "beats in 4/4; does not change project tempo or signature",
    }


def inspect_sub_notes(notes):
    active = sorted([n for n in notes if not n.get("mute", False)], key=lambda n: n["start_time"])
    overlaps = []
    for i, first in enumerate(active):
        for second in active[i + 1 :]:
            if second["start_time"] >= first["start_time"] + first["duration"] - 1e-6:
                break
            overlaps.append({"first": first["start_time"], "second": second["start_time"]})
            if len(overlaps) >= 64:
                break
        if len(overlaps) >= 64:
            break
    pitches = sorted(set(int(n["pitch"]) for n in active))
    return {
        "note_count": len(active),
        "pitches": pitches,
        "overlaps": overlaps,
        "out_of_sub_register": [p for p in pitches if p < 24 or p > 48],
        "frequency_hz": {str(p): round(440 * 2 ** ((p - 69) / 12), 2) for p in pitches},
        "scope": "MIDI structure only; no audio level, phase, spectrum or mix-quality measurement",
    }
