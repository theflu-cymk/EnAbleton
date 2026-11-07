"""Bounded sample-accurate audio assets and honest audio measurements.

Runs in a subprocess for MCP work. PyAV is already an upstream dependency.
"""

from array import array
from fractions import Fraction
import gc
import hashlib
import json
import math
from pathlib import Path
import sys
import wave

import av

from .warp_analysis import beat_to_source

MAX_SECONDS = 120
MAX_BYTES = 512 * 1024 * 1024


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def file_identity(path):
    path = Path(path).expanduser().resolve()
    before = path.stat()
    if not path.is_file() or before.st_size > MAX_BYTES:
        raise ValueError("Audio source must be a file <=512 MiB")
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Source changed while fingerprinting")
    return dict(
        path=str(path), size=after.st_size, mtime_ns=after.st_mtime_ns, sha256=h.hexdigest()
    )


def decode_window(path, start=0, duration=MAX_SECONDS):
    if not 0 <= start <= 1800 or not 0 < duration <= MAX_SECONDS:
        raise ValueError("Use a 0..1800 second start and a window <=120 seconds")
    # Count decoded samples rather than trusting compressed-container start PTS.
    # This matches the source sample coordinates used by the Live clip map.
    output = bytearray()
    position = 0
    with av.open(str(path)) as container:
        stream = container.streams.audio[0]
        sr = stream.codec_context.sample_rate
        channels = len(stream.codec_context.layout.channels)
        if channels not in [1, 2] or not 8000 <= sr <= 96000:
            raise ValueError("Mono/stereo sources at 8..96 kHz required")
        layout = "mono" if channels == 1 else "stereo"
        convert = av.AudioResampler(format="s16", layout=layout, rate=sr)
        begin = round(start * sr)
        end = round((start + duration) * sr)
        for frame in container.decode(audio=0):
            for block in convert.resample(frame):
                a = max(begin, position)
                b = min(end, position + block.samples)
                if b > a:
                    raw = bytes(block.planes[0])[: block.samples * channels * 2]
                    output.extend(
                        raw[(a - position) * channels * 2 : (b - position) * channels * 2]
                    )
                position += block.samples
            if position >= end:
                break
    expected = end - begin
    if len(output) // (channels * 2) < expected - 2:
        raise ValueError("Requested source window extends beyond available decoded audio")
    output = (output + bytes(expected * channels * 2))[: expected * channels * 2]
    values = array("h", output)
    if sys.byteorder != "little":
        values.byteswap()
    return values, sr, channels


def _frames(values, sr, channels):
    raw = values.tobytes()
    layout = "mono" if channels == 1 else "stereo"
    for i in range(0, len(values) // channels, 2048):
        n = min(2048, len(values) // channels - i)
        f = av.AudioFrame(format="s16", layout=layout, samples=n)
        f.sample_rate = sr
        f.time_base = Fraction(1, sr)
        f.pts = i
        f.planes[0].update(raw[i * channels * 2 : (i + n) * channels * 2])
        yield f


def stretch(values, sr, channels, target_frames):
    count = len(values) // channels
    if abs(count - target_frames) <= 1:
        return array("h", (values + array("h", [0] * channels))[: target_frames * channels])
    ratio = count / target_frames
    if not 0.25 <= ratio <= 4:
        raise ValueError("Source timing needs more than 4x stretch; choose another window")
    graph = av.filter.Graph()
    layout = "mono" if channels == 1 else "stereo"
    source = graph.add_abuffer(
        sample_rate=sr, format="s16", layout=layout, channels=channels, time_base=Fraction(1, sr)
    )
    tail = source
    while ratio > 2:
        node = graph.add("atempo", "2")
        tail.link_to(node)
        tail = node
        ratio /= 2
    while ratio < 0.5:
        node = graph.add("atempo", "0.5")
        tail.link_to(node)
        tail = node
        ratio /= 0.5
    node = graph.add("atempo", str(ratio))
    tail.link_to(node)
    sink = graph.add("abuffersink")
    node.link_to(sink)
    graph.configure()
    output = bytearray()
    resample = av.AudioResampler(format="s16", layout=layout, rate=sr)

    def drain():
        while True:
            try:
                frame = graph.pull()
            except (BlockingIOError, EOFError):
                break
            for block in resample.resample(frame):
                output.extend(bytes(block.planes[0])[: block.samples * channels * 2])

    for frame in _frames(values, sr, channels):
        graph.push(frame)
        drain()
    graph.push(None)
    drain()
    expected = target_frames * channels * 2
    # Filter latency can leave a short tail. Inputs use context padding below.
    output = (output + bytes(expected))[:expected]
    result = array("h", output)
    if sys.byteorder != "little":
        result.byteswap()
    return result


def write_wave(path, values, sr, channels):
    path = Path(path)
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = array("h", values)
    if sys.byteorder != "little":
        raw.byteswap()
    temporary = path.with_name(path.name + ".part")
    if temporary.exists():
        raise FileExistsError(temporary)
    try:
        with wave.open(str(temporary), "wb") as f:
            f.setparams((channels, 2, sr, 0, "NONE", "not compressed"))
            f.writeframes(raw.tobytes())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return str(path)


def fade_edges(values, sr, channels, milliseconds=5):
    count = len(values) // channels
    n = min(count // 2, max(1, round(milliseconds * sr / 1000)))
    for i in range(n):
        gain = math.sin(math.pi * i / (2 * n)) ** 2
        for ch in range(channels):
            values[i * channels + ch] = round(values[i * channels + ch] * gain)
            k = (count - i - 1) * channels + ch
            values[k] = round(values[k] * gain)


def aligned_source(binding, tempo, length_beats):
    timing = binding["timing"]
    spb = 60 / tempo
    if timing.get("pitch_coarse", 0) or timing.get("pitch_fine", 0):
        raise ValueError(
            "Bounce pitched source clips first; renderer will not silently discard clip tuning"
        )
    if binding.get("clip_gain", 0.4) != 0.4 and not math.isclose(
        binding.get("clip_gain", 0.4), 0.4, abs_tol=1e-6
    ):
        raise ValueError("Bounce non-unity clip gain before binding this source")
    start = binding["source_start"]
    warped = timing.get("warping", False)
    markers = timing.get("warp_markers", [])

    def source_seconds(beat):
        return beat_to_source(start + beat, markers) if warped else start + beat * spb

    # Split at actual Warp changes, not an assumed constant tempo.
    boundaries = {0.0, float(length_beats)}
    if warped:
        boundaries.update(
            m["beat_time"] - start for m in markers if start < m["beat_time"] < start + length_beats
        )
    ordered = sorted(boundaries)
    # Coalesce redundant linear anchors to avoid needless filter restarts.
    points = []
    for beat in ordered:
        sec = source_seconds(beat)
        if len(points) > 1:
            a, x = points[-2]
            b, y = points[-1]
            if abs((y - x) / (b - a) - (sec - y) / (beat - b)) < 1e-6:
                points.pop()
        points.append((beat, sec))
    if len(points) > 128:
        raise ValueError("Too many Warp segments; bounce this source before rendering")
    window_start = points[0][1]
    window_end = points[-1][1]
    if window_start < 0 or window_end <= window_start:
        raise ValueError("Invalid source range")
    with av.open(timing["file_path"]) as container:
        file_seconds = container.duration / av.time_base if container.duration else window_end
    origin = max(0, window_start - 0.2)
    limit = min(file_seconds, window_end + 0.2)
    values, sr, ch = decode_window(timing["file_path"], origin, limit - origin)
    total = round(length_beats * spb * sr)
    accumulation = array("f", [0]) * (total * ch)
    weights = array("f", [0]) * total
    overlap = max(1, round(0.005 * sr))
    for (beat, a), (nextbeat, b) in zip(points, points[1:]):
        first = round(beat * spb * sr)
        last = round(nextbeat * spb * sr)
        n = last - first
        if n < 2:
            raise ValueError("Warp markers are too dense to render safely")
        left = max(origin, a - 0.15)
        right = min(limit, b + 0.15)
        raw = values[round((left - origin) * sr) * ch : round((right - origin) * sr) * ch]
        factor = (b - a) / (n / sr)
        processed = stretch(raw, sr, ch, round(len(raw) / ch / factor))
        offset = round((a - left) / factor * sr)
        for dest in range(max(0, first - overlap), min(total, last + overlap)):
            position = offset + dest - first
            if not 0 <= position < len(processed) // ch:
                continue
            gain = 1.0
            if first > 0 and dest < first + overlap:
                gain *= math.sin((dest - first + overlap) / (2 * overlap) * math.pi / 2) ** 2
            if last < total and dest > last - overlap:
                gain *= math.cos((dest - last + overlap) / (2 * overlap) * math.pi / 2) ** 2
            weights[dest] += gain
            for channel in range(ch):
                accumulation[dest * ch + channel] += processed[position * ch + channel] * gain
    out = array("h")
    for i, w in enumerate(weights):
        if w < 1e-6:
            raise RuntimeError("Uncovered audio window; refusing a discontinuous render")
        for channel in range(ch):
            out.append(max(-32768, min(32767, round(accumulation[i * ch + channel] / w))))
    fade_edges(out, sr, ch, 5)
    return out, sr, ch


def activity_regions(values, sr, ch, tempo):
    step = max(1, round(0.02 * sr))
    frames = len(values) // ch
    blocks = []
    for start in range(0, frames, step):
        block = values[start * ch : min(frames, start + step) * ch]
        blocks.append(math.sqrt(sum(float(x) * x for x in block) / max(1, len(block))) / 32768)
    threshold = max(10 ** (-48 / 20), max(blocks, default=0) * 10 ** (-28 / 20))
    spans = []
    start = None
    for i, v in enumerate(blocks + [0]):
        if v >= threshold and start is None:
            start = i * step / sr
        if v < threshold and start is not None:
            end = min(frames / sr, i * step / sr)
            if end - start >= 0.08:
                a = max(0, start - 0.06)
                b = min(frames / sr, end + 0.1)
                if spans and a - spans[-1][1] < 0.15:
                    spans[-1][1] = b
                else:
                    spans.append([a, b])
            start = None
    return [dict(start=a * tempo / 60, end=b * tempo / 60) for a, b in spans[:256]]


def gain_curve(plan, sr, frames, role):
    s = plan["movement"]["settings"]
    bpf = plan["grid"]["tempo"] / 60 / sr
    floor = s["floor"]
    curve = array("f", [floor if role == "riff" else 1]) * frames
    if role == "riff":
        for pulse in plan["movement"]["pulses"]:
            start = pulse["time"] / bpf
            duration = pulse["duration"] / bpf
            attack = min(duration, s["attack_ms"] * sr / 1000)
            release = s["release_ms"] * sr / 1000
            for i in range(max(0, int(start)), min(frames, math.ceil(start + duration + release))):
                x = i - start
                if x < 0:
                    continue
                if x < attack:
                    g = math.sin(math.pi * x / (2 * attack)) ** 2
                elif x < duration:
                    g = 1
                else:
                    g = math.cos(math.pi * (x - duration) / (2 * release)) ** 2
                curve[i] = max(curve[i], floor + (1 - floor) * g)
        depth = 10 ** (-(3 + s["vocal_duck_db"]) / 20)
        for r in plan["config"]["vocal_regions"]:
            a = round(r["start"] / bpf)
            b = round(r["end"] / bpf)
            ramp = max(1, round(0.02 * sr))
            for i in range(max(0, a - ramp), min(frames, b + ramp)):
                t = min(1, max(0, (i - a + ramp) / ramp), max(0, (b + ramp - i) / ramp))
                curve[i] *= 1 - (1 - depth) * math.sin(t * math.pi / 2) ** 2
    if role == "rock_context":
        gap = round(s["transition_gap_beats"] / bpf)
        if gap:
            edge = max(0, frames - gap)
            ramp = max(1, round(0.005 * sr))
            for i in range(max(0, edge - ramp), edge):
                curve[i] *= math.cos((i - edge + ramp) / ramp * math.pi / 2) ** 2
            for i in range(edge, frames):
                curve[i] = 0
    return curve


def process_values(values, sr, ch, plan, role):
    values = array("h", values)
    frames = len(values) // ch
    gains = gain_curve(plan, sr, frames, role)
    for i, g in enumerate(gains):
        for c in range(ch):
            values[i * ch + c] = round(values[i * ch + c] * g)
    if role == "vocal" and plan["config"]["vocal_mode"] == "chops":
        source = array("h", values)
        for event in plan["arrangement"]["vocal_chops"]:
            a = round(event["start"] * 60 / plan["grid"]["tempo"] * sr)
            n = round((event["end"] - event["start"]) * 60 / plan["grid"]["tempo"] * sr)
            b = round(event["source_start"] * 60 / plan["grid"]["tempo"] * sr)
            piece = source[b * ch : (b + n) * ch]
            fade_edges(piece, sr, ch, 8)
            for j, v in enumerate(piece):
                if a * ch + j < len(values):
                    values[a * ch + j] = v
    fade_edges(values, sr, ch, plan["movement"]["boundary_fade_ms"])
    return values


def loudness(values, sr, ch):
    """FFmpeg loudnorm input analysis, not gain normalization."""
    old = av.logging.get_level()
    av.logging.set_level(av.logging.INFO)
    try:
        with av.logging.Capture() as logs:
            graph = av.filter.Graph()
            layout = "mono" if ch == 1 else "stereo"
            source = graph.add_abuffer(
                sample_rate=sr, format="s16", layout=layout, channels=ch, time_base=Fraction(1, sr)
            )
            node = graph.add("loudnorm", "I=-16:TP=-1:LRA=11:print_format=json")
            sink = graph.add("abuffersink")
            source.link_to(node)
            node.link_to(sink)
            graph.configure()

            def drain(active_graph=graph):
                while True:
                    try:
                        active_graph.pull()
                    except (BlockingIOError, EOFError):
                        break

            for f in _frames(values, sr, ch):
                graph.push(f)
                drain()
            graph.push(None)
            drain()
            del drain, source, node, sink, graph
            gc.collect()
        messages = "".join(row[2] for row in logs)
        start = messages.find("{")
        end = messages.rfind("}")
        if start < 0:
            raise RuntimeError("loudnorm analysis metadata unavailable")
        data = json.loads(messages[start : end + 1])

        def finite_number(key):
            v = float(data[key])
            return v if math.isfinite(v) else None

        return dict(
            integrated_lufs=finite_number("input_i"),
            true_peak_dbtp=finite_number("input_tp"),
            loudness_range_lu=finite_number("input_lra"),
            method="FFmpeg loudnorm input analysis",
        )
    except (ValueError, RuntimeError, av.error.FFmpegError) as error:
        return dict(
            integrated_lufs=None, true_peak_dbtp=None, method="unavailable", error=str(error)
        )
    finally:
        av.logging.set_level(old)


def measure(path):
    with av.open(str(path)) as c:
        duration = float(c.duration / av.time_base) if c.duration else None
    if duration is None or not 0 < duration <= MAX_SECONDS:
        raise ValueError("Measure an audio preview <=120 seconds")
    values, sr, ch = decode_window(path, 0, duration)
    frames = len(values) // ch
    peak = max((abs(v) for v in values), default=0) / 32768
    rms = math.sqrt(sum(float(v) * v for v in values) / max(1, len(values))) / 32768
    result = dict(
        seconds=frames / sr,
        frames=frames,
        sample_rate=sr,
        channels=ch,
        sample_peak_dbfs=20 * math.log10(peak) if peak else None,
        rms_dbfs=20 * math.log10(rms) if rms else None,
        **loudness(values, sr, ch),
    )
    if ch == 2:
        alpha = 1 - math.exp(-2 * math.pi * 80 / sr)
        l = r = ll = rr = lr = side = 0
        for i in range(frames):
            l += alpha * (values[2 * i] - l)
            r += alpha * (values[2 * i + 1] - r)
            ll += l * l
            rr += r * r
            lr += l * r
            side += ((l - r) / 2) ** 2
        result["low_band"] = dict(
            correlation=lr / math.sqrt(ll * rr) if ll * rr else None,
            side_energy_share=2 * side / (ll + rr) if ll + rr else None,
            method="80 Hz first-order low-pass approximation, not source separation",
        )
    return result


def compare(reference, variant, output_dir):
    root = Path(output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    reports = [measure(reference), measure(variant)]
    if abs(reports[0]["seconds"] - reports[1]["seconds"]) > 0.05:
        raise ValueError("A/B files must cover the same musical duration")
    use_lufs = all(x["integrated_lufs"] is not None for x in reports)
    levels = [x["integrated_lufs"] if use_lufs else x["rms_dbfs"] for x in reports]
    if any(v is None for v in levels):
        raise ValueError("Cannot loudness-match silence")
    target = min(levels)
    outputs = []
    for label, path, level in zip(["A", "B"], [reference, variant], levels):
        gain_db = target - level
        v, sr, ch = decode_window(path, 0, reports[len(outputs)]["seconds"])
        gain = 10 ** (gain_db / 20)
        for i in range(len(v)):
            v[i] = round(v[i] * gain)
        name = f"{label}-{digest(dict(source=file_identity(path), gain_db=gain_db))[:20]}.wav"
        dest = root / name
        if not dest.exists():
            write_wave(dest, v, sr, ch)
        outputs.append(dict(path=str(dest), gain_db=gain_db))
    return dict(
        reference=outputs[0],
        variant=outputs[1],
        measurements=reports,
        match_method="integrated LUFS" if use_lufs else "RMS fallback, not LUFS",
        target=target,
        limitation="Loudness matching does not establish musical preference",
    )
