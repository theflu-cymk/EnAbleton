"""Groove and offline-envelope tools ported from the community ableton-mcp fork."""

from pathlib import Path

from . import groove as groove_math
from .als_automation import ENERGY_CC, inject_file
from .numbers import finite
from .warp_tools import _analyze


def register_groove(mcp):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def groove_offset_report(
        vocal_onsets: list[float],
        drum_hits: list[float],
        bpm: float = 120.0,
        grid_beats: float = 1.0,
        tolerance_beats: float = 0.25,
    ) -> dict:
        """Compare two explicit beat-position lists to the grid and recommend one constant
        shift. Only events within tolerance of a grid line are averaged. Reports ms and
        beats plus how many events were used. A constant shift corrects feel, not phrase
        structure: audition before moving clips. No Live access or changes.
        """
        return groove_math.groove_offset_report(
            vocal_onsets, drum_hits, bpm, grid_beats, tolerance_beats
        )

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def groove_alignment_report(
        source_notes: list[dict],
        target_notes: list[dict],
        source_offset: float = 0,
        bpm: float = 120.0,
        match_by_pitch: bool = True,
    ) -> dict:
        """Per-note offset from each source note to its nearest target event, plus mean,
        spread, min and max. notes are {pitch, start_time} in a shared beat timeline.
        Nearest-event matching only: different instrument roles can pair by accident, and
        intentional swing is not an error. No Live access or changes.
        """
        return groove_math.groove_alignment(
            source_notes, target_notes, source_offset, bpm, match_by_pitch
        )

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def groove_marker_plan(
        source_notes: list[dict],
        target_notes: list[dict],
        source_offset: float = 0,
        bpm: float = 120.0,
        min_offset_ms: float = 20,
        match_by_pitch: bool = True,
        min_spacing_beats: float = 0,
        pitch_filter: list[int] | None = None,
        max_markers: int = 0,
        quantize_targets_to: float = 0,
        markers_per_bar: float = 0,
    ) -> dict:
        """Plan warp markers from explicit source/target note lists: original_beat,
        target_beat and seconds per marker, with minimum offset, spacing, density, pitch
        filter and caps. Writes nothing. Apply to a fresh duplicate only and audition;
        wrong note pairing or intentional swing can produce musically wrong markers.
        """
        return groove_math.groove_marker_plan(
            source_notes,
            target_notes,
            source_offset,
            bpm,
            min_offset_ms,
            match_by_pitch,
            min_spacing_beats,
            pitch_filter,
            max_markers,
            quantize_targets_to,
            markers_per_bar,
        )

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def quantize_notes_to_groove(
        source_notes: list[dict],
        target_notes: list[dict],
        source_offset: float = 0,
        max_snap_beats: float = 1.0,
        match_by_pitch: bool = True,
    ) -> dict:
        """Snap each source note to its nearest target event within max_snap_beats, leaving
        far notes unchanged, and report how many moved. Snapping removes intentional feel:
        keep the original clip to compare. No Live access or changes.
        """
        return groove_math.quantize_notes_to_groove(
            source_notes, target_notes, source_offset, max_snap_beats, match_by_pitch
        )

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def local_onsets_to_notes(
        path: str,
        bpm: float | None = None,
        pitch: int = 38,
        min_strength: float = 0,
        start_seconds: float = 0,
        max_seconds: float = 30,
    ) -> dict:
        """Measure onsets in a bounded local PCM WAV window and convert them to a note grid
        for groove work; strength becomes velocity. No phoneme, lyric or pitch detection,
        so the notes are rhythm only. Seconds convert at a constant BPM, so use unwarped
        audio or convert with the clip's warp map first. No Live access or changes.
        """
        analysis = _analyze(path, start_seconds, max_seconds, bpm)
        effective = bpm if bpm is not None else analysis["tempo"].get("bpm")
        if not effective:
            raise ValueError("No usable tempo: pass bpm explicitly")
        grid = groove_math.onsets_to_note_grid(analysis["onsets"], effective, pitch, min_strength)
        return {
            "notes": grid["notes"],
            "count": grid["count"],
            "bpm": grid["bpm"],
            "bpm_source": "argument" if bpm is not None else "heuristic estimate",
            "tempo_confidence": analysis["tempo"].get("confidence"),
            "assumes_constant_rate": grid["assumes_constant_rate"],
            "limits": grid["limits"],
        }

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def inject_saved_clip_envelope(
        als_path: str,
        track_pattern: str,
        clip_time: float,
        cc: int,
        points: list[dict],
        output_path: str | None = None,
        replace: bool = False,
        dry_run: bool = True,
    ) -> dict:
        """Write one MIDI CC automation envelope into a SAVED .als with Live closed, for the
        MIDI clip that starts at clip_time beats on the single track matching the name
        pattern. points are clip-relative beats with normalized 0..1 values, strictly
        increasing, stored as 0..127. Requires that track's ControllerTargets.<cc>, so
        create the MIDI track in Live first. Dry run by default; an in-place write is
        backed up and re-read. Close Live before writing: a save would overwrite this.
        Verification is file-level, not a Live readback.
        """
        if not track_pattern:
            raise ValueError("track_pattern required")
        if not Path(als_path).is_absolute():
            raise ValueError("Absolute .als path required")
        return inject_file(
            als_path,
            track_pattern,
            finite(clip_time, "clip_time"),
            cc,
            points,
            output_path,
            replace,
            dry_run,
        )

    return {"energy_cc": ENERGY_CC}
