"""Bounded full-sample PCM diagnostics; findings are review candidates, not audition."""

import math
from pathlib import Path
import wave

from .warp_analysis import finite, MAX_FILE_BYTES


RECIPES = {
    "discontinuity": {
        "steps": [
            "Audition the flagged seam and inspect the waveform.",
            "At an edit, try a 2–5 ms fade/crossfade; use longer fades for bass if needed.",
            "Inside continuous audio, try local de-click/interpolation instead of fading the whole note.",
        ],
        "source": "https://help.ableton.com/hc/en-us/articles/209069969-Create-Fades-on-Clip-Edges-to-avoid-clicks",
    },
    "near_full_scale": {
        "steps": [
            "Inspect and audition the peak; near-full-scale samples alone do not prove clipping.",
            "If flattened peaks are distorted, try de-clip on a copy or replace the passage.",
            "Reduce gain to prevent further overload; a limiter cannot restore lost peaks.",
        ],
    },
    "silence_gap": {
        "steps": [
            "Check whether the silence is an intentional rest or gate.",
            "For a damaged short gap, try spectral replacement/interpolation on a copy.",
            "For longer missing material, copy a matching phrase or sustain and crossfade.",
        ],
        "source": "https://downloads.izotope.com/docs/rx6/35-spectral-repair/index.html",
    },
    "level_jump": {
        "steps": [
            "Check whether the change is musical or an edit with mismatched level.",
            "Match phrases with clip gain first.",
            "If still needed, try 2:1 compression, 10–30 ms attack, 100–300 ms release; tune by ear.",
        ],
    },
    "dc_offset": {
        "steps": [
            "Check a longer representative section; asymmetric waveforms can bias a short window.",
            "If persistent, try DC removal on a copy and compare the bass and transients.",
        ],
    },
}


def scan_pcm(path, start_seconds=0, max_seconds=30):
    """Stream every sample in a bounded integer PCM WAV window without changing it."""
    start = finite(start_seconds, "start_seconds")
    duration = finite(max_seconds, "max_seconds")
    if start < 0 or not 0 < duration <= 120:
        raise ValueError("Use start_seconds >= 0 and 0 < max_seconds <= 120")
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Existing absolute local PCM WAV <=512 MiB required")
    if path.suffix.lower() not in {".wav", ".wave"}:
        raise ValueError("Only integer PCM WAV is supported; export a PCM WAV copy")
    before = path.stat()
    findings = []
    counts = {}

    def finding(code, first, last, channel, evidence, confidence="low"):
        counts[code] = counts.get(code, 0) + 1
        if counts[code] <= 24:
            findings.append(
                dict(
                    code=code,
                    severity="review",
                    confidence=confidence,
                    start_seconds=first,
                    end_seconds=last,
                    channel=channel,
                    evidence=evidence,
                    recipe=code,
                    autofixable=False,
                )
            )

    with wave.open(str(path), "rb") as audio:
        sr, channels, width, total = (
            audio.getframerate(),
            audio.getnchannels(),
            audio.getsampwidth(),
            audio.getnframes(),
        )
        if not 8000 <= sr <= 192000 or not 1 <= channels <= 8 or width not in (1, 2, 3, 4):
            raise ValueError("Supported PCM: 8/16/24/32-bit, 8–192 kHz, 1–8 channels")
        first = round(start * sr)
        if first >= total:
            raise ValueError("Window begins after end of source")
        frames = min(round(duration * sr), total - first, 4_000_000 // channels)
        if frames < 1:
            raise ValueError("Window contains no samples")
        audio.setpos(first)
        sums, squares, peaks, rails = ([0.0] * channels for _ in range(4))
        previous = [None] * channels
        last_jump = [-sr] * channels
        rail_start = [None] * channels
        blocks = []
        done = 0
        scale = 2 ** (width * 8 - 1)
        hop = max(1, round(sr * 0.01))
        while done < frames:
            n = min(hop, frames - done)
            raw = audio.readframes(n)
            if len(raw) != n * channels * width:
                raise ValueError("Truncated PCM data; scan incomplete")
            energy = 0.0
            for frame in range(n):
                index = done + frame
                for ch in range(channels):
                    offset = (frame * channels + ch) * width
                    value = (
                        (raw[offset] - 128)
                        if width == 1
                        else int.from_bytes(raw[offset : offset + width], "little", signed=True)
                    ) / scale
                    sums[ch] += value
                    squares[ch] += value * value
                    peaks[ch] = max(peaks[ch], abs(value))
                    energy += value * value
                    if abs(value) >= 1 - 1 / scale:
                        rails[ch] += 1
                        if rail_start[ch] is None:
                            rail_start[ch] = index
                    elif rail_start[ch] is not None:
                        begin = rail_start[ch]
                        finding(
                            "near_full_scale",
                            (first + begin) / sr,
                            (first + index) / sr,
                            ch + 1,
                            {"consecutive_rail_samples": index - begin},
                            "medium",
                        )
                        rail_start[ch] = None
                    delta = abs(value - previous[ch]) if previous[ch] is not None else 0
                    if delta > 0.35 and index - last_jump[ch] >= sr * 0.01:
                        finding(
                            "discontinuity",
                            (first + index) / sr,
                            (first + index + 1) / sr,
                            ch + 1,
                            {
                                "adjacent_sample_delta": delta,
                                "caveat": "Percussion and bright waveforms can trigger this.",
                            },
                        )
                        last_jump[ch] = index
                    previous[ch] = value
            blocks.append((done, n, math.sqrt(energy / (n * channels))))
            done += n
        for ch in range(channels):
            if rail_start[ch] is not None:
                finding(
                    "near_full_scale",
                    (first + rail_start[ch]) / sr,
                    (first + frames) / sr,
                    ch + 1,
                    {"consecutive_rail_samples": frames - rail_start[ch]},
                    "medium",
                )
            dc = sums[ch] / frames
            if abs(dc) > 0.01:
                finding(
                    "dc_offset",
                    first / sr,
                    (first + frames) / sr,
                    ch + 1,
                    {"mean_amplitude": dc},
                    "medium",
                )
        gap_start = None
        for i, (offset, n, rms) in enumerate(blocks):
            if rms <= 0.00001:
                if gap_start is None:
                    gap_start = i
            elif gap_start is not None:
                if gap_start > 0 and blocks[gap_start - 1][2] > 0.01 and rms > 0.01:
                    begin = blocks[gap_start][0]
                    if 0.01 <= (offset - begin) / sr <= 0.5:
                        finding(
                            "silence_gap",
                            (first + begin) / sr,
                            (first + offset) / sr,
                            None,
                            {
                                "duration_seconds": (offset - begin) / sr,
                                "caveat": "Intentional rests and gates also qualify.",
                            },
                        )
                gap_start = None
            if i and rms > 0.001 and blocks[i - 1][2] > 0.001:
                change = 20 * math.log10(rms / blocks[i - 1][2])
                if abs(change) >= 12:
                    finding(
                        "level_jump",
                        (first + offset) / sr,
                        (first + offset + n) / sr,
                        None,
                        {
                            "rms_change_db": change,
                            "caveat": "Transients and phrase changes also qualify.",
                        },
                    )
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed during scan; discard results")
    db = lambda value: 20 * math.log10(value) if value > 0 else None
    return {
        "schema_version": 1,
        "status": "review" if counts else "no_findings_in_window",
        "source": {
            "path": str(path.resolve()),
            "size": before.st_size,
            "mtime_ns": before.st_mtime_ns,
        },
        "coverage": {
            "start_seconds": first / sr,
            "end_seconds": (first + frames) / sr,
            "source_duration_seconds": total / sr,
            "sample_rate": sr,
            "frames_analyzed": frames,
            "partial": first > 0 or first + frames < total,
            "timestamps": "source-file seconds, not Arrangement or warped playback time",
            "measurement": "Every decoded sample in the reported window; no audition.",
        },
        "channels": [
            dict(
                channel=ch + 1,
                sample_peak_dbfs=db(peaks[ch]),
                rms_dbfs=db(math.sqrt(squares[ch] / frames)),
                dc_offset=sums[ch] / frames,
                rail_samples=int(rails[ch]),
            )
            for ch in range(channels)
        ],
        "finding_counts": counts,
        "findings": sorted(findings, key=lambda f: f["start_seconds"]),
        "findings_limit_per_code": 24,
        "repair_recipes": {
            code: dict(RECIPES[code], settings_provenance="Original starting points, tune by ear")
            for code in counts
        },
        "not_assessed": [
            "LUFS or true peak",
            "hum/hiss spectrum",
            "stereo phase correlation",
            "aliasing",
            "separation artifacts",
            "pumping or gate causality",
            "post-device or warped playback audio",
        ],
        "next_step": "Audition flagged regions and choose a targeted repair on a copy. No audio or Live edits were made.",
    }
