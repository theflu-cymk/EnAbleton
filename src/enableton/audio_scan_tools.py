"""Read-only repair diagnostics exposed to MCP and CLI."""

import json
import subprocess
import sys

from .warp_analysis import finite, timing_fingerprint
from .warp_tools import _window


def scan_audio_file(path, start_seconds=0, max_seconds=30):
    start_seconds = finite(start_seconds, "start_seconds")
    max_seconds = finite(max_seconds, "max_seconds")
    if start_seconds < 0 or not 0 < max_seconds <= 120:
        raise ValueError("Invalid window; maximum 120 seconds")
    request = dict(path=str(path), start_seconds=start_seconds, max_seconds=max_seconds)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "enableton.audio_scan_worker"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=25,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Scan exceeded 25 seconds; use a shorter window") from exc
    if len(result.stdout) > 1_000_000:
        raise RuntimeError("Scan response exceeded 1 MB")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Audio scan worker failed") from exc
    if result.returncode or "error" in report:
        raise ValueError(report.get("error", "Audio scan worker failed"))
    return report


def scan_clip(dispatch, target, max_seconds=30):
    max_seconds = finite(max_seconds, "max_seconds")
    if not 0 < max_seconds <= 120:
        raise ValueError("Invalid window; maximum 120 seconds")
    timing = dispatch("get_audio_clip_timing", target)
    start, duration = _window(timing, finite(max_seconds, "max_seconds"))
    report = scan_audio_file(timing["file_path"], start, duration)
    latest = dispatch("get_audio_clip_timing", target)
    if timing_fingerprint(timing) != timing_fingerprint(latest):
        raise ValueError("Clip changed during scan; discard results and scan again")
    report["clip"] = {
        key: timing.get(key)
        for key in ("track_name", "clip_name", "warping", "warp_mode", "arrangement_start")
    }
    return report


def register_audio_scan(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def scan_audio_problems(path: str, start_seconds: float = 0, max_seconds: float = 30) -> dict:
        """Scan local integer PCM WAV for measured levels/DC and suspected clicks, gaps,
        near-full-scale peaks and level jumps. Returns source timestamps, evidence,
        confidence and targeted repair recipes. Bounded window, not audition or automatic
        smoothing. Other formats and unassessed defects are explicit. No writes.
        """
        return scan_audio_file(path, start_seconds, max_seconds)

    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def scan_clip_audio_problems(target: dict, max_seconds: float = 30) -> dict:
        """Scan the source WAV window of one explicit Session/Arrangement audio clip.
        target uses track_index, clip_index, clip_view and optional name/start guards.
        Rechecks clip timing after scan. Reports source seconds; effects, fades and Warp
        playback are not rendered or analyzed. No edits, playback or automatic repair.
        """
        return scan_clip(dispatch, target, max_seconds)
