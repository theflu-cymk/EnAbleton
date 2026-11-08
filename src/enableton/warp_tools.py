"""Audio analysis runs in a bounded subprocess; Live writes are duplicate-only."""

import json
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid
from .bridge_version import VERSION
from .jsonio import atomic_json
from .warp_analysis import (
    audit_timing,
    beat_to_source,
    compare_reference,
    finite,
    plan_moves,
    timing_fingerprint,
)

_cache = {}
_previews = {}
_lock = threading.Lock()


def _file_identity(path):
    path = Path(path)
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Source file is unavailable")
    stat = path.stat()
    return {"path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def _analyze(path, start_seconds=0, max_seconds=30, tempo_hint=None):
    path = Path(path)
    start_seconds = finite(start_seconds, "start_seconds")
    max_seconds = finite(max_seconds, "max_seconds")
    if start_seconds < 0 or not 0 < max_seconds <= 120:
        raise ValueError("Invalid window; maximum 120 seconds")
    if not path.is_absolute() or not path.is_file():
        raise ValueError("Existing absolute local file required")
    stat = path.stat()
    key = (
        str(path.resolve()),
        stat.st_size,
        stat.st_mtime_ns,
        start_seconds,
        max_seconds,
        tempo_hint,
    )
    now = time.monotonic()
    with _lock:
        if key in _cache and now - _cache[key][0] < 1800:
            return _cache[key][1]
    request = dict(
        path=str(path), start_seconds=start_seconds, max_seconds=max_seconds, tempo_hint=tempo_hint
    )
    try:
        result = subprocess.run(
            [sys.executable, "-m", "enableton.warp_audio_worker"],
            input=json.dumps(request),
            capture_output=True,
            text=True,
            timeout=25,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Audio analysis exceeded 25 seconds; no Live changes made") from error
    if len(result.stdout) > 4_000_000:
        raise RuntimeError("Analysis response exceeded 4 MB")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Audio worker returned invalid output") from error
    if result.returncode or "error" in data:
        raise RuntimeError(data.get("error", "Audio worker failed"))
    latest = path.stat()
    if (latest.st_size, latest.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
        raise RuntimeError("Source file changed during analysis")
    data["source_file_identity"] = {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
    with _lock:
        if len(_cache) >= 16:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (now, data)
    return data


def _window(timing, max_seconds):
    if timing["warping"]:
        begin = timing["loop_start"] if timing["looping"] else timing["start_marker"]
        end = timing["loop_end"] if timing["looping"] else timing["end_marker"]
        start = beat_to_source(begin, timing["warp_markers"])
        stop = beat_to_source(end, timing["warp_markers"])
    else:
        start = timing["start_marker"]
        stop = timing["end_marker"]
    if stop <= start:
        raise ValueError("Invalid source analysis window")
    return max(0, start), min(max_seconds, stop - max(0, start))


def register_warp(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def describe_warp_workflow() -> dict:
        """List implemented warp analysis, preview repair and runtime limits."""
        return {
            "version": VERSION,
            "audio_analysis": "Local PCM WAV, bounded 120-second windows in a 25-second subprocess; per-file metadata cache",
            "analysis": [
                "BPM candidates, heuristic confidence and half/double-time ambiguity",
                "Strong-attack downbeat candidates, never assumed musical beat one",
                "Warp slope, order, abrupt drift and explicit bar-length checks",
                "Straight, triplet or 2:1 swing transient-to-grid review",
                "Exact-window loop seam discontinuity estimate",
                "Reference-event offset comparison",
                "Warp-mode audition guidance",
            ],
            "repair": "Preview token -> saved timing backup -> apply existing-marker moves to a non-overlapping duplicate only -> verify original unchanged -> audition",
            "limits": [
                "No automatic changes from estimated tempo or transient detections",
                "No audio audition or semantic beat-one guarantee",
                "No destructive in-place marker replacement",
                "No new-marker insertion/deletion in this release",
                "Unsupported/compressed audio formats fail explicitly; PCM WAV only",
                "Batch audio analysis is partial when file/time budgets are reached",
                "Real Live marker-move API remains capability-gated and needs readback; synthetic tests do not certify sonic quality",
            ],
        }

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def analyze_warp_audio(
        path: str,
        start_seconds: float = 0,
        max_seconds: float = 30,
        tempo_hint: float | None = None,
    ) -> dict:
        """Estimate tempo and candidate downbeats from a bounded local PCM WAV window.
        Returns measured onset events, heuristic confidence, half/double alternatives,
        loop-edge discontinuity estimate and warp-mode guidance. Not audio audition.
        Unsupported files fail explicitly; no Live access or changes.
        """
        return _analyze(path, start_seconds, max_seconds, tempo_hint)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def audit_warp_clip(
        target: dict,
        analyze_audio: bool = True,
        max_seconds: float = 30,
        grid_beats: float = 0.25,
        groove: str = "straight",
        tolerance_ms: float = 25,
        expected_bars: float | None = None,
    ) -> dict:
        """Read Session/Arrangement warp timing and optionally analyze its source WAV.
        Checks marker order/slopes/drift, explicit bar length, source BPM versus mapping,
        transient alignment and exact-window seam. Groove straight|triplet|swing.
        Flags are structural errors or review candidates, never automatic repairs.
        target uses track_index, clip_index, clip_view and optional name/start guards.
        """
        timing = dispatch("get_audio_clip_timing", target)
        audio = None
        error = None
        if analyze_audio:
            try:
                start, window = _window(timing, max_seconds)
                audio = _analyze(timing["file_path"], start, window)
            except (ValueError, RuntimeError, OSError) as exc:
                error = str(exc)
        tempo = dispatch("get_session_info", {})["tempo"]
        audit = audit_timing(timing, audio, grid_beats, groove, tolerance_ms, tempo, expected_bars)
        return {
            "timing": timing,
            "audit": audit,
            "audio_analysis": audio,
            "audio_error": error,
            "coverage": "Windowed audio analysis; tempo automation and later source sections are not inferred",
        }

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def compare_warp_reference(
        candidate_beats: list[float], reference_beats: list[float], max_offset_beats: float = 1
    ) -> dict:
        """Compare explicit measured/reference event times in a shared beat coordinate
        system. Suggests a constant offset; no automatic matching of instrument roles,
        phrase structure or groove. Does not modify Live.
        """
        return compare_reference(candidate_beats, reference_beats, max_offset_beats)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def preview_warp_repair(
        target: dict,
        moves: list[dict],
        destination_time: float,
        max_shift_beats: float = 0.125,
        warp_mode: int | None = None,
    ) -> dict:
        """Preview explicit existing-marker moves WITHOUT editing Live. Requires track
        and clip names; Arrangement source requires expected_start_time. Preserves
        first/hidden terminal anchors and source sample positions; detects crossing,
        excessive shifts and invalid slopes. Destination is for a later duplicate,
        in Arrangement beats. Token expires after 10 min and after one apply attempt.
        """
        if not target.get("expected_track_name") or not target.get("expected_clip_name"):
            raise ValueError("Track and clip name guards required")
        if target.get("clip_view") == "arrangement" and target.get("expected_start_time") is None:
            raise ValueError("Arrangement start guard required")
        destination_time = finite(destination_time, "destination_time")
        if not 0 <= destination_time <= 1576800:
            raise ValueError("Invalid destination")
        timing = dispatch("get_audio_clip_timing", target)
        if not timing.get("marker_api", {}).get("move_warp_marker"):
            raise RuntimeError("Live does not expose marker moves on this clip")
        plan = plan_moves(timing, moves, max_shift_beats)
        if warp_mode is not None and (
            isinstance(warp_mode, bool)
            or not isinstance(warp_mode, int)
            or warp_mode not in timing.get("available_warp_modes", [])
        ):
            raise ValueError("Warp mode unavailable")
        arr = dispatch("get_arrangement_clips", {"track_index": target["track_index"]})["clips"]
        length = timing.get("arrangement_end", timing["end_marker"]) - timing.get(
            "arrangement_start", timing["start_marker"]
        )
        if timing.get("looping") and target.get("clip_view", "session") == "session":
            length = timing["loop_end"] - timing["loop_start"]
        if any(
            destination_time < c["end_time"] - 1e-6
            and destination_time + length > c["start_time"] + 1e-6
            for c in arr
        ):
            raise ValueError("Preview destination overlaps Arrangement content")
        token = uuid.uuid4().hex
        row = {
            "created": time.monotonic(),
            "target": dict(target),
            "timing": timing,
            "plan": plan,
            "destination_time": destination_time,
            "warp_mode": warp_mode,
            "source_file_identity": _file_identity(timing["file_path"]),
        }
        with _lock:
            if len(_previews) >= 64:
                _previews.pop(next(iter(_previews)))
            _previews[token] = row
        return {
            "preview_token": token,
            "expires_in_seconds": 600,
            "plan": plan,
            "destination_time": destination_time,
            "source_timing": timing,
            "mutated_live": False,
            "next": "Review moves, then apply_warp_repair. Original is preserved; repaired duplicate must be auditioned.",
        }

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def apply_warp_repair(preview_token: str) -> dict:
        """Apply a reviewed preview to a non-overlapping duplicate ONLY. Saves the
        source timing/plan before writing. Refuses stale/expired tokens and changed
        files/targets, validates every marker, verifies original unchanged. Never
        starts playback or replaces the original. After a timeout, inspect state;
        token cannot be replayed. Needs EXT.5 Live bridge and actual marker API.
        """
        with _lock:
            row = _previews.pop(preview_token, None)
        if not row or time.monotonic() - row["created"] > 600:
            raise ValueError("Expired, unknown or consumed preview; create a fresh preview")
        current = dispatch("get_audio_clip_timing", row["target"])
        if timing_fingerprint(current) != row["plan"]["before_fingerprint"]:
            raise ValueError("Target changed since preview")
        if _file_identity(current["file_path"]) != row["source_file_identity"]:
            raise ValueError("Source file changed since preview")
        folder = Path.home() / ".enableton" / "backups" / "warp-repairs"
        backup = folder / (time.strftime("%Y%m%d-%H%M%S") + "-" + preview_token + ".json")
        atomic_json(
            backup,
            {
                "target": row["target"],
                "source_timing": row["timing"],
                "plan": row["plan"],
                "destination_time": row["destination_time"],
                "source_file_identity": row["source_file_identity"],
            },
        )
        try:
            result = dispatch(
                "repair_warp_duplicate",
                {
                    "target": row["target"],
                    "moves": row["plan"]["moves"],
                    "max_shift_beats": row["plan"]["max_shift_beats"],
                    "expected_fingerprint": row["plan"]["before_fingerprint"],
                    "destination_time": row["destination_time"],
                    "warp_mode": row["warp_mode"],
                    "operation_id": preview_token,
                },
            )
        except Exception as error:
            atomic_json(
                backup.with_suffix(".result.json"),
                {"status": "failed_or_unknown", "error": str(error), "inspect_before_retry": True},
            )
            raise RuntimeError(
                "Apply failed or outcome unknown; inspect Live before retrying. Backup: "
                + str(backup)
                + ". "
                + str(error)
            ) from error
        try:
            atomic_json(backup.with_suffix(".result.json"), result)
        except OSError as error:
            result["journal_warning"] = (
                "Live operation completed, but result journal failed: " + str(error)
            )
        return dict(result, backup_path=str(backup))

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def batch_warp_audit(
        targets: list[dict], max_audio_files: int = 4, max_seconds_per_file: float = 15
    ) -> dict:
        """Read-only audit of up to 256 explicit clip targets, with per-clip failures,
        source-analysis deduplication and a 45-second batch budget. Max 8 unique WAV
        windows, 15 seconds each; returns explicit skipped/unverified coverage. No
        recoloring, marker changes or playback. Process further targets in another batch.
        """
        if (
            not 1 <= len(targets) <= 256
            or isinstance(max_audio_files, bool)
            or not isinstance(max_audio_files, int)
            or not 0 <= max_audio_files <= 8
        ):
            raise ValueError("Invalid batch budget")
        max_seconds_per_file = finite(max_seconds_per_file, "max_seconds_per_file")
        if not 0 < max_seconds_per_file <= 15:
            raise ValueError("Window must be <=15 seconds in a batch")
        begin = time.monotonic()
        seen = {}
        rows = []
        tempo = dispatch("get_session_info", {})["tempo"]
        for i, target in enumerate(targets):
            if time.monotonic() - begin > 45:
                rows.extend({"target": r, "status": "skipped_time_budget"} for r in targets[i:])
                break
            try:
                timing = dispatch("get_audio_clip_timing", target)
                audio = None
                error = None
                start, window = _window(timing, max_seconds_per_file)
                key = (timing["file_path"], round(start, 6), round(window, 6))
                if key in seen:
                    audio, error = seen[key]
                elif len(seen) < max_audio_files and time.monotonic() - begin < 20:
                    try:
                        audio = _analyze(timing["file_path"], start, window)
                    except Exception as exc:
                        error = str(exc)
                    seen[key] = (audio, error)
                else:
                    error = "Audio file/window budget reached; structural checks only"
                report = audit_timing(timing, audio, project_bpm=tempo)
                if "transient_alignment" in report:
                    report["transient_alignment"].pop("events", None)
                rows.append(
                    {
                        "target": target,
                        "status": "audited",
                        "audio_checked": audio is not None,
                        "audio_error": error,
                        "audit": report,
                    }
                )
            except Exception as error:
                rows.append({"target": target, "status": "failed", "error": str(error)})
        return {
            "results": rows,
            "requested": len(targets),
            "audio_windows_attempted": len(seen),
            "read_only": True,
            "limits": "Structural/heuristic checks only. Skipped and unsupported windows remain unverified; no audio was auditioned.",
        }
