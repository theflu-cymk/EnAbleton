"""Offline clip-envelope injection into a saved .als file.

Ported capability from the community ableton-mcp PR #1 (``als_automation_injector``):
a MIDI clip stores its automation as ``<ClipEnvelope>`` elements inside a nested
``<Envelopes><Envelopes>`` container, and a MIDI CC target is addressed by the ``Id``
of ``<ControllerTargets.N>`` in that track's ``<MidiControllers>``.

Changed from the original: clip time is matched exactly (the original truncated the
start beat to an int), times are clip-relative beats rather than absolute seconds,
a missing controller target raises instead of writing nothing, an existing envelope
for the same target is never duplicated silently, in-place writes are backed up, and
the written file is re-read and checked.
"""

import re
import shutil
import time
from pathlib import Path

from .als_warp import read_set, write_set
from .numbers import finite

ENERGY_CC = {
    "rms": 22,
    "centroid": 23,
    "flux": 24,
    "band_sub": 25,
    "band_bass": 26,
    "band_low_mid": 27,
    "band_high_mid": 28,
    "band_high": 29,
}
INITIAL_EVENT_TIME = -63072000
MAX_POINTS = 2048

TRACK = re.compile(r"<MidiTrack\b[^>]*>.*?</MidiTrack>", re.S)
CLIP = re.compile(r'<MidiClip\b[^>]*Time="([^"]+)"[^>]*>.*?</MidiClip>', re.S)
CLIP_START = re.compile(r'<MidiClip\b[^>]*Time="([^"]+)"')
CONTROLLERS = re.compile(r"<MidiControllers>.*?</MidiControllers>", re.S)
TARGET = re.compile(r'<ControllerTargets\.(\d+)\s[^>]*Id="([^"]*)"')
NAME = re.compile(r'<EffectiveName Value="([^"]*)"')
POINTEE = re.compile(r'<PointeeId Value="([^"]*)"')
ENVELOPE = re.compile(r"<ClipEnvelope\b.*?</ClipEnvelope>", re.S)
EVENTS = re.compile(r"<Events>.*?</Events>", re.S)

FALLBACK_TEMPLATE = """<ClipEnvelope Id="{id}">
  <EnvelopeTarget>
    <PointeeId Value="{pointee}" />
  </EnvelopeTarget>
  <Automation>
    <Events>{events}</Events>
    <AutomationTransformViewState>
      <IsTransformPending Value="false" />
      <TimeAndValueTransforms />
    </AutomationTransformViewState>
  </Automation>
  <ScrollerTimePreserver>
    <LeftTime Value="0" />
    <RightTime Value="{length}" />
  </ScrollerTimePreserver>
</ClipEnvelope>"""


def _number(value):
    text = ("%.6f" % float(value)).rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def _same_time(text, clip_time):
    try:
        return abs(float(text) - clip_time) < 1e-6
    except (TypeError, ValueError):
        return False


def midi_tracks(xml):
    """Every MIDI track with its span, so unrelated tracks stay byte-identical."""
    rows = []
    for match in TRACK.finditer(xml):
        name = NAME.search(match.group(0))
        rows.append(
            {
                "name": name.group(1) if name else "",
                "start": match.start(),
                "end": match.end(),
                "body": match.group(0),
            }
        )
    return rows


def controller_ids(track_body):
    """Map MIDI CC number to the PointeeId this set uses for that controller."""
    block = CONTROLLERS.search(track_body)
    if block is None:
        return {}
    return {int(cc): ident for cc, ident in TARGET.findall(block.group(0))}


def envelope_template(xml, track_body=None):
    """Reuse a real ClipEnvelope from this set so the element shape matches Live's."""
    bodies = [track_body] if track_body else []
    bodies += [row["body"] for row in midi_tracks(xml)]
    for body in bodies:
        if body:
            match = ENVELOPE.search(body)
            if match:
                return match.group(0)
    return None


def render_envelope(envelope_id, pointee, points, length, template=None):
    """One ClipEnvelope with a leading initial-value event and clip-relative beats."""
    events = [
        '<FloatEvent Id="0" Time="%d" Value="%s" />'
        % (INITIAL_EVENT_TIME, _number(points[0][1] * 127.0))
    ]
    for index, (beat, value) in enumerate(points):
        events.append(
            '<FloatEvent Id="%d" Time="%s" Value="%s" />'
            % (index + 1, _number(beat), _number(value * 127.0))
        )
    events_xml = "\n".join(events)
    if not template:
        return FALLBACK_TEMPLATE.format(
            id=envelope_id, pointee=pointee, events=events_xml, length=_number(length)
        )
    text = EVENTS.sub(lambda _m: "<Events>%s</Events>" % events_xml, template, count=1)
    text = POINTEE.sub(lambda m: '<PointeeId Value="%s"' % pointee, text, count=1)
    text = re.sub(
        r'(<ClipEnvelope\b[^>]*\bId=")[^"]*(")',
        lambda m: m.group(1) + str(envelope_id) + m.group(2),
        text,
        count=1,
    )
    text = re.sub(
        r'(<RightTime Value=")[^"]*(")',
        lambda m: m.group(1) + _number(length) + m.group(2),
        text,
        count=1,
    )
    return text


def _insert(clip_text, block):
    """Place the envelope in the inner container, matching the shapes Live writes."""
    nested = re.search(r"<Envelopes>\s*<Envelopes>", clip_text)
    if nested is not None:
        inner = re.search(r"<Envelopes>\s*<Envelopes>.*?</Envelopes>", clip_text, re.S)
        if inner is not None:
            span = inner.group(0)
            patched = (
                span[: span.rfind("</Envelopes>")]
                + block
                + "\n"
                + span[span.rfind("</Envelopes>") :]
            )
            return clip_text[: inner.start()] + patched + clip_text[inner.end() :]
    empty_pair = re.search(r"<Envelopes>\s*<Envelopes\s*/>\s*</Envelopes>", clip_text)
    if empty_pair is not None:
        return (
            clip_text[: empty_pair.start()]
            + "<Envelopes><Envelopes>%s</Envelopes></Envelopes>" % block
            + clip_text[empty_pair.end() :]
        )
    empty_outer = re.search(r"<Envelopes\s*/>", clip_text)
    if empty_outer is not None:
        return (
            clip_text[: empty_outer.start()]
            + "<Envelopes><Envelopes>%s</Envelopes></Envelopes>" % block
            + clip_text[empty_outer.end() :]
        )
    single = re.search(r"<Envelopes>.*?</Envelopes>", clip_text, re.S)
    if single is not None:
        span = single.group(0)
        patched = (
            span[: span.rfind("</Envelopes>")]
            + "<Envelopes>%s</Envelopes>" % block
            + span[span.rfind("</Envelopes>") :]
        )
        return clip_text[: single.start()] + patched + clip_text[single.end() :]
    closing = clip_text.rfind("</MidiClip>")
    if closing < 0:
        raise ValueError("Clip block has no closing tag")
    return (
        clip_text[:closing]
        + "<Envelopes><Envelopes>%s</Envelopes></Envelopes>" % block
        + clip_text[closing:]
    )


def _clip_span(track_body, clip_time):
    for match in CLIP.finditer(track_body):
        if _same_time(match.group(1), clip_time):
            return match
    return None


def inject(xml, track_pattern, clip_time, cc, points, replace=False):
    """Write one MIDI CC envelope into one clip; returns the new XML and a report."""
    clip_time = finite(clip_time, "clip_time")
    if isinstance(cc, bool) or not isinstance(cc, int) or not 0 <= cc <= 127:
        raise ValueError("cc must be an integer 0..127")
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
        raise ValueError("points must hold 1..2048 entries")
    clean = []
    for row in points:
        if not isinstance(row, dict):
            raise ValueError("Each point needs time and value")
        beat = finite(row.get("time"), "point time")
        value = finite(row.get("value"), "point value")
        if beat < 0:
            raise ValueError("Point times are clip-relative beats and cannot be negative")
        if not 0 <= value <= 1:
            raise ValueError("Point values must be normalized 0..1")
        if clean and beat <= clean[-1][0]:
            raise ValueError("Point times must strictly increase")
        clean.append((beat, value))
    matches = [row for row in midi_tracks(xml) if re.search(track_pattern, row["name"], re.I)]
    if not matches:
        raise ValueError("No MIDI track matches " + repr(track_pattern))
    if len(matches) > 1:
        raise ValueError(
            "Pattern matches several MIDI tracks: " + ", ".join(row["name"] for row in matches)
        )
    track = matches[0]
    pointee = controller_ids(track["body"]).get(cc)
    if pointee is None:
        raise ValueError(
            "This track has no ControllerTargets.%d; create the MIDI track in Live first so the "
            "set contains that controller" % cc
        )
    clip = _clip_span(track["body"], clip_time)
    if clip is None:
        raise ValueError("No MIDI clip starts at beat " + _number(clip_time) + " on that track")
    clip_text = clip.group(0)
    existing = [row for row in ENVELOPE.findall(clip_text) if porow(row) == pointee]
    if existing and not replace:
        raise ValueError("This target already has an envelope; inspect it and pass replace=true")
    body = clip_text
    if existing:
        for row in existing:
            body = body.replace(row, "", 1)
    template = envelope_template(xml, track["body"])
    block = render_envelope(0, pointee, clean, clean[-1][0], template)
    patched = _insert(body, block)
    report = {
        "track": track["name"],
        "clip_time": clip_time,
        "cc": cc,
        "pointee_id": pointee,
        "points": len(clean),
        "replaced": bool(existing),
        "template": "existing ClipEnvelope in this set" if template else "built-in fallback",
    }
    return xml[: track["start"]] + track["body"].replace(clip_text, patched, 1) + xml[
        track["end"] :
    ], report


def porow(envelope_text):
    match = POINTEE.search(envelope_text)
    return match.group(1) if match else None


def inject_file(
    als_path,
    track_pattern,
    clip_time,
    cc,
    points,
    output_path=None,
    replace=False,
    dry_run=True,
):
    """Plan or write the envelope; an in-place write is always backed up and re-read."""
    als_path = Path(als_path)
    output_path = Path(output_path) if output_path else als_path
    xml = read_set(als_path)
    patched, report = inject(xml, track_pattern, clip_time, cc, points, replace)
    report.update({"als": str(als_path), "dry_run": bool(dry_run)})
    if dry_run:
        return report
    backup = None
    if output_path.resolve() == als_path.resolve():
        backup = als_path.with_name(als_path.name + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
        shutil.copy2(als_path, backup)
    write_set(patched, output_path)
    reread = read_set(output_path)
    found = 0
    for track in midi_tracks(reread):
        if track["name"] != report["track"]:
            continue
        clip = _clip_span(track["body"], report["clip_time"])
        if clip is None:
            continue
        found = sum(
            1 for row in ENVELOPE.findall(clip.group(0)) if porow(row) == report["pointee_id"]
        )
    report["written"] = str(output_path)
    report["backup"] = str(backup) if backup else None
    report["envelopes_for_target"] = found
    if found != 1:
        raise RuntimeError(
            "Wrote the set but readback found %d envelopes for this target; restore %s"
            % (found, backup or als_path)
        )
    return report
