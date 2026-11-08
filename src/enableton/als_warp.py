"""Offline warp-map injection into a saved .als file (gzip-compressed XML).

The Live Object Model exposes marker *reads* everywhere and marker rewrites only
through the extended bridge, so any bridge-side change needs Live restarted before
it can run. The saved set stores the same map as
``<WarpMarkers><WarpMarker Id SecTime BeatTime/></WarpMarkers>`` inside each
``<AudioClip>``, so a uniform map can also be written with Live closed.

Technique adapted from the community ``als_warp_injector`` (jhurliman/ableton-mcp
PR #1): decompress, replace the marker block of one clip matched by its ``Time``
attribute, recompress. This module adds guards that version does not have: it
refuses clips whose warp block it cannot see, never overwrites without a backup,
and re-reads the written file to verify the map.
"""

import gzip
import re
import shutil
import time
from pathlib import Path

TRACK = re.compile(r"<AudioTrack\b[^>]*>.*?</AudioTrack>", re.S)
CLIP = re.compile(r'<AudioClip\b[^>]*Time="([^"]+)"[^>]*>.*?</AudioClip>', re.S)
MARKERS = re.compile(r"<WarpMarkers>.*?</WarpMarkers>", re.S)
MARKER = re.compile(r"<WarpMarker\b([^/>]*)/>")
NAME = re.compile(r'<EffectiveName Value="([^"]*)"')
BOUNDS = {"CurrentStart": 0.0, "LoopStart": 0.0}


def read_set(path):
    """Return the decompressed XML text of a saved .als file."""
    return gzip.decompress(Path(path).read_bytes()).decode("utf-8")


def write_set(xml, path):
    Path(path).write_bytes(gzip.compress(xml.encode("utf-8")))


def _number(value):
    text = ("%.6f" % float(value)).rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def track_spans(xml):
    """Every AudioTrack with its byte span, so edits keep unrelated tracks intact."""
    spans = []
    for match in TRACK.finditer(xml):
        name = NAME.search(match.group(0))
        spans.append(
            {
                "name": name.group(1) if name else "",
                "start": match.start(),
                "end": match.end(),
                "body": match.group(0),
            }
        )
    return spans


def read_markers(clip_text):
    """Marker rows for one clip, or None when the clip carries no warp block."""
    block = MARKERS.search(clip_text)
    if block is None:
        return None
    rows = []
    for match in MARKER.finditer(block.group(0)):
        attrs = dict(re.findall(r'(\w+)="([^"]*)"', match.group(1)))
        rows.append(
            {
                "id": int(attrs.get("Id", len(rows))),
                "sec": float(attrs["SecTime"]),
                "beat": float(attrs["BeatTime"]),
            }
        )
    return rows


def uniform_markers(anchor_seconds, beats_per_second, source_seconds, step_seconds=0.0):
    """A straight map: ``anchor_seconds`` plays at beat 0, then one constant rate."""
    beats_per_second = float(beats_per_second)
    anchor_seconds = float(anchor_seconds)
    source_seconds = float(source_seconds)
    if not beats_per_second > 0:
        raise ValueError("beats_per_second must be positive")
    if not 0 <= anchor_seconds < source_seconds:
        raise ValueError("anchor_seconds must fall inside the source file")
    seconds = [anchor_seconds]
    if step_seconds and step_seconds > 0:
        point = anchor_seconds + step_seconds
        while point < source_seconds - step_seconds / 2:
            seconds.append(point)
            point += step_seconds
    seconds.append(source_seconds)
    return [
        {
            "id": index,
            "sec": round(sec, 6),
            "beat": round((sec - anchor_seconds) * beats_per_second, 6),
        }
        for index, sec in enumerate(seconds)
    ]


def render_markers(markers):
    lines = ["<WarpMarkers>"]
    for row in markers:
        lines.append(
            '  <WarpMarker Id="%d" SecTime="%s" BeatTime="%s" />'
            % (row["id"], _number(row["sec"]), _number(row["beat"]))
        )
    lines.append("</WarpMarkers>")
    return "\n".join(lines)


def update_bounds(clip_text, content_beats):
    """Point the visible clip section at the retimed span when those tags exist."""
    touched = []
    for tag, value in list(BOUNDS.items()) + [
        ("CurrentEnd", content_beats),
        ("LoopEnd", content_beats),
    ]:
        pattern = re.compile(r'(<%s Value=")([^"]*)(")' % tag)
        if pattern.search(clip_text):
            clip_text = pattern.sub(
                lambda m: m.group(1) + _number(value) + m.group(3), clip_text, 1
            )
            touched.append(tag)
    return clip_text, touched


def inject(
    xml,
    track_pattern,
    beats_per_second,
    source_seconds,
    anchor_seconds=0.0,
    step_seconds=0.0,
):
    """Rewrite the warp map of every AudioClip on tracks matching the pattern."""
    records = []
    result = xml
    for span in reversed(track_spans(xml)):
        if not re.search(track_pattern, span["name"], re.I):
            continue
        body = span["body"]
        patched_body = body
        for clip in reversed(list(CLIP.finditer(body))):
            clip_text = clip.group(0)
            before = read_markers(clip_text)
            entry = {"track": span["name"], "clip_time": clip.group(1)}
            if before is None:
                entry["status"] = "skipped: clip has no warp block"
                records.append(entry)
                continue
            after = uniform_markers(anchor_seconds, beats_per_second, source_seconds, step_seconds)
            block = render_markers(after)
            patched = MARKERS.sub(lambda _match: block, clip_text, count=1)
            patched, tags = update_bounds(patched, after[-1]["beat"])
            patched_body = patched_body[: clip.start()] + patched + patched_body[clip.end() :]
            entry.update(
                {
                    "status": "retimed",
                    "markers_before": len(before),
                    "first_before": before[0],
                    "last_before": before[-1],
                    "markers_after": len(after),
                    "first_after": after[0],
                    "last_after": after[-1],
                    "bounds_updated": tags,
                }
            )
            records.append(entry)
        if patched_body != body:
            result = result[: span["start"]] + patched_body + result[span["end"] :]
    return result, records


def inject_file(
    als_path,
    output_path,
    track_pattern,
    beats_per_second,
    source_seconds,
    anchor_seconds=0.0,
    step_seconds=0.0,
    dry_run=True,
):
    """Plan or write the retimed map; an in-place write is always backed up first."""
    als_path = Path(als_path)
    output_path = Path(output_path)
    xml = read_set(als_path)
    patched, records = inject(
        xml, track_pattern, beats_per_second, source_seconds, anchor_seconds, step_seconds
    )
    changed = [row for row in records if row["status"] == "retimed"]
    report = {
        "als": str(als_path),
        "dry_run": bool(dry_run),
        "clips": records,
        "changed": len(changed),
    }
    if dry_run or not changed:
        return report
    backup = None
    if output_path.resolve() == als_path.resolve():
        backup = als_path.with_name(als_path.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(als_path, backup)
    write_set(patched, output_path)
    written = read_set(output_path)
    verified = 0
    for row in changed:
        for span in track_spans(written):
            if span["name"] != row["track"]:
                continue
            for clip in CLIP.finditer(span["body"]):
                if clip.group(1) != row["clip_time"]:
                    continue
                rows = read_markers(clip.group(0)) or []
                expected = uniform_markers(
                    anchor_seconds, beats_per_second, source_seconds, step_seconds
                )
                if len(rows) == len(expected) and all(
                    abs(a["sec"] - b["sec"]) < 1e-4 and abs(a["beat"] - b["beat"]) < 1e-4
                    for a, b in zip(rows, expected)
                ):
                    verified += 1
    report.update(
        {
            "written": str(output_path),
            "backup": str(backup) if backup else None,
            "verified_clips": verified,
        }
    )
    if verified != len(changed):
        raise RuntimeError(
            "Wrote the set but readback verified %d of %d clips; restore %s"
            % (verified, len(changed), backup or als_path)
        )
    return report
