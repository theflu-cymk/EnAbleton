"""Groove comparison and marker planning over explicit beat positions.

Ported from the community ableton-mcp PR #1 (``audio_analysis`` groove helpers)
with the numpy dependency removed, input bounds added and the same honest limit:
an offset is the distance to the nearest event, which is not proof of intent.
Intentional swing and triplet phrasing must never be silently "corrected".
"""

import bisect
import statistics

from .numbers import finite

MAX_NOTES = 20000


def _bpm(value):
    bpm = finite(value, "bpm")
    if not 20 <= bpm <= 999:
        raise ValueError("bpm must be within 20..999")
    return bpm


def _positions(rows, label):
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_NOTES:
        raise ValueError(label + " must hold 1..20000 beat positions")
    return sorted(finite(row, label + " entry") for row in rows)


def _notes(rows, label):
    """Validate explicit notes; input order is never trusted."""
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_NOTES:
        raise ValueError(label + " must hold 1..20000 notes")
    clean = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(label + " entries need pitch and start_time")
        pitch = row.get("pitch", 60)
        if isinstance(pitch, bool) or not isinstance(pitch, int) or not 0 <= pitch <= 127:
            raise ValueError("pitch must be an integer within 0..127")
        clean.append((pitch, finite(row.get("start_time"), "start_time")))
    clean.sort(key=lambda pair: (pair[1], pair[0]))
    return clean


def _nearest(times, value):
    at = bisect.bisect_left(times, value)
    options = [times[i] for i in (at - 1, at) if 0 <= i < len(times)]
    return min(options, key=lambda t: abs(t - value))


def _grid_offsets(positions, grid, tolerance):
    offsets = []
    for beat in positions:
        offset = beat - round(beat / grid) * grid
        if abs(offset) <= tolerance:
            offsets.append(offset)
    return offsets


def groove_offset_report(vocal_onsets, drum_hits, bpm=120.0, grid_beats=1.0, tolerance_beats=0.25):
    """Mean distance from the grid for each source, and the constant shift that matches them."""
    bpm = _bpm(bpm)
    grid = finite(grid_beats, "grid_beats")
    tolerance = finite(tolerance_beats, "tolerance_beats")
    if not 0.03125 <= grid <= 4:
        raise ValueError("grid_beats must be within 0.03125..4")
    if not 0 < tolerance <= 1:
        raise ValueError("tolerance_beats must be within (0,1]")
    vocal = _grid_offsets(_positions(vocal_onsets, "vocal_onsets"), grid, tolerance)
    drum = _grid_offsets(_positions(drum_hits, "drum_hits"), grid, tolerance)
    ms_per_beat = 60000.0 / bpm
    vocal_ms = statistics.mean(vocal) * ms_per_beat if vocal else 0.0
    drum_ms = statistics.mean(drum) * ms_per_beat if drum else 0.0
    shift_ms = drum_ms - vocal_ms
    return {
        "vocal_grid_offset_ms": round(vocal_ms, 1),
        "drum_grid_offset_ms": round(drum_ms, 1),
        "recommended_shift_ms": round(shift_ms, 1),
        "recommended_shift_beats": round(shift_ms / ms_per_beat, 4),
        "vocal_onsets_used": len(vocal),
        "drum_hits_used": len(drum),
        "bpm": bpm,
        "grid_beats": grid,
        "used_events_note": "Only events within tolerance of a grid line are averaged",
        "limits": "A constant shift corrects feel, not phrase structure; audition before moving clips",
    }


def groove_alignment(source_notes, target_notes, source_offset=0.0, bpm=120.0, match_by_pitch=True):
    """Per-note distance from each source note to its nearest target event."""
    bpm = _bpm(bpm)
    offset = finite(source_offset, "source_offset")
    source = _notes(source_notes, "source_notes")
    target = _notes(target_notes, "target_notes")
    if not isinstance(match_by_pitch, bool):
        raise ValueError("match_by_pitch must be boolean")
    by_pitch = {}
    for pitch, start in target:
        by_pitch.setdefault(pitch, []).append(start)
    all_times = sorted(start for _, start in target)
    alignments = []
    for pitch, start in source:
        candidates = by_pitch.get(pitch) if match_by_pitch else None
        target_time = _nearest(candidates or all_times, start + offset)
        beats = start + offset - target_time
        alignments.append(
            {
                "source_beat": round(start, 4),
                "target_beat": round(target_time, 4),
                "offset_beats": round(beats, 4),
                "offset_ms": round(beats * 60000.0 / bpm, 1),
                "pitch": pitch,
            }
        )
    offsets = [row["offset_beats"] for row in alignments]
    return {
        "alignments": alignments,
        "statistics": {
            "notes": len(offsets),
            "mean_offset_beats": round(statistics.mean(offsets), 4) if offsets else 0.0,
            "std_offset_beats": round(statistics.pstdev(offsets), 4) if len(offsets) > 1 else 0.0,
            "min_offset_beats": round(min(offsets), 4) if offsets else 0.0,
            "max_offset_beats": round(max(offsets), 4) if offsets else 0.0,
        },
        "bpm": bpm,
        "source_offset": offset,
        "match_by_pitch": match_by_pitch,
        "limits": "Nearest-event matching only; different instrument roles can pair by accident",
    }


def groove_marker_plan(
    source_notes,
    target_notes,
    source_offset=0.0,
    bpm=120.0,
    min_offset_ms=20.0,
    match_by_pitch=True,
    min_spacing_beats=0.0,
    pitch_filter=None,
    max_markers=0,
    quantize_targets_to=0.0,
    markers_per_bar=0.0,
):
    """Turn per-note offsets into a warp-marker plan for one clip.

    ``original_beat`` is where the audio currently lands, ``target_beat`` where the
    groove wants it. Apply these to a fresh duplicate only.
    """
    bpm = _bpm(bpm)
    minimum = finite(min_offset_ms, "min_offset_ms")
    spacing = finite(min_spacing_beats, "min_spacing_beats")
    per_bar = finite(markers_per_bar, "markers_per_bar")
    grid = finite(quantize_targets_to, "quantize_targets_to")
    if minimum < 0 or spacing < 0 or per_bar < 0 or grid < 0:
        raise ValueError("Offsets, spacing, density and grid cannot be negative")
    if (
        isinstance(max_markers, bool)
        or not isinstance(max_markers, int)
        or not 0 <= max_markers <= 512
    ):
        raise ValueError("max_markers must be an integer 0..512")
    wanted = None
    if pitch_filter is not None:
        if not isinstance(pitch_filter, list) or not pitch_filter:
            raise ValueError("pitch_filter must be a non-empty list of pitches")
        wanted = []
        for pitch in pitch_filter:
            if isinstance(pitch, bool) or not isinstance(pitch, int) or not 0 <= pitch <= 127:
                raise ValueError("pitch_filter entries must be integers 0..127")
            wanted.append(pitch)
    analysis = groove_alignment(source_notes, target_notes, source_offset, bpm, match_by_pitch)
    rows = analysis["alignments"]
    if wanted is not None:
        rows = [row for row in rows if row["pitch"] in wanted]
    rows = [row for row in rows if abs(row["offset_ms"]) >= minimum]
    rows.sort(key=lambda row: abs(row["offset_ms"]), reverse=True)
    if max_markers:
        rows = rows[:max_markers]
    rows.sort(key=lambda row: row["source_beat"])
    effective_spacing = 4.0 / per_bar if per_bar else spacing
    kept = []
    last = None
    for row in rows:
        if last is not None and row["source_beat"] - last < effective_spacing:
            continue
        kept.append(row)
        last = row["source_beat"]
    markers = []
    for row in kept:
        target = row["target_beat"]
        if grid:
            target = round(target / grid) * grid
        markers.append(
            {
                "original_beat": row["source_beat"],
                "target_beat": round(target, 6),
                "original_seconds": round(row["source_beat"] * 60.0 / bpm, 4),
                "target_seconds": round(target * 60.0 / bpm, 4),
                "offset_ms": row["offset_ms"],
                "pitch": row["pitch"],
            }
        )
    markers.sort(key=lambda row: row["original_beat"])
    return {
        "markers": markers,
        "count": len(markers),
        "candidates_before_spacing": len(rows),
        "effective_spacing_beats": round(effective_spacing, 4),
        "min_offset_ms": minimum,
        "quantize_targets_to": grid,
        "bpm": bpm,
        "limits": (
            "Markers come from nearest-event offsets of explicit note lists; wrong note "
            "pairing or intentional swing can produce musically wrong markers. Apply to a duplicate."
        ),
    }


def onsets_to_note_grid(onsets, bpm=120.0, pitch=38, min_strength=0.0):
    """Convert measured onsets (absolute seconds) into a note grid for groove analysis.

    This is the dependency-free stand-in for the upstream ``vocal_to_midi``: it keeps
    the measured attack and strength but does no phoneme classification, so treat the
    notes as rhythm, not as lyrics or pitch.
    """
    bpm = _bpm(bpm)
    if isinstance(pitch, bool) or not isinstance(pitch, int) or not 0 <= pitch <= 127:
        raise ValueError("pitch must be an integer 0..127")
    minimum = finite(min_strength, "min_strength")
    if not 0 <= minimum <= 1:
        raise ValueError("min_strength must be within 0..1")
    if not isinstance(onsets, list) or not 1 <= len(onsets) <= MAX_NOTES:
        raise ValueError("onsets must hold 1..20000 measured events")
    rows = []
    for onset in onsets:
        if not isinstance(onset, dict):
            raise ValueError("onset entries need time and strength")
        seconds = finite(onset.get("time"), "onset time")
        strength = finite(onset.get("strength", 1.0), "onset strength")
        if strength < minimum:
            continue
        rows.append((seconds, strength))
    if not rows:
        raise ValueError("No onset passed min_strength")
    rows.sort()
    beats = [seconds * bpm / 60.0 for seconds, _ in rows]
    notes = []
    for index, (seconds, strength) in enumerate(rows):
        gap = (beats[index + 1] - beats[index]) if index + 1 < len(beats) else 0.5
        notes.append(
            {
                "pitch": pitch,
                "start_time": round(beats[index], 6),
                "duration": round(min(1.0, max(0.05, gap)), 6),
                "velocity": max(1, min(127, round(30 + 97 * strength))),
                "mute": False,
                "source_seconds": round(seconds, 6),
                "strength": round(strength, 4),
            }
        )
    return {
        "notes": notes,
        "count": len(notes),
        "bpm": bpm,
        "assumes_constant_rate": True,
        "limits": (
            "Seconds are converted at the given BPM, so this is valid for unwarped audio. "
            "For a warped clip convert with its own map first, or pass beats directly."
        ),
    }


def quantize_notes_to_groove(
    source_notes, target_notes, source_offset=0.0, max_snap_beats=1.0, match_by_pitch=True
):
    """Snap each source note to its nearest target event, keeping far notes unchanged."""
    limit = finite(max_snap_beats, "max_snap_beats")
    if not 0 < limit <= 8:
        raise ValueError("max_snap_beats must be within (0,8]")
    source = _notes(source_notes, "source_notes")
    target = _notes(target_notes, "target_notes")
    offset = finite(source_offset, "source_offset")
    by_pitch = {}
    for pitch, start in target:
        by_pitch.setdefault(pitch, []).append(start)
    all_times = sorted(start for _, start in target)
    moved = 0
    notes = []
    for pitch, start in source:
        candidates = (by_pitch.get(pitch) if match_by_pitch else None) or all_times
        nearest = _nearest(candidates, start + offset)
        if abs(start + offset - nearest) <= limit:
            new_start = nearest - offset
            moved += 1
        else:
            new_start = start
        notes.append({"pitch": pitch, "start_time": round(new_start, 6)})
    return {
        "notes": notes,
        "snapped": moved,
        "unchanged": len(notes) - moved,
        "max_snap_beats": limit,
        "limits": "Snapping destroys intentional feel; keep the original clip and compare",
    }
