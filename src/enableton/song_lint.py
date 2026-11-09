"""Read-only Live-set linting, structured findings and narrowly guarded metadata fixes."""

from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from uuid import uuid4
from time import perf_counter

from .live_reads import read_many

RULES = {}
SEVERITY = {"info": 0, "warning": 1, "error": 2}
DEFAULT_COLORS = {
    "drums": 6,
    "bass": 20,
    "vocals": 11,
    "synth": 8,
    "piano": 8,
    "chords": 8,
    "guitar": 1,
    "source": 13,
    "reference": 13,
    "print": 14,
    "group": 13,
    "fx": 9,
    "loops": 6,
    "utility": 13,
}


def rule(name, severity="warning"):
    def decorate(fn):
        RULES[name] = (fn, severity)
        return fn

    return decorate


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=True).encode()
    ).hexdigest()


def role_for(info):
    prefix = info["name"].split("|")[0].strip().upper()
    mapping = {
        "SRC": "source",
        "REF": "reference",
        "BASS": "bass",
        "DRUMS": "drums",
        "GTR": "guitar",
        "KEYS": "piano",
        "HARM": "chords",
        "VOX": "vocals",
        "VOCALS": "vocals",
        "SYNTH": "synth",
        "GROUP": "group",
        "STEMS": "group",
        "PRINT": "print",
        "FX": "fx",
        "LOOPS": "loops",
        "UTIL": "utility",
    }
    if prefix in mapping:
        return mapping[prefix]
    name = info["name"].lower()
    for token, role in [
        ("bass", "bass"),
        ("drum", "drums"),
        ("vocal", "vocals"),
        ("piano", "piano"),
        ("guitar", "guitar"),
    ]:
        if token in name:
            return role
    return "midi" if info.get("is_midi_track") else "audio"


def collect_live(connection=None, include_session=False, track_indices=None):
    """Only documented read commands; never treats a failed read as an empty object."""
    from .wire import install as install_wire

    install_wire()
    if connection is None:
        from ableton_live_mcp.connection import get_ableton_connection

        connection = get_ableton_connection()
    metrics = {"roundTrips": 0, "bridgeSeconds": 0.0}

    def call(kind, params):
        started = perf_counter()
        metrics["roundTrips"] += 1
        try:
            return connection.send_command(kind, params)
        finally:
            metrics["bridgeSeconds"] += perf_counter() - started

    session = call("get_session_info", {})
    state = {
        "capturedAt": datetime.now(timezone.utc).isoformat(),
        "source": "live",
        "session": {
            "tempo": session["tempo"],
            "numerator": session["signature_numerator"],
            "denominator": session["signature_denominator"],
            "is_playing": session["is_playing"],
            "recording": session.get("record_mode"),
            "reported_length_beats": session.get("song_length"),
        },
        "tracks": [],
        "capture_errors": [],
        "includeSession": include_session,
        "limitations": [
            "Plug-in sound quality and opaque state are not assessed.",
            "Automation and full routing are not fully exposed; group metadata is captured where supported.",
            "Capture-local IDs must be re-resolved before applying a saved plan.",
        ],
    }
    indices = list(range(session["track_count"])) if track_indices is None else list(track_indices)
    if len(indices) != len(set(indices)) or any(
        type(i) is not int or not 0 <= i < session["track_count"] for i in indices
    ):
        raise ValueError("Track indices must be unique existing integer positions")
    state["capture_scope"] = {"track_indices": indices, "full_set": track_indices is None}
    infos = []
    commands = [{"type": "get_track_info", "params": {"track_index": i}} for i in indices]
    for i, (info, error) in zip(indices, read_many(call, commands)):
        if error is None:
            infos.append(info)
        else:
            state["capture_errors"].append(
                {"target": f"track:{i}", "operation": "get_track_info", "error": str(error)}
            )
    group_reads = read_many(
        call,
        [{"type": "get_group_info", "params": {"track_index": info["index"]}} for info in infos],
    )
    arrangement_infos = [
        info
        for info, (g, error) in zip(infos, group_reads)
        if error is not None or not g["is_foldable"]
    ]
    arrangement_reads = dict(
        zip(
            (info["index"] for info in arrangement_infos),
            read_many(
                call,
                [
                    {"type": "get_arrangement_clips", "params": {"track_index": info["index"]}}
                    for info in arrangement_infos
                ],
            ),
        )
    )
    tasks = []
    for info, (grouping, group_error) in zip(infos, group_reads):
        i = info["index"]
        group = (
            bool(grouping["is_foldable"])
            if group_error is None
            else bool(info.get("is_foldable", False))
        )
        track = {
            "id": f"track:{i}",
            "index": i,
            "name": info["name"],
            "role": "group" if group else role_for(info),
            "type": "group" if group else "midi" if info["is_midi_track"] else "audio",
            "is_group": group,
            "group_name": grouping.get("group_track") if grouping else None,
            "group_read_complete": grouping is not None,
            "is_return": False,
            "is_master": False,
            "devices": info.get("devices", []),
            "color_index": info.get("color_index"),
            "mute": info.get("mute"),
            "armed": info.get("arm"),
            "has_session_clips": any(s["has_clip"] for s in info["clip_slots"]),
            "has_automation": None,
            "live_input": None,
            "clips": [],
        }
        state["tracks"].append(track)
        if group:
            continue
        arrangement_result, error = arrangement_reads[i]
        if error is not None:
            if "Main, Group and Return Tracks" in str(error):
                track.update(is_group=True, type="group", role="group")
                continue
            state["capture_errors"].append(
                {"target": track["id"], "operation": "get_arrangement_clips", "error": str(error)}
            )
            continue
        arrangement = arrangement_result["clips"]
        locations = [("arrangement", j, c) for j, c in enumerate(arrangement)]
        if include_session:
            locations += [
                ("session", s["index"], s["clip"]) for s in info["clip_slots"] if s["has_clip"]
            ]
        for view, j, summary in locations:
            audio = track["type"] == "audio"
            locator = dict(
                track_index=i,
                clip_index=j,
                clip_view=view,
                expected_track_name=info["name"],
                expected_clip_name=summary["name"],
            )
            if view == "arrangement":
                locator["expected_start_time"] = summary["start_time"]
            clip = {
                "id": f"track:{i}:{view}:{j}",
                "name": summary["name"],
                "view": view,
                "type": "audio" if audio else "midi",
                "locator": locator,
                "start_beats": summary.get("start_time", 0),
                "end_beats": summary.get("end_time"),
                "read_complete": False,
                "protected": view == "session" and summary["name"].upper().startswith("ORIGINAL"),
            }
            track["clips"].append(clip)
            tasks.append((clip, "get_audio_clip_timing" if audio else "get_access_notes", locator))
    detail_reads = read_many(call, [{"type": kind, "params": params} for _, kind, params in tasks])
    for (clip, kind, _), (details, error) in zip(tasks, detail_reads):
        if error is not None:
            state["capture_errors"].append(
                {"target": clip["id"], "operation": kind, "error": str(error)}
            )
        if details is None:
            continue
        clip["read_complete"] = True
        clip["loop_start"] = details.get("loop_start")
        clip["loop_end"] = details.get("loop_end")
        if clip["type"] == "audio":
            path = details["file_path"]
            clip.update(
                audio_path=path,
                file_exists=bool(path) and Path(path).is_file(),
                sample_frames=details.get("sample_length"),
                sample_rate=details.get("sample_rate"),
                warping=details["warping"],
                warp_mode=details["warp_mode"],
                warp_markers=details["warp_markers"],
                start_marker=details.get("start_marker"),
                pitch_coarse=details.get("pitch_coarse"),
                pitch_fine=details.get("pitch_fine"),
                clip_identity=details.get("clip_identity"),
            )
        else:
            clip["notes"] = details["notes"]
        clip["state_fingerprint"] = fingerprint(
            {k: v for k, v in clip.items() if k != "state_fingerprint"}
        )
    # Keep independent freshness checks, but amortize their transport overhead.
    checks = []
    owners = []
    for track in state["tracks"]:
        checks.append({"type": "get_track_info", "params": {"track_index": track["index"]}})
        owners.append((track, "track"))
        if not track["is_group"]:
            checks.append(
                {"type": "get_arrangement_clips", "params": {"track_index": track["index"]}}
            )
            owners.append((track, "arrangement"))
    for (track, kind), (fresh, error) in zip(owners, read_many(call, checks)):
        if error is None:
            if kind == "track" and fresh["name"] != track["name"]:
                error = ValueError("Track changed while capturing")
            elif kind == "arrangement":
                now = [(c["name"], c["start_time"], c["end_time"]) for c in fresh["clips"]]
                prior = [
                    (c["name"], c["start_beats"], c["end_beats"])
                    for c in track["clips"]
                    if c["view"] == "arrangement"
                ]
                if now != prior:
                    error = ValueError("Arrangement changed while capturing")
        if error is not None:
            state["capture_errors"].append(
                {"target": track["id"], "operation": "capture_consistency", "error": str(error)}
            )
    state["capture_metrics"] = metrics
    state["capture_fingerprint"] = fingerprint(
        {"session": state["session"], "tracks": state["tracks"]}
    )
    return state


def eligible(state):
    for track in state.get("tracks", []):
        if track.get("is_master") or track.get("is_return"):
            continue
        for clip in track.get("clips", []):
            if not clip.get("protected"):
                yield track, clip


def midi_clips(state):
    for track, clip in eligible(state):
        if clip["type"] == "midi" and "notes" in clip and clip.get("read_complete", True):
            yield track, clip


def active(notes):
    return [n for n in notes if not n.get("mute")]


def finding(
    code, severity, track, clip, message, *, evidence=None, fix=None, confidence="measured"
):
    return {
        "code": code,
        "severity": severity,
        "track": {"id": track["id"], "name": track["name"]},
        "clip": {
            "id": clip["id"],
            "name": clip["name"],
            "view": clip.get("view"),
            "start_beats": clip.get("start_beats")
            if isinstance(clip.get("start_beats"), (int, float))
            and math.isfinite(clip["start_beats"])
            else None,
        }
        if clip
        else None,
        "message": message,
        "confidence": confidence,
        "evidence": evidence or {},
        "fix": fix,
        "autofixable": fix is not None,
    }


def metadata_fix(track, clip, patch):
    # Only harmless allowlisted metadata writes are implemented; no hidden MIDI writer.
    return {
        "kind": "set_clip" if clip else "set_track",
        "track_index": track.get("index"),
        "expected_track_name": track["name"],
        "locator": clip.get("locator") if clip else None,
        "patch": patch,
    }


def default_name(name):
    return not name.strip() or bool(
        re.fullmatch(
            r"(?:\d+[- ]?)?(?:Audio(?: Track)?|MIDI(?: Clip)?|Track(?:\s*\d+)?|Group)",
            name.strip(),
            re.I,
        )
    )


@rule("track_naming")
def names(state, params):
    output = []
    counts = Counter(t["name"] for t in state.get("tracks", []))
    for t in state.get("tracks", []):
        if default_name(t["name"]):
            device = next(
                (d["name"] if isinstance(d, dict) else d for d in t.get("devices", [])), None
            )
            role = t.get("role", t["type"])
            label = device or "Unassigned"
            new = f"{role.upper()} | {label} {t.get('index', 0) + 1:02d}"
            output.append(
                finding(
                    "TRACK_DEFAULT_NAME",
                    "warning",
                    t,
                    None,
                    "Track name does not identify its content.",
                    fix=metadata_fix(t, None, {"name": new}) if t["name"] else None,
                )
            )
        if counts[t["name"]] > 1:
            output.append(
                finding(
                    "TRACK_DUPLICATE_NAME",
                    "warning",
                    t,
                    None,
                    "Duplicate track name makes targeting ambiguous.",
                )
            )
    return output


@rule("clip_naming", "info")
def clip_names(state, params):
    output = []
    for t, c in eligible(state):
        if default_name(c["name"]):
            bpm = state.get("session", {}).get("tempo", "unknown")
            label = f"{t.get('role', t['type']).title()} | {bpm} BPM | {c['type'].upper()}"
            output.append(
                finding(
                    "CLIP_DEFAULT_NAME",
                    "info",
                    t,
                    c,
                    "Clip uses a generic default name.",
                    fix=metadata_fix(t, c, {"name": label}) if c["name"] and t["name"] else None,
                    evidence={"fix_requires": "Empty-name-capable guarded writer"}
                    if not c["name"]
                    else None,
                )
            )
    return output


@rule("missing_samples", "error")
def missing(state, params):
    output = []
    for t, c in eligible(state):
        if c["type"] != "audio" or not c.get("read_complete", True):
            continue
        exists = c.get("file_exists")
        if exists is None:
            exists = bool(c.get("audio_path")) and Path(c["audio_path"]).is_file()
        if not exists:
            output.append(
                finding(
                    "AUDIO_MISSING",
                    "error",
                    t,
                    c,
                    "Referenced audio cannot be found.",
                    evidence={"path": c.get("audio_path")},
                )
            )
    return output


@rule("midi_validity", "error")
def midi_validity(state, params):
    output = []
    for t, c in midi_clips(state):
        invalid = []
        for i, n in enumerate(c["notes"]):
            try:
                valid = (
                    type(n["pitch"]) is int
                    and 0 <= n["pitch"] <= 127
                    and math.isfinite(n["start_time"])
                    and math.isfinite(n["duration"])
                    and n["duration"] > 0
                    and math.isfinite(n["velocity"])
                    and 1 <= n["velocity"] <= 127
                )
            except (KeyError, TypeError, ValueError):
                valid = False
            if not valid:
                invalid.append(n.get("note_id", i))
        if invalid:
            output.append(
                finding(
                    "MIDI_INVALID_NOTES",
                    "error",
                    t,
                    c,
                    "MIDI has invalid pitch/time/duration/velocity values.",
                    evidence={"count": len(invalid), "note_ids": invalid[:30]},
                )
            )
    return output


@rule("midi_overlaps")
def overlaps(state, params):
    output = []
    for t, c in midi_clips(state):
        groups = defaultdict(list)
        mono = t.get("role") in params.get("monophonicRoles", ["bass"]) or t["id"] in params.get(
            "monophonicTrackIds", []
        )
        for n in active(c["notes"]):
            groups[0 if mono else n["pitch"]].append(n)
        collisions = []
        for ns in groups.values():
            previous = None
            for note in sorted(ns, key=lambda n: n["start_time"]):
                if (
                    previous
                    and previous["start_time"] + previous["duration"] > note["start_time"] + 0.005
                ):
                    collisions.append(
                        {
                            "previous": previous.get("note_id"),
                            "next": note.get("note_id"),
                            "at_beat": note["start_time"],
                        }
                    )
                if (
                    previous is None
                    or note["start_time"] + note["duration"]
                    > previous["start_time"] + previous["duration"]
                ):
                    previous = note
        if collisions:
            output.append(
                finding(
                    "MIDI_MONO_OVERLAP" if mono else "MIDI_SAME_PITCH_OVERLAP",
                    "warning",
                    t,
                    c,
                    "Overlapping bass voices."
                    if mono
                    else "Same-pitch notes overlap; ordinary chord polyphony is preserved.",
                    evidence={
                        "count": len(collisions),
                        "examples": collisions[:15],
                        "fix_requires": "Verified MIDI replacement helper preserving automation, loop offsets and originals",
                    },
                )
            )
    return output


@rule("midi_grid", "info")
def grid(state, params):
    step = params.get("gridBeats", 0.25)
    tolerance = params.get("toleranceBeats", 0.04)
    if (
        not isinstance(step, (int, float))
        or isinstance(step, bool)
        or not math.isfinite(step)
        or step <= 0
    ):
        raise ValueError("midi_grid.gridBeats must be positive and finite")
    if not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("midi_grid.toleranceBeats must be non-negative and finite")
    output = []
    for t, c in midi_clips(state):
        errors = [
            abs(n["start_time"] - round(n["start_time"] / step) * step)
            for n in active(c["notes"])
            if math.isfinite(n.get("start_time", math.nan))
        ]
        bad = [x for x in errors if x > tolerance]
        if bad:
            output.append(
                finding(
                    "MIDI_OFF_GRID",
                    "info",
                    t,
                    c,
                    "Some starts fall outside the configured grid tolerance; swing/pickups may be intentional.",
                    evidence={
                        "count": len(bad),
                        "grid_beats": step,
                        "tolerance_beats": tolerance,
                        "max_deviation_beats": max(bad),
                    },
                    confidence="heuristic",
                )
            )
    return output


@rule("midi_dynamics")
def dynamics(state, params):
    output = []
    for t, c in midi_clips(state):
        notes = active(c["notes"])
        if len(notes) >= 8 and sum(n["velocity"] == 127 for n in notes) / len(notes) >= 0.9:
            output.append(
                finding(
                    "MIDI_MAX_VELOCITY",
                    "warning",
                    t,
                    c,
                    "At least 90% of notes are at maximum velocity; review dynamics before layering.",
                    evidence={"notes": len(notes)},
                    confidence="heuristic",
                )
            )
    return output


@rule("empty_content", "info")
def empty(state, params):
    output = []
    for t in state.get("tracks", []):
        if (
            not t.get("is_group")
            and not t.get("is_return")
            and not t.get("is_master")
            and not t.get("clips")
            and not t.get("devices")
            and not t.get("has_session_clips")
        ):
            output.append(
                finding(
                    "TRACK_POSSIBLY_UNUSED",
                    "info",
                    t,
                    None,
                    "No clips or devices; automation/live-input use must be checked before deletion.",
                )
            )
    for t, c in eligible(state):
        if c["type"] == "midi" and "notes" in c and not c["notes"]:
            output.append(
                finding(
                    "MIDI_EMPTY_CLIP",
                    "info",
                    t,
                    c,
                    "Clip has no notes; it may still carry automation.",
                )
            )
        if c["type"] == "audio" and c.get("sample_frames") == 0:
            output.append(finding("AUDIO_ZERO_LENGTH", "warning", t, c, "Audio has zero frames."))
    return output


@rule("clip_boundaries", "info")
def boundaries(state, params):
    session = state.get("session", {})
    bar = session.get("numerator", 4) * 4 / session.get("denominator", 4)
    output = []
    for t, c in eligible(state):
        start, end = c.get("start_beats"), c.get("end_beats")
        if c.get("view") != "arrangement" or start is None or end is None:
            continue
        if not all(math.isfinite(v) for v in [start, end]) or end <= start:
            output.append(
                finding("CLIP_INVALID_RANGE", "error", t, c, "Clip has an invalid timeline range.")
            )
        elif abs(end - round(end / bar) * bar) > params.get("toleranceBeats", 0.04):
            output.append(
                finding(
                    "CLIP_NON_BAR_END",
                    "info",
                    t,
                    c,
                    "Clip ends between bar boundaries; tails, source lengths and edits can be intentional.",
                    confidence="heuristic",
                )
            )
    return output


@rule("arrangement_overlaps")
def arrangement_overlaps(state, params):
    output = []
    for t in state.get("tracks", []):
        cs = sorted(
            (
                c
                for c in t.get("clips", [])
                if c.get("view") == "arrangement" and c.get("end_beats") is not None
            ),
            key=lambda c: c["start_beats"],
        )
        furthest = None
        for c in cs:
            if furthest and c["start_beats"] < furthest["end_beats"] - 0.001:
                output.append(
                    finding(
                        "ARRANGEMENT_OVERLAP",
                        "warning",
                        t,
                        c,
                        "Same-track Arrangement clips overlap.",
                        evidence={"other_clip": furthest["id"]},
                    )
                )
            if furthest is None or c["end_beats"] > furthest["end_beats"]:
                furthest = c
    return output


@rule("warp_maps")
def warp_maps(state, params):
    output = []
    for t, c in eligible(state):
        if c["type"] != "audio" or not c.get("warping"):
            continue
        markers = c.get("warp_markers", [])
        invalid = any(
            b["beat_time"] <= a["beat_time"] or b["sample_time"] <= a["sample_time"]
            for a, b in zip(markers, markers[1:])
        )
        if invalid:
            output.append(
                finding(
                    "WARP_NON_MONOTONIC",
                    "error",
                    t,
                    c,
                    "Warp coordinates are not strictly increasing.",
                )
            )
        label = re.search(r"(?i)(?:_(\d{2,3})_|(\d{2,3})\s*BPM)", c.get("audio_path", ""))
        if label and len(markers) >= 2 and not invalid:
            a, b = markers[0], markers[-1]
            measured = (
                60 * (b["beat_time"] - a["beat_time"]) / (b["sample_time"] - a["sample_time"])
            )
            labeled = int(label[1] or label[2])
            if abs(measured / labeled - 1) > 0.03:
                half_double = min(abs(measured / labeled - 0.5), abs(measured / labeled - 2)) < 0.04
                output.append(
                    finding(
                        "WARP_HALF_DOUBLE" if half_double else "WARP_LABEL_MISMATCH",
                        "info" if half_double else "warning",
                        t,
                        c,
                        "Warp-map tempo differs from the filename label; verify the musical interpretation.",
                        evidence={"filename_bpm": labeled, "map_average_bpm": measured},
                        confidence="heuristic",
                    )
                )
    return output


@rule("stem_sync")
def sync(state, params):
    byid = {t["id"]: t for t in state.get("tracks", [])}
    output = []
    for group in params.get("groups", []):
        clips = []
        for ident in group:
            if ident not in byid:
                raise ValueError(f"Unknown stem-sync track ID: {ident}")
            cs = [
                c
                for c in byid[ident].get("clips", [])
                if c["type"] == "audio"
                and c.get("view") == "arrangement"
                and c.get("read_complete", True)
            ]
            if len(cs) != 1:
                raise ValueError(
                    "Explicit stem-sync groups currently require one complete audio clip per track"
                )
            clips.append((byid[ident], cs[0]))
        if len(clips) < 2:
            raise ValueError("A stem-sync group needs at least two tracks")
        reference = clips[0][1]
        for track, clip in clips[1:]:
            differs = (
                abs(clip["start_beats"] - reference["start_beats"]) > 0.01
                or abs(clip["end_beats"] - reference["end_beats"]) > 0.05
                or clip.get("warping") != reference.get("warping")
                or clip.get("warp_markers") != reference.get("warp_markers")
            )
            if differs:
                output.append(
                    finding(
                        "STEM_TIMING_MISMATCH",
                        "warning",
                        track,
                        clip,
                        "Explicitly linked stems have different starts, lengths or Warp maps.",
                        evidence={"reference": reference["id"]},
                    )
                )
    return output


@rule("instrument_assignments")
def instruments(state, params):
    output = []
    for t in state.get("tracks", []):
        if (
            t["type"] == "midi"
            and not t.get("devices")
            and any(active(c.get("notes", [])) for c in t.get("clips", []))
        ):
            output.append(
                finding(
                    "MIDI_NO_LOADED_INSTRUMENT",
                    "warning",
                    t,
                    None,
                    "MIDI notes exist but no device is loaded; check instrument or external routing.",
                )
            )
    return output


@rule("track_colors", "info")
def colors(state, params):
    from .layer_naming import ROLE_COLORS

    palette = params.get("colors", ROLE_COLORS)
    if not isinstance(palette, dict) or any(
        type(v) is not int or not 0 <= v <= 69 for v in palette.values()
    ):
        raise ValueError("track_colors.colors must map roles to color indexes 0..69")
    output = []
    for t in state.get("tracks", []):
        wanted = palette.get(t.get("role"))
        if wanted is not None and t.get("color_index") != wanted:
            output.append(
                finding(
                    "TRACK_COLOR_CONVENTION",
                    "info",
                    t,
                    None,
                    "Track color differs from the configured role convention.",
                    evidence={"current": t.get("color_index"), "proposed": wanted},
                    fix=metadata_fix(t, None, {"color_index": wanted}),
                )
            )
    return output


@rule("harmonic_layering", "info")
def harmonic_layering(state, params):
    """Flag measurable sustained semitone rubs, not inferred wrong-key notes."""
    minimum = params.get("minOverlapBeats", 0.5)
    if not isinstance(minimum, (int, float)) or not math.isfinite(minimum) or minimum <= 0:
        raise ValueError("minOverlapBeats must be positive and finite")
    output = []
    for track, clip in midi_clips(state):
        if track.get("role") == "drums":
            continue
        sounding = []
        pairs = []
        truncated = False
        for note in sorted(active(clip["notes"]), key=lambda n: n["start_time"]):
            sounding = [n for n in sounding if n["start_time"] + n["duration"] > note["start_time"]]
            for previous in sounding:
                overlap = (
                    min(
                        previous["start_time"] + previous["duration"],
                        note["start_time"] + note["duration"],
                    )
                    - note["start_time"]
                )
                if abs(previous["pitch"] - note["pitch"]) % 12 in {1, 11} and overlap >= minimum:
                    pairs.append(
                        {
                            "pitches": [previous["pitch"], note["pitch"]],
                            "at_beat": note["start_time"],
                            "overlap_beats": overlap,
                        }
                    )
                    if len(pairs) >= 256:
                        truncated = True
                        break
            if truncated:
                break
            sounding.append(note)
        if pairs:
            output.append(
                finding(
                    "MIDI_SUSTAINED_CLOSE_INTERVAL",
                    "info",
                    track,
                    clip,
                    "Sustained voices rub by a semitone/minor ninth; review voicing. This can be intentional and is not proof of a wrong note.",
                    evidence={"count": len(pairs), "truncated": truncated, "examples": pairs[:15]},
                    confidence="heuristic",
                )
            )
    return output


@rule("session_settings")
def session_settings(state, params):
    session = state.get("session", {})
    tempo = session.get("tempo")
    sentinel = {"id": "session", "name": "Session"}
    output = []
    if (
        not isinstance(tempo, (int, float))
        or isinstance(tempo, bool)
        or not math.isfinite(tempo)
        or not 20 <= tempo <= 999
    ):
        output.append(
            finding(
                "SESSION_INVALID_TEMPO",
                "error",
                sentinel,
                None,
                "Session tempo is invalid or unavailable.",
            )
        )
    expected = params.get("expectedTempo")
    if expected is not None:
        if (
            not isinstance(expected, (int, float))
            or isinstance(expected, bool)
            or not math.isfinite(expected)
            or not 20 <= expected <= 999
        ):
            raise ValueError("expectedTempo must be a verified BPM in 20..999")
        if (
            isinstance(tempo, (int, float))
            and math.isfinite(tempo)
            and abs(tempo - expected) > params.get("toleranceBpm", 0.25)
        ):
            output.append(
                finding(
                    "SESSION_EXPECTED_TEMPO",
                    "warning",
                    sentinel,
                    None,
                    "Session tempo differs from the explicitly configured reference.",
                    evidence={"expected_bpm": expected, "actual_bpm": tempo},
                )
            )
    return output


@rule("organization", "info")
def organization(state, params):
    output = []
    byrole = defaultdict(list)
    for track in state.get("tracks", []):
        if (
            track.get("role") in params.get("roles", ["bass", "drums", "synth"])
            and track.get("group_read_complete")
            and not track.get("group_name")
        ):
            byrole[track["role"]].append(track)
    for role, tracks in byrole.items():
        if len(tracks) >= params.get("minTracks", 2):
            output.append(
                finding(
                    "ROLE_TRACKS_UNGROUPED",
                    "info",
                    tracks[0],
                    None,
                    "Several tracks of this role are ungrouped; review organization without changing routing automatically.",
                    evidence={"role": role, "tracks": [t["id"] for t in tracks]},
                    confidence="convention",
                )
            )
    return output


def lint_state(state, config=None, selected_rules=None):
    settings = config or {}
    if set(settings) - {"failOn", "rules", "includeSession", "target"}:
        raise ValueError("Unknown lint configuration key")
    target = settings.get("target", {})
    if (
        not isinstance(target, dict)
        or set(target) - {"trackIds", "clipIds", "types"}
        or any(
            not isinstance(v, list) or any(not isinstance(x, str) for x in v)
            for v in target.values()
        )
    ):
        raise ValueError("Invalid lint target selectors")
    if target:
        from .song_init import selected

        state = deepcopy(state)
        track_ids = {t["id"] for t in state["tracks"]}
        clip_ids = {c["id"] for t in state["tracks"] for c in t.get("clips", [])}
        if set(target.get("trackIds", [])) - track_ids or set(target.get("clipIds", [])) - clip_ids:
            raise ValueError("Lint target IDs are not present in this capture")
        state["tracks"] = list(selected(state, target))
        if "clipIds" in target:
            for track in state["tracks"]:
                track["clips"] = [c for c in track.get("clips", []) if c["id"] in target["clipIds"]]
        allowed = {t["id"] for t in state["tracks"]} | {
            c["id"] for t in state["tracks"] for c in t.get("clips", [])
        }
        state["capture_errors"] = [
            e
            for e in state.get("capture_errors", [])
            if not e.get("target") or e["target"] in allowed
        ]
    overrides = settings.get("rules", {})
    if not isinstance(overrides, dict) or set(overrides) - RULES.keys():
        raise ValueError("Unknown lint rule")
    selected_rules = set(selected_rules or RULES)
    if selected_rules - RULES.keys():
        raise ValueError("Unknown selected lint rule")
    findings, checks = [], []
    for name, (fn, default_severity) in RULES.items():
        opts = overrides.get(name, {})
        if not isinstance(opts, dict) or set(opts) - {"enabled", "severity", "params"}:
            raise ValueError(f"Invalid settings for {name}")
        if type(opts.get("enabled", True)) is not bool or not isinstance(
            opts.get("params", {}), dict
        ):
            raise ValueError(f"Invalid enabled/params for {name}")
        severity = opts.get("severity", default_severity)
        if severity not in SEVERITY:
            raise ValueError("severity must be info, warning or error")
        if name not in selected_rules or not opts.get("enabled", True):
            checks.append({"rule": name, "status": "disabled"})
            continue
        if name == "organization" and any(
            t.get("role") in opts.get("params", {}).get("roles", ["bass", "drums", "synth"])
            and not t.get("group_read_complete")
            for t in state.get("tracks", [])
        ):
            checks.append(
                {
                    "rule": name,
                    "status": "not_evaluated",
                    "reason": "Group hierarchy metadata is unavailable",
                }
            )
            continue
        if name == "stem_sync" and not opts.get("params", {}).get("groups"):
            checks.append(
                {
                    "rule": name,
                    "status": "not_evaluated",
                    "reason": "No explicit linked-stem groups; independent loops are not assumed to be stems.",
                }
            )
            continue
        try:
            issues = fn(state, opts.get("params", {}))
        except (KeyError, TypeError, ZeroDivisionError, OverflowError) as error:
            checks.append({"rule": name, "status": "incomplete", "reason": str(error)})
            continue
        for issue in issues:
            issue["rule"] = name
            if "severity" in opts:
                issue["severity"] = severity
            issue["id"] = fingerprint(
                {
                    "rule": name,
                    "code": issue["code"],
                    "track": issue["track"]["id"],
                    "clip": issue["clip"]["id"] if issue["clip"] else None,
                }
            )[:16]
        findings.extend(issues)
        checks.append({"rule": name, "status": "assessed", "findings": len(issues)})
    capture_errors = deepcopy(state.get("capture_errors", []))
    for _, clip in eligible(state):
        if clip.get("read_complete") is False or (clip["type"] == "midi" and "notes" not in clip):
            if not any(e.get("target") == clip["id"] for e in capture_errors):
                capture_errors.append(
                    {
                        "target": clip["id"],
                        "operation": "data_completeness",
                        "error": "Clip data was not fully read",
                    }
                )
    fail_on = settings.get("failOn", "warning")
    if fail_on not in {"none", *SEVERITY}:
        raise ValueError("failOn must be none, info, warning or error")
    incomplete = (
        bool(capture_errors)
        or any(c["status"] == "incomplete" for c in checks)
        or not any(c["status"] == "assessed" for c in checks)
    )
    counts = {s: sum(f["severity"] == s for f in findings) for s in SEVERITY}
    fail = fail_on != "none" and any(SEVERITY[f["severity"]] >= SEVERITY[fail_on] for f in findings)
    return {
        "schemaVersion": 1,
        "mode": "lint",
        "source": state.get("source", "snapshot"),
        "capturedAt": state.get("capturedAt"),
        "captureFingerprint": state.get("capture_fingerprint"),
        "captureMetrics": state.get("capture_metrics"),
        "captureScope": state.get("capture_scope"),
        "readOnly": True,
        "scope": {
            "includeSession": state.get("includeSession", False),
            "protectedOriginalsExcluded": True,
            "target": target,
        },
        "summary": {
            "tracks": len(state.get("tracks", [])),
            "clips": sum(len(t.get("clips", [])) for t in state.get("tracks", [])),
            "audioClips": sum(c["type"] == "audio" for _, c in eligible(state)),
            "midiClips": sum(1 for _ in midi_clips(state)),
            "midiNotes": sum(len(c["notes"]) for _, c in midi_clips(state)),
            "findings": len(findings),
            **counts,
            "autofixable": sum(f["autofixable"] for f in findings),
        },
        "checks": checks,
        "findings": findings,
        "captureErrors": capture_errors,
        "limitations": state.get("limitations", [])
        + [
            "Grid, velocity and filename-BPM findings are review hints, not audio audition.",
            "Harmonic correctness needs verified key/chord/time context and is not claimed by structural linting.",
            "No grouping/reordering, MIDI replacement, trimming, Warp repair, deletion or native Save As is automatically performed.",
        ],
        "failOn": fail_on,
        "exitCode": 2 if incomplete else 1 if fail else 0,
        "status": "incomplete"
        if incomplete
        else "issues"
        if fail
        else "review"
        if findings
        else "passed",
    }


def apply_metadata_fixes(report, connection):
    """Apply only names/colors, rechecking live guards. Never apply unsupported repairs."""
    if report["source"] != "live" or report["captureErrors"] or report["exitCode"] == 2:
        raise ValueError("Fixes require a complete fresh Live capture")
    fixes = [f for f in report["findings"] if f["autofixable"]]
    duplicate_ids = {
        f["track"]["id"] for f in report["findings"] if f["code"] == "TRACK_DUPLICATE_NAME"
    }
    if any(f["track"]["id"] in duplicate_ids for f in fixes):
        raise ValueError("Resolve ambiguous duplicate track names before automatic fixes")
    # Clip names first, then colors, then track renames, preserving captured name guards.
    fixes.sort(
        key=lambda f: (
            2
            if f["fix"]["kind"] == "set_track" and "name" in f["fix"]["patch"]
            else 0
            if f["fix"]["kind"] == "set_clip"
            else 1
        )
    )
    for item in fixes:
        if set(item["fix"]["patch"]) - {"name", "color_index"}:
            raise ValueError("Unsupported automatic property")
    # One guarded read per target, batched on the main thread. Every guard is
    # checked before the first write, so a stale target still blocks the batch.
    guards = []
    owners = []
    for item in fixes:
        fix = item["fix"]
        guards.append({"type": "get_track_info", "params": {"track_index": fix["track_index"]}})
        owners.append((fix, "track"))
        if fix["kind"] == "set_clip":
            guards.append(
                {"type": "read_access_object", "params": dict(fix["locator"], object_type="clip")}
            )
            owners.append((fix, "clip"))
    for (fix, kind), (value, error) in zip(owners, read_many(connection.send_command, guards)):
        if error is not None:
            raise RuntimeError(
                "Fix guard read failed; nothing was written: " + str(error)
            ) from error
        if kind == "track" and value.get("name") != fix["expected_track_name"]:
            raise ValueError("Track moved/renamed since lint capture; rerun lint")
    commands = []
    for item in fixes:
        fix = item["fix"]
        if fix["kind"] == "set_clip":
            target = dict(fix["locator"])
        else:
            target = dict(
                track_index=fix["track_index"], expected_track_name=fix["expected_track_name"]
            )
        commands.append(
            {
                "type": "write_access_object",
                "params": dict(
                    target,
                    object_type="clip" if fix["kind"] == "set_clip" else "track",
                    properties=fix["patch"],
                ),
            }
        )
    if not commands:
        return []
    # Existing bridge executes the batch on the main thread and each writer verifies readback.
    try:
        result = connection.send_command("batch", {"commands": commands})
        if result.get("executed") != len(commands):
            raise RuntimeError("Incomplete metadata write batch")
    except Exception as error:
        raise RuntimeError(
            "Metadata fix failed; partial changes may exist. Rerun lint before retrying: "
            + str(error)
        ) from error
    # Independent readback, including final track names after all renames.
    final_names = {
        f["fix"]["track_index"]: f["fix"]["patch"]["name"]
        for f in fixes
        if f["fix"]["kind"] == "set_track" and "name" in f["fix"]["patch"]
    }
    reads = []
    for item in fixes:
        fix = item["fix"]
        if fix["kind"] == "set_track":
            reads.append({"type": "get_track_info", "params": {"track_index": fix["track_index"]}})
        else:
            loc = dict(fix["locator"])
            loc["expected_track_name"] = final_names.get(
                fix["track_index"], fix["expected_track_name"]
            )
            if "name" in fix["patch"]:
                loc["expected_clip_name"] = fix["patch"]["name"]
            reads.append({"type": "read_access_object", "params": dict(loc, object_type="clip")})
    for item, (actual, error) in zip(fixes, read_many(connection.send_command, reads)):
        fix = item["fix"]
        if error is not None:
            raise RuntimeError(
                "Metadata readback failed; rerun lint and inspect Live Undo: " + str(error)
            ) from error
        seen = actual if fix["kind"] == "set_track" else actual["properties"]
        for field, value in fix["patch"].items():
            if seen[field] != value:
                raise RuntimeError("Metadata readback failed; rerun lint and inspect Live Undo")
    return [f["id"] for f in fixes]


def run_lint(
    config,
    *,
    snapshot=None,
    connection=None,
    live=False,
    fix=False,
    selected_rules=None,
    fail_on=None,
    include_session=False,
    target=None,
):
    settings = deepcopy(config.get("lint", {}))
    if fail_on:
        settings["failOn"] = fail_on
    if target:
        settings["target"] = target
    if type(settings.get("includeSession", False)) is not bool:
        raise ValueError("lint.includeSession must be boolean")
    include_session = include_session or settings.get("includeSession", False)
    if fix and not live:
        raise ValueError("--fix requires --live; snapshot files are never treated as Live handles")
    if live and connection is None:
        from ableton_live_mcp.connection import get_ableton_connection

        from .wire import install as install_wire

        install_wire()
        try:
            connection = get_ableton_connection()
        except Exception as error:
            raise RuntimeError("Live is not connected: " + str(error)) from error
    try:
        state = collect_live(connection, include_session) if live else snapshot
    except Exception as error:
        raise RuntimeError("Cannot capture the running Live set: " + str(error)) from error
    if not isinstance(state, dict) or not isinstance(state.get("tracks"), list):
        raise ValueError("A normalized set snapshot is required")
    report = lint_state(state, settings, selected_rules)
    if fix:
        before = deepcopy(report)
        applied = apply_metadata_fixes(report, connection)
        after = collect_live(connection, include_session)
        report = lint_state(after, settings, selected_rules)
        report.update(
            readOnly=False,
            appliedFixIds=applied,
            beforeSummary=before["summary"],
            beforeFindings=before["findings"],
            mode="lint-fix",
        )
    return report


def write_report(path, report):
    """Explicit --report is the only file write during read-only lint."""
    path = Path(path)
    if not path.parent.is_dir():
        raise ValueError("Report parent directory must already exist")
    if path.exists():
        raise ValueError("Report exists; choose a new report path")
    with path.open("x", encoding="utf-8") as output:
        json.dump(report, output, indent=2, allow_nan=False)
    return path
