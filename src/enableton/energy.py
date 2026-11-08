"""Measured per-sixteenth energy features for local PCM WAV files.

Dependency-free band split: one-pole low-pass filters run in series at each band
edge and the bands are formed by differencing adjacent outputs. Slopes are about
6 dB/octave per pole, so these are relative energy movements for mixing decisions,
not calibrated spectral power or LUFS. Unsupported formats fail explicitly.
"""

import math
from pathlib import Path
import statistics
import wave

from .numbers import finite

MAX_SECONDS = 120
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_SAMPLES = 8_000_000
BAND_EDGES = (60, 250, 500, 2000)
BAND_NAMES = ("sub", "bass", "low_mid", "high_mid", "high")
ANALYSIS_RATE = 11025


def _decode_mono(path, start_seconds, max_seconds):
    start_seconds = finite(start_seconds, "start_seconds")
    max_seconds = finite(max_seconds, "max_seconds")
    if start_seconds < 0 or not 0 < max_seconds <= MAX_SECONDS:
        raise ValueError("Invalid window; maximum 120 seconds")
    path = Path(path)
    if not path.is_absolute() or not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError("Need an existing absolute local audio file <=512 MiB")
    if path.suffix.lower() not in (".wav", ".wave"):
        raise ValueError("PCM WAV only; convert other formats explicitly first")
    with wave.open(str(path), "rb") as audio:
        sr = audio.getframerate()
        channels = audio.getnchannels()
        width = audio.getsampwidth()
        total = audio.getnframes()
        if not 8000 <= sr <= 192000 or not 1 <= channels <= 8 or width not in (1, 2, 3, 4):
            raise ValueError("Supported PCM: 8/16/24/32-bit, 8-192 kHz, 1-8 channels")
        first = round(start_seconds * sr)
        if first >= total:
            raise ValueError("Window begins after end of source")
        stride = max(1, sr // ANALYSIS_RATE)
        wanted = min(round(max_seconds * sr), total - first)
        audio.setpos(first)
        raw = audio.readframes(wanted)
        scale = 128.0 if width == 1 else float(2 ** (width * 8 - 1))
        samples = []
        frame_size = width * channels
        frames = len(raw) // frame_size
        for frame in range(0, frames, stride):
            offset = frame * frame_size
            total_value = 0.0
            for channel in range(channels):
                start = offset + channel * width
                if width == 1:
                    total_value += (raw[start] - 128) / scale
                else:
                    total_value += (
                        int.from_bytes(raw[start : start + width], "little", signed=True) / scale
                    )
            samples.append(total_value / channels)
    if len(samples) < 2:
        raise ValueError("Window contains too few samples")
    effective_rate = sr / stride
    return {
        "samples": samples,
        "rate": effective_rate,
        "source_sample_rate": sr,
        "analyzed_seconds": len(samples) / effective_rate,
        "window_start_seconds": first / sr,
        "partial": first > 0 or first + wanted < total,
    }


def _lowpass(samples, rate, cutoff):
    alpha = 1.0 - math.exp(-2.0 * math.pi * cutoff / rate)
    state = 0.0
    out = []
    for value in samples:
        state += alpha * (value - state)
        out.append(state)
    return out


def _normalize(series):
    peak = max((abs(value) for value in series), default=0.0)
    if peak < 1e-9:
        return [0.0] * len(series)
    return [value / peak for value in series]


def energy_series(path, bpm=120.0, start_seconds=0, max_seconds=30):
    """RMS, flux and five band envelopes per sixteenth note, each normalized 0..1."""
    bpm = finite(bpm, "bpm")
    if not 20 <= bpm <= 999:
        raise ValueError("bpm must be within 20..999")
    window = _decode_mono(path, start_seconds, max_seconds)
    samples, rate = window["samples"], window["rate"]
    if len(samples) > MAX_SAMPLES:
        raise ValueError("Window exceeds the analysis budget; shorten max_seconds")
    low = [_lowpass(samples, rate, edge) for edge in BAND_EDGES]
    bands = {
        BAND_NAMES[0]: low[0],
        BAND_NAMES[1]: [a - b for a, b in zip(low[1], low[0])],
        BAND_NAMES[2]: [a - b for a, b in zip(low[2], low[1])],
        BAND_NAMES[3]: [a - b for a, b in zip(low[3], low[2])],
        BAND_NAMES[4]: [s - y for s, y in zip(samples, low[3])],
    }
    block = 60.0 / bpm / 4.0
    per_block = max(1, round(block * rate))
    count = len(samples) // per_block
    if count < 2:
        raise ValueError("Window is shorter than two sixteenth notes")
    rms = []
    band_blocks = {name: [] for name in BAND_NAMES}
    for index in range(count):
        begin = index * per_block
        end = begin + per_block
        chunk = samples[begin:end]
        rms.append(math.sqrt(sum(value * value for value in chunk) / len(chunk)))
        for name in BAND_NAMES:
            part = bands[name][begin:end]
            band_blocks[name].append(math.sqrt(sum(value * value for value in part) / len(part)))
    flux = [0.0] + [max(0.0, rms[i] - rms[i - 1]) for i in range(1, len(rms))]
    track = samples[:: max(1, per_block // 24)]
    return {
        "bpm": bpm,
        "sixteenth_seconds": round(block, 6),
        "count": count,
        "times": [round(window["window_start_seconds"] + i * block, 6) for i in range(count)],
        "rms": [round(value, 6) for value in _normalize(rms)],
        "flux": [round(value, 6) for value in _normalize(flux)],
        "bands": {
            name: [round(value, 6) for value in _normalize(band_blocks[name])]
            for name in BAND_NAMES
        },
        "band_edges_hz": list(BAND_EDGES),
        "global_stats": {
            "median_rms": round(statistics.median(rms), 6),
            "peak_rms": round(max(rms), 6),
            "waveform_peak": round(max([abs(value) for value in track], default=0.0), 6),
        },
        "window": {
            "analyzed_seconds": round(window["analyzed_seconds"], 3),
            "partial": window["partial"],
            "sample_rate": window["source_sample_rate"],
        },
        "method": "one-pole band split, ~6 dB/octave slopes, normalized per feature",
        "limits": "Relative movement only: not LUFS, not calibrated spectrum, not a musical judgement",
    }


def band_clash(path_a, path_b, bpm=120.0, start_seconds=0, max_seconds=30, top=5):
    """Compare two files' band energy and suggest EQ Eight moves for the shared range."""
    if isinstance(top, bool) or not isinstance(top, int) or not 1 <= top <= 8:
        raise ValueError("top must be an integer 1..8")
    first = energy_series(path_a, bpm, start_seconds, max_seconds)
    second = energy_series(path_b, bpm, start_seconds, max_seconds)
    rows = []
    for index, name in enumerate(BAND_NAMES):
        mean_a = statistics.mean(first["bands"][name])
        mean_b = statistics.mean(second["bands"][name])
        centre = BAND_EDGES[index] if index == 0 else BAND_EDGES[index - 1]
        high = 20000 if index == len(BAND_NAMES) - 1 else BAND_EDGES[index]
        score = round(mean_a * mean_b, 4)
        rows.append(
            {
                "band": name,
                "eq_band": index + 1,
                "range_hz": [centre, high],
                "file_a_mean": round(mean_a, 4),
                "file_b_mean": round(mean_b, 4),
                "clash_score": score,
            }
        )
    rows.sort(key=lambda row: row["clash_score"], reverse=True)
    suggestions = [
        {
            "eq_band": row["eq_band"],
            "center_hz": round(
                math.sqrt(max(row["range_hz"][0], 20) * min(row["range_hz"][1], 20000))
            ),
            "suggested_action": "cut about %.1f dB on the busier source, Q about 1.0"
            % (2.0 + 2.0 * row["clash_score"]),
        }
        for row in rows[:top]
    ]
    return {
        "bands": rows,
        "suggestions": suggestions,
        "alignment": {
            "same_window": abs(
                first["window"]["analyzed_seconds"] - second["window"]["analyzed_seconds"]
            )
            < 0.05,
            "file_a": first["window"],
            "file_b": second["window"],
        },
        "method": "mean normalized band energy per file; the product ranks overlap",
        "limits": "Overlapping energy is not automatically a problem: arrangement and level decide. Audition first",
    }


def segment_plan(series, min_segment_sixteenths=32, threshold=0.12):
    """Split an energy series where its RMS level changes and hold each section long enough."""
    if not isinstance(series, dict) or "rms" not in series or "times" not in series:
        raise ValueError("series must come from energy_series")
    rms = [finite(value, "rms") for value in series["rms"]]
    times = [finite(value, "time") for value in series["times"]]
    if len(rms) != len(times) or len(rms) < 4:
        raise ValueError("Series is too short to segment")
    minimum = finite(min_segment_sixteenths, "min_segment_sixteenths")
    limit = finite(threshold, "threshold")
    if not 4 <= minimum <= 4096 or not 0 <= limit <= 1:
        raise ValueError("min_segment_sixteenths must be 4..4096 and threshold 0..1")
    step = times[1] - times[0]
    boundaries = [0]
    for index in range(1, len(rms)):
        if abs(rms[index] - rms[index - 1]) >= limit and index - boundaries[-1] >= minimum:
            boundaries.append(index)
    boundaries.append(len(rms))
    segments = []
    for start, end in zip(boundaries, boundaries[1:]):
        average = statistics.mean(rms[start:end])
        segments.append(
            {
                "start_seconds": round(times[start], 3),
                "end_seconds": round(times[end - 1] + step, 3),
                "start_beat": round(times[start] * float(series["bpm"]) / 60.0, 4),
                "length_sixteenths": end - start,
                "energy_class": "high" if average >= 0.6 else "mid" if average >= 0.3 else "low",
                "mean_rms": round(average, 4),
            }
        )
    return {
        "segments": segments,
        "count": len(segments),
        "method": "RMS change threshold with a minimum section length",
        "limits": "Boundaries are level changes, not proven song sections: confirm by listening",
    }
