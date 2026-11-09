"""Nine preparation operations for the open set.

``enableton`` with no arguments shows these operations. Each ``run`` mutates a
state dict, or sends the same edits through a Live ``dispatch`` callable.
``--plan`` copies the state first, so the caller's set is left untouched.

The result field ``undo`` is the contract string "one Live Undo step". Known-ahead
property writes go out as one bridge ``batch``. ``adopt`` cannot do that: the copy
index exists only after ``duplicate_track``, and this module does not pretend
otherwise. Live may still record a nested undo inside a command handler.
"""

import argparse
import json
import re
import socket
import sys
from copy import deepcopy
from pathlib import Path

from .align_safety import base_name, is_protected, protection_name
from .align_tracks import preferred_mode, resolve_mode
from .assign_instruments import candidates_for, has_instrument, plan_assignments
from .audio_repair import dc_decision, gain_decision
from .clip_geometry import overlaps
from .layer_naming import ROLE_COLORS, ROLE_LABELS, layer_name
from .song_init import Result, register
from .track_prep import ARCHIVE_COLOR, _find_copy, infer_content

UNDO = "one Live Undo step"
AMBIGUOUS = "no role keyword, device or pitch pattern"
WARP_OFF_REASON = "needs reference and rendered replacement"
SECTION_NAMES = ("Intro", "Verse 1", "Chorus", "Drop", "Break", "Outro")
_BATCHABLE = {"write_access_object", "set_access_warp", "set_fold_state"}

_WORDS = {
    "adopt": "Make a muted ORIGINAL copy of each track",
    "name": "NN Role track names and role colours",
    "label": "Name each clip by role, content and length",
    "voice": "Placeholder instrument on silent MIDI tracks",
    "level": "Fix full-scale clip gain and DC offset",
    "lock": "Warp mode per a reference layer",
    "frame": "Bar-align loop bounds and clip ends",
    "map": "Section locators (Intro, Drop, Outro)",
    "check": "Lint findings, no writes",
}

_TITLES = {
    "adopt": "Protect originals",
    "name": "Name tracks",
    "label": "Name clips",
    "voice": "Placeholder instruments",
    "level": "Clip gain and DC",
    "lock": "Warp modes",
    "frame": "Bar lengths",
    "map": "Section locators",
    "check": "Lint",
}

_PHASE = {
    "adopt": "protect",
    "name": "identify",
    "label": "identify",
    "voice": "audible",
    "level": "audible",
    "lock": "time",
    "frame": "time",
    "map": "navigate",
    "check": "gate",
}

_ORDER = ("adopt", "name", "label", "voice", "level", "lock", "frame", "map", "check")
_ALIASES = {"align": "lock"}
_DEPRECATED = {
    "prepare-tracks": ("adopt", "name"),
    "assign-instruments": ("voice",),
    "repair-audio": ("level",),
    "align-tracks": ("lock",),
}
_DEPRECATED_LINE = {
    "prepare-tracks": "enableton: prepare-tracks is now adopt, then name",
    "assign-instruments": "enableton: assign-instruments is now voice",
    "repair-audio": "enableton: repair-audio is now level",
    "align-tracks": "enableton: align-tracks is now lock",
    "lint": "enableton: lint is now check",
}
_LEGACY = {
    "serve",
    "build-bridge",
    "install",
    "doctor",
    "song-init",
    "initiate",
    "scan-audio",
    "remix-plan",
    "remix-guide",
    "remix-refine",
    "remix-prepare",
    "remix-build",
    "remix-preview",
    "remix-compare",
    "remix-inspect",
}


def _run_later(op_id):
    def _call(source, options):
        return run(op_id, source, options)

    return _call


OPS = [
    {
        "id": op_id,
        "title": _TITLES[op_id],
        "writes": op_id != "check",
        "phase": _PHASE[op_id],
        "run": _run_later(op_id),
        "needs": [] if op_id == "check" else ["stopped transport"],
        "idempotent": True,
        "words": _WORDS[op_id],
    }
    for op_id in _ORDER
]
_BY_ID = {op["id"]: op for op in OPS}


def instructions():
    """Handshake text. A model can list the nine ops without calling a tool."""

    ops = "; ".join(f"{op['id']}: {op['words']}" for op in OPS)
    return "\n".join(
        [
            "EnAbleton edits the open set and writes by default.",
            f"Ops: {ops}.",
            'When the user says "Enableton", show these nine operations and a prompt. Wait for a number, an operation id, or free text. Do not write until they choose.',
            'Answer "prep my song" and "set me up" with prep all.',
            "A direct edit request is executed with the write tools; do not propose a plan.",
            "Identity guard: match name and index, and Arrangement start time, before every write.",
            "Read back every written field before reporting the edit.",
            "One Live Undo step per operation.",
            "Live has no API for grouping, track reordering, or GUI automation.",
        ]
    )


def probe_live(timeout=1.5):
    """Return True when something accepts TCP on 127.0.0.1:9877. Never raises."""

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(("127.0.0.1", 9877))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def resolve(text):
    """Map a number, id, unique prefix, or the align alias to an op id."""

    key = str(text).strip().casefold()
    if key in {"all", "list"}:
        return key
    if key in _ALIASES:
        return _ALIASES[key]
    if key.isdigit():
        number = int(key)
        if 1 <= number <= len(OPS):
            return OPS[number - 1]["id"]
        return None
    if key in _BY_ID:
        return key
    matches = [op_id for op_id in _ORDER if key and op_id.startswith(key)]
    if len(matches) == 1:
        return matches[0]
    return None


def _session(state):
    session = state.get("session") or {}
    tempo = session.get("tempo") or 120
    numerator = session.get("numerator") or session.get("signature_numerator") or 4
    denominator = session.get("denominator") or session.get("signature_denominator") or 4
    return {
        "tempo": float(tempo),
        "numerator": int(numerator),
        "denominator": int(denominator),
        "is_playing": bool(session.get("is_playing") or session.get("playing")),
        "recording": bool(session.get("recording") or session.get("record_mode")),
    }


def _track_type(track):
    if track.get("is_group") or track.get("type") == "group":
        return "group"
    if track.get("is_return") or track.get("type") == "return":
        return "return"
    if track.get("is_master") or track.get("type") in {"main", "master"}:
        return "main"
    return track.get("type") or "midi"


def _selected(track, options):
    wanted = options.get("tracks")
    if not wanted:
        return True
    return track.get("index") in set(wanted)


def _regular(track):
    return _track_type(track) in {"audio", "midi"} and not is_protected(track.get("name"))


def _content_tracks(state, options):
    rows = []
    for track in state.get("tracks") or []:
        if _regular(track) and _selected(track, options):
            rows.append(track)
    return rows


def _empty(track):
    return not (track.get("clips") or [])


def _result(op, status, changed, readback, unsupported, skipped):
    return {
        "op": op,
        "status": status,
        "changed": changed,
        "readback": readback,
        "unsupported": unsupported,
        "counts": {
            "targets": len(changed) + skipped + len(unsupported),
            "changed": len(changed),
            "skipped": skipped,
            "unsupported": len(unsupported),
        },
        "undo": UNDO,
    }


def _finish(op, changed, readback, unsupported, skipped, refused=False):
    if refused:
        status = "refused"
    elif unsupported:
        status = "partial"
    elif changed:
        status = "applied"
    else:
        status = "unchanged"
    return _result(op, status, changed, readback, unsupported, skipped)


def _refused(op, reason):
    return _finish(
        op,
        [],
        {},
        [{"target": "session", "reason": reason}],
        0,
        refused=True,
    )


def _guard(state, op):
    if op == "check":
        return None
    session = _session(state)
    if session["is_playing"] or session["recording"]:
        return _refused(op, "Stop playback and recording before editing")
    return None


def _record(state, commands):
    if commands:
        state.setdefault("writes", []).append({"type": "batch", "params": {"commands": commands}})


def _send_one(dispatch, command):
    kind = command["type"]
    params = dict(command.get("params") or {})
    if kind == "create_locator":
        if "time" in params:
            dispatch("set_current_song_time", {"time": params.pop("time")})
        dispatch("create_locator", {"name": params["name"]})
        return
    dispatch(kind, params)


def _commit(state, commands):
    """Record one write. A Live dispatch sends it. Plan shadows have no dispatch.

    ``adopt`` does not use this sender. Its copy index exists only after
    ``duplicate_track``, so the live path calls ``_find_copy`` first.
    """

    _record(state, commands)
    dispatch = state.get("_dispatch")
    if dispatch is None or not commands:
        return
    kinds = {command["type"] for command in commands}
    if kinds <= _BATCHABLE:
        dispatch("batch", {"commands": commands})
        return
    for command in commands:
        _send_one(dispatch, command)


def _adopt_live(dispatch, index, name, copy_name):
    """Duplicate, then name the copy Live actually created. Do not rename the source."""

    before = dispatch("get_session_info", {})["track_count"]
    dispatch("duplicate_track", {"track_index": index})
    count = dispatch("get_session_info", {})["track_count"]
    if count != before + 1:
        raise RuntimeError("duplicate did not create exactly one track")
    copy_index, found_name = _find_copy(dispatch, index, name, count, previous_count=before)
    dispatch(
        "write_access_object",
        {
            "object_type": "track",
            "track_index": copy_index,
            "expected_track_name": found_name,
            "properties": {
                "name": copy_name,
                "mute": True,
                "solo": False,
                "arm": False,
                "color_index": ARCHIVE_COLOR,
            },
        },
    )
    group = dispatch("get_group_info", {"track_index": copy_index})
    if group.get("is_foldable"):
        dispatch("set_fold_state", {"track_index": copy_index, "folded": True})


def _reindex(state):
    for index, track in enumerate(state.get("tracks") or []):
        track["index"] = index


def _clip_index(clip):
    if clip.get("index") is not None:
        return clip.get("index")
    locator = clip.get("locator") or {}
    if locator.get("clip_index") is not None:
        return locator["clip_index"]
    return 0


def _clip_view(clip):
    view = clip.get("view") or (clip.get("locator") or {}).get("clip_view")
    if view in ("session", "arrangement"):
        return view
    return "arrangement"


def _clip_label(clip):
    """Clip name the bridge can guard. An empty name is rejected before any write."""

    name = clip.get("name")
    if isinstance(name, str) and name.strip():
        return name
    return None


def _clip_start(clip):
    for key in ("start", "start_beats", "start_time"):
        value = clip.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return 0.0


def _clip_address(track, clip):
    """Target the clip's own view. The bridge defaults to an empty Session slot."""

    view = _clip_view(clip)
    params = {
        "track_index": track.get("index"),
        "clip_index": _clip_index(clip),
        "clip_view": view,
        "expected_track_name": track.get("name"),
        "expected_clip_name": clip.get("name") or "",
    }
    if view == "arrangement":
        params["expected_start_time"] = _clip_start(clip)
    return params


def _clip_end(clip):
    for key in ("end", "end_beats", "end_time", "loop_end"):
        value = clip.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    return None


def _units_of(clip):
    if clip.get("type") == "midi" or _track_type({"type": clip.get("type")}) == "midi":
        return "beats"
    if clip.get("warping") is True:
        return "beats"
    if clip.get("warping") is False:
        return "seconds"
    return None


def _bar(state, units):
    session = _session(state)
    beats = session["numerator"] * 4 / session["denominator"]
    if units == "seconds":
        return beats * 60.0 / session["tempo"], 0.04 * 60.0 / session["tempo"]
    return beats, 0.04


def _snap(value, bar, tolerance):
    nearest = round(float(value) / bar) * bar
    if abs(float(value) - nearest) <= tolerance:
        return float(value)
    return float(nearest)


def _loop_value(fields, name, current):
    for field, _previous, snapped in fields:
        if field == name:
            return snapped
    return current


def _keep_loop_order(clip, fields, bar):
    """Keep loop end after loop start. A downward snap must not make an empty loop."""

    start = clip.get("loop_start")
    end = clip.get("loop_end")
    if isinstance(start, bool) or not isinstance(start, (int, float)):
        return fields
    if isinstance(end, bool) or not isinstance(end, (int, float)):
        return fields
    start_value = _loop_value(fields, "loop_start", float(start))
    end_value = _loop_value(fields, "loop_end", float(end))
    if end_value <= start_value:
        fields = [item for item in fields if item[0] != "loop_end"]
        fields.append(("loop_end", float(end), float(start_value + bar)))
        end_value = start_value + bar
    marker = clip.get("end_marker")
    if isinstance(marker, bool) or not isinstance(marker, (int, float)):
        return fields
    marker_value = _loop_value(fields, "end_marker", float(marker))
    if marker_value < end_value:
        fields = [item for item in fields if item[0] != "end_marker"]
        fields.append(("end_marker", float(marker), float(end_value)))
    order = {"loop_start": 0, "loop_end": 1, "end_marker": 2}
    return sorted(fields, key=lambda item: order.get(item[0], 9))


def _derived_roles(state, options):
    """Same numbering ``name`` uses. Nothing here is written."""

    rows = []
    number = 0
    for track in state.get("tracks") or []:
        if not _regular(track):
            continue
        number += 1
        content = infer_content(track)
        role = content["role"]
        rows.append(
            {
                "track": track,
                "number": number,
                "role": role,
                "label": ROLE_LABELS.get(role, ROLE_LABELS["other"]),
                "color": ROLE_COLORS.get(role, ROLE_COLORS["other"]),
                "evidence": content["evidence"],
                "ambiguous": content["evidence"] == AMBIGUOUS,
                "selected": _selected(track, options),
            }
        )
    return rows


def _existing_original(tracks, name):
    target = protection_name(name)
    source_base = base_name(name)
    for track in tracks:
        other = track.get("name") or ""
        if other == target:
            return True
        if is_protected(other) and other.split("|", 1)[-1].strip() == name.strip():
            return True
        if is_protected(other) and base_name(other.split("|", 1)[-1].strip()) == source_base:
            return True
    return False


def _existing_unprotected_copy(tracks, index, name):
    """True when ``track_prep._find_copy`` would see a non-protected sibling."""

    def send(command, params):
        if command != "get_track_info":
            raise RuntimeError(command)
        return tracks[params["track_index"]]

    try:
        _find_copy(send, index, name, len(tracks))
    except (RuntimeError, IndexError, KeyError):
        return False
    return True


def _run_adopt(state, options):
    blocked = _guard(state, "adopt")
    if blocked:
        return blocked
    changed = []
    readback = {}
    unsupported = []
    skipped = 0
    tracks = state.setdefault("tracks", [])
    originals = [track for track in list(tracks) if not _empty(track)]
    for source in originals:
        if not _selected(source, options):
            continue
        name = source.get("name") or ""
        if not _regular(source) or is_protected(name):
            skipped += 1
            continue
        if not name.strip():
            unsupported.append(
                {"target": f"track:{source.get('index')}", "reason": "track name is empty"}
            )
            continue
        index = next(position for position, track in enumerate(tracks) if track is source)
        if _existing_original(tracks, name) or _existing_unprotected_copy(tracks, index, name):
            skipped += 1
            continue
        copy_name = protection_name(name)
        commands = [
            {"type": "duplicate_track", "params": {"track_index": index}},
            {
                "type": "write_access_object",
                "params": {
                    "object_type": "track",
                    "track_index": index + 1,
                    "expected_track_name": copy_name,
                    "properties": {"name": copy_name, "mute": True, "arm": False},
                },
            },
        ]
        if state.get("_dispatch") is not None:
            _adopt_live(state["_dispatch"], index, name, copy_name)
            _record(state, commands)
        else:
            _commit(state, commands)
        copy = {
            "name": copy_name,
            "type": _track_type(source),
            "mute": True,
            "arm": False,
            "solo": False,
            "color_index": ARCHIVE_COLOR,
            "frozen": False,
            "is_foldable": bool(source.get("is_foldable") or _track_type(source) == "group"),
            "folded": bool(source.get("is_foldable") or _track_type(source) == "group"),
            "devices": deepcopy(source.get("devices") or []),
            "clips": deepcopy(source.get("clips") or []),
        }
        tracks.insert(index + 1, copy)
        _reindex(state)
        changed.append(
            {
                "track_index": index + 1,
                "expected_track_name": copy_name,
                "field": "name",
                "from": name,
                "to": copy_name,
            }
        )
        readback[f"track:{index + 1}:name"] = copy["name"]
        readback[f"track:{index + 1}:mute"] = True
        readback[f"track:{index + 1}:arm"] = False
    return _finish("adopt", changed, readback, unsupported, skipped)


def _run_name(state, options):
    blocked = _guard(state, "name")
    if blocked:
        return blocked
    changed = []
    readback = {}
    unsupported = []
    skipped = 0
    commands = []
    for row in _derived_roles(state, options):
        if not row["selected"]:
            continue
        track = row["track"]
        if row["ambiguous"]:
            unsupported.append({"target": f"track:{track.get('index')}", "reason": AMBIGUOUS})
            continue
        target = layer_name(row["role"], row["number"])
        color = row["color"]
        current = track.get("name") or ""
        same_name = current == target
        same_color = track.get("color_index") == color
        if same_name and same_color:
            skipped += 1
            continue
        if current != target:
            changed.append(
                {
                    "track_index": track.get("index"),
                    "expected_track_name": current,
                    "field": "name",
                    "from": current,
                    "to": target,
                }
            )
            commands.append(
                {
                    "type": "write_access_object",
                    "params": {
                        "object_type": "track",
                        "track_index": track.get("index"),
                        "expected_track_name": current,
                        "properties": {"name": target, "color_index": color},
                    },
                }
            )
            track["name"] = target
        if track.get("color_index") != color:
            if same_name:
                changed.append(
                    {
                        "track_index": track.get("index"),
                        "expected_track_name": current,
                        "field": "color_index",
                        "from": track.get("color_index"),
                        "to": color,
                    }
                )
            track["color_index"] = color
        readback[f"track:{track.get('index')}:name"] = track.get("name")
        readback[f"track:{track.get('index')}:color_index"] = track.get("color_index")
    _commit(state, commands)
    return _finish("name", changed, readback, unsupported, skipped)


def _owning_number(track, derived):
    match = re.match(r"^(\d+)\s+", (track.get("name") or "").strip())
    if match:
        return int(match.group(1))
    return derived


def _phrase(clip, bar):
    start = _clip_start(clip) if clip.get("view") == "arrangement" else 0.0
    end = _clip_end(clip)
    if end is None:
        return "loop"
    span = end - (
        _clip_start(clip)
        if clip.get("view") == "arrangement"
        else float(clip.get("loop_start") or 0)
    )
    if span <= 0:
        return "loop"
    bars = span / bar
    whole = int(round(bars))
    if whole <= 0 or abs(bars - whole) > 0.05:
        return "loop"
    start_bars = start / bar
    notes = clip.get("notes") or []
    if clip.get("view") == "arrangement" and whole >= 8 and 8 <= start_bars < 32:
        return f"verse {whole}"
    if notes and whole:
        return f"{whole}-bar loop"
    return f"{whole}-bar loop"


def _run_label(state, options):
    blocked = _guard(state, "label")
    if blocked:
        return blocked
    changed = []
    readback = {}
    unsupported = []
    skipped = 0
    commands = []
    roles = {id(row["track"]): row for row in _derived_roles(state, options)}
    for track in state.get("tracks") or []:
        if not _regular(track) or not _selected(track, options):
            if _selected(track, options) and is_protected(track.get("name")):
                skipped += 1
            continue
        row = roles.get(id(track))
        if row is None:
            skipped += 1
            continue
        units = "beats"
        for clip in track.get("clips") or []:
            clip_units = _units_of(clip) or "beats"
            units = clip_units
            bar, _tolerance = _bar(state, units)
            number = _owning_number(track, row["number"])
            target = f"{number:02d} {row['label']} | {_phrase(clip, bar)}"
            current = clip.get("name") or ""
            clip_index = _clip_index(clip)
            if _clip_label(clip) is None:
                unsupported.append(
                    {
                        "target": f"track:{track.get('index')}:clip:{clip_index}",
                        "reason": "clip name is empty",
                    }
                )
                continue
            if current == target:
                skipped += 1
                continue
            changed.append(
                {
                    "track_index": track.get("index"),
                    "expected_track_name": track.get("name"),
                    "clip_index": clip_index,
                    "field": "name",
                    "from": current,
                    "to": target,
                    "units": units,
                }
            )
            commands.append(
                {
                    "type": "write_access_object",
                    "params": dict(
                        _clip_address(track, clip),
                        object_type="clip",
                        expected_clip_name=current,
                        properties={"name": target},
                    ),
                }
            )
            clip["name"] = target
            readback[f"track:{track.get('index')}:clip:{clip_index}:name"] = clip["name"]
    _commit(state, commands)
    return _finish("label", changed, readback, unsupported, skipped)


def _assign_tracks(state):
    rows = []
    for track in state.get("tracks") or []:
        kind = _track_type(track)
        row = {
            "index": track.get("index"),
            "name": track.get("name") or "",
            "type": "midi" if kind == "midi" else kind,
            "is_group": kind == "group",
            "is_return": kind == "return",
            "is_master": kind == "main",
            "is_frozen": bool(track.get("frozen") or track.get("is_frozen")),
            "devices": track.get("devices") or [],
            "clips": [],
        }
        if "midi_output" in track:
            row["midi_output"] = track.get("midi_output")
        for clip in track.get("clips") or []:
            row["clips"].append(
                {
                    "type": clip.get("type") or kind,
                    "name": clip.get("name") or "",
                    "notes": clip.get("notes") or [],
                }
            )
        rows.append(row)
    return rows


def _run_voice(state, options):
    blocked = _guard(state, "voice")
    if blocked:
        return blocked
    changed = []
    readback = {}
    unsupported = []
    skipped = 0
    commands = []
    planned = plan_assignments(_assign_tracks(state))
    if state.get("_dispatch") is not None:
        from .assign_instruments import apply_plan

        applied = apply_plan(state["_dispatch"], planned, confirm=True)
        for row in applied.get("results") or []:
            changed.append(
                {
                    "track_index": row.get("track_index"),
                    "expected_track_name": row.get("track_name"),
                    "field": "devices",
                    "from": [],
                    "to": row.get("device_name"),
                }
            )
            readback[f"track:{row.get('track_index')}:device:0:name"] = row.get("device_name")
        _record(
            state,
            [
                {
                    "type": "load_instrument_or_effect",
                    "params": {"track_index": row.get("track_index")},
                }
                for row in applied.get("results") or []
            ],
        )
        return _finish("voice", changed, readback, unsupported, skipped)
    by_index = {track.get("index"): track for track in state.get("tracks") or []}
    for action in planned.get("skipped") or []:
        if _selected({"index": action.get("index")}, options):
            skipped += 1
    for action in planned.get("tracks") or []:
        track = by_index.get(action.get("track_index"))
        if track is None or not _selected(track, options):
            continue
        if has_instrument(track.get("devices")):
            skipped += 1
            continue
        names = list(action.get("candidates") or candidates_for(action.get("role")))
        if not names:
            unsupported.append(
                {"target": f"track:{track.get('index')}", "reason": "no stock placeholder"}
            )
            continue
        device_name = names[0]
        if track.get("device_confirmed") is False:
            raise RuntimeError(
                f"{device_name} was not confirmed on {track.get('name')}. "
                "Inspect that track before loading it again."
            )
        devices = list(track.get("devices") or [])
        devices.insert(0, {"name": device_name, "type": "instrument", "class_name": device_name})
        track["devices"] = devices
        commands.append(
            {
                "type": "load_instrument_or_effect",
                "params": {
                    "track_index": track.get("index"),
                    "expected_track_name": track.get("name"),
                    "uri": device_name,
                },
            }
        )
        changed.append(
            {
                "track_index": track.get("index"),
                "expected_track_name": track.get("name"),
                "field": "devices",
                "from": [],
                "to": device_name,
            }
        )
        readback[f"track:{track.get('index')}:device:0:name"] = track["devices"][0]["name"]
    _commit(state, commands)
    return _finish("voice", changed, readback, unsupported, skipped)


def _level_issues(clip):
    issues = [str(item) for item in clip.get("issues") or []]
    reasons = []
    if any(item in {"click", "discontinuity"} for item in issues):
        reasons.append("click stays unsupported; clip properties cannot write a fade")
    if any(item in {"gap", "silence_gap"} for item in issues):
        reasons.append("gap stays unsupported; missing audio was not replaced")
    if "level_jump" in issues:
        reasons.append("level jump stays unsupported; no dynamics were added")
    return reasons


def _run_level(state, options):
    blocked = _guard(state, "level")
    if blocked:
        return blocked
    changed = []
    readback = {}
    unsupported = []
    skipped = 0
    commands = []
    for track in state.get("tracks") or []:
        if not _selected(track, options) or not _regular(track):
            continue
        if _track_type(track) != "audio":
            skipped += 1
            continue
        for clip in track.get("clips") or []:
            if clip.get("view") not in {None, "arrangement"}:
                skipped += 1
                continue
            target = f"track:{track.get('index')}:clip:{clip.get('index', 0)}"
            for reason in _level_issues(clip):
                unsupported.append({"target": target, "reason": reason})
            wrote = False
            if clip.get("full_scale") and clip.get("gain") is not None:
                decision = gain_decision(clip.get("gain"))
                if decision.get("write") and _clip_label(clip) is None:
                    unsupported.append({"target": target, "reason": "clip name is empty"})
                elif decision.get("write"):
                    previous = clip.get("gain")
                    clip["gain"] = decision["gain"]
                    wrote = True
                    changed.append(
                        {
                            "track_index": track.get("index"),
                            "expected_track_name": track.get("name"),
                            "clip_index": clip.get("index", 0),
                            "field": "gain",
                            "from": previous,
                            "to": decision["gain"],
                        }
                    )
                    commands.append(
                        {
                            "type": "write_access_object",
                            "params": dict(
                                _clip_address(track, clip),
                                object_type="clip",
                                properties={"gain": decision["gain"]},
                            ),
                        }
                    )
                    readback[f"{target}:gain"] = clip["gain"]
            if clip.get("dc_parameters"):
                decision = dc_decision(clip.get("dc_parameters"))
                if decision.get("write"):
                    previous = None
                    for item in clip["dc_parameters"]:
                        if item.get("name") == decision["name"]:
                            previous = item.get("value")
                            item["value"] = decision["value"]
                    wrote = True
                    changed.append(
                        {
                            "track_index": track.get("index"),
                            "expected_track_name": track.get("name"),
                            "clip_index": clip.get("index", 0),
                            "field": "dc",
                            "from": previous,
                            "to": decision["value"],
                        }
                    )
                    readback[f"{target}:dc"] = decision["value"]
            if not wrote and not _level_issues(clip):
                skipped += 1
    _commit(state, commands)
    return _finish("level", changed, readback, unsupported, skipped)


def _reference_track(state, options):
    wanted = options.get("reference")
    audio = [
        track
        for track in state.get("tracks") or []
        if _track_type(track) == "audio" and not is_protected(track.get("name"))
    ]
    if wanted:
        for track in audio:
            if track.get("name") == wanted:
                return track
        return None

    def frames(track):
        total = 0
        for clip in track.get("clips") or []:
            value = clip.get("sample_frames") or clip.get("sample_length") or 0
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += int(value)
        return total

    if not audio:
        return None
    return sorted(audio, key=lambda track: (-frames(track), track.get("index") or 0))[0]


def _run_lock(state, options):
    blocked = _guard(state, "lock")
    if blocked:
        return blocked
    changed = []
    readback = {}
    unsupported = []
    skipped = 0
    commands = []
    reference = _reference_track(state, options)
    if reference is None:
        return _finish(
            "lock",
            [],
            {},
            [{"target": "session", "reason": "no reference audio track"}],
            0,
        )
    for track in state.get("tracks") or []:
        if not _selected(track, options):
            continue
        if is_protected(track.get("name")) or _track_type(track) != "audio":
            skipped += 1
            continue
        if track is reference:
            skipped += 1
            continue
        role = infer_content(track)["role"]
        mode = preferred_mode(role)
        for clip in track.get("clips") or []:
            if clip.get("type") not in {None, "audio"}:
                continue
            target = f"track:{track.get('index')}:clip:{clip.get('index', 0)}"
            if clip.get("warping") is False:
                if clip.get("rendered"):
                    skipped += 1
                else:
                    unsupported.append({"target": target, "reason": WARP_OFF_REASON})
                continue
            if clip.get("warping") is not True:
                unsupported.append({"target": target, "reason": "warp state was not read"})
                continue
            if clip.get("warp_mode") == 3:
                skipped += 1
                continue
            available = clip.get("available_warp_modes")
            resolved = resolve_mode(mode, available)
            if resolved is None:
                unsupported.append(
                    {"target": target, "reason": "preferred warp mode is unavailable"}
                )
                continue
            if clip.get("warp_mode") == resolved:
                skipped += 1
                continue
            if _clip_label(clip) is None:
                unsupported.append({"target": target, "reason": "clip name is empty"})
                continue
            previous = clip.get("warp_mode")
            start = _clip_start(clip)
            clip["warp_mode"] = resolved
            commands.append(
                {
                    "type": "set_access_warp",
                    "params": dict(
                        _clip_address(track, clip),
                        properties={"warp_mode": resolved},
                    ),
                }
            )
            changed.append(
                {
                    "track_index": track.get("index"),
                    "expected_track_name": track.get("name"),
                    "clip_index": clip.get("index", 0),
                    "field": "warp_mode",
                    "from": previous,
                    "to": resolved,
                }
            )
            readback[f"{target}:warp_mode"] = clip["warp_mode"]
            readback[f"{target}:start"] = start
    _commit(state, commands)
    return _finish("lock", changed, readback, unsupported, skipped)


def _set_span(clip, field, value):
    if field == "end":
        for key in ("end", "end_beats", "end_time"):
            if key in clip:
                clip[key] = value
                return
        clip["end"] = value
        return
    clip[field] = value


def _run_frame(state, options):
    blocked = _guard(state, "frame")
    if blocked:
        return blocked
    changed = []
    readback = {}
    unsupported = []
    skipped = 0
    commands = []
    for track in state.get("tracks") or []:
        if not _selected(track, options):
            continue
        if not _regular(track):
            skipped += 1
            continue
        clips = list(track.get("clips") or [])
        for clip in clips:
            units = _units_of(clip)
            target = f"track:{track.get('index')}:clip:{clip.get('index', 0)}"
            if units is None:
                unsupported.append({"target": target, "reason": "time units were not read"})
                continue
            bar, tolerance = _bar(state, units)
            fields = []
            for field in ("loop_start", "loop_end", "end_marker"):
                current = clip.get(field)
                if isinstance(current, bool) or not isinstance(current, (int, float)):
                    continue
                snapped = _snap(current, bar, tolerance)
                if snapped <= 0 and field != "loop_start":
                    snapped = bar
                if float(current) != float(snapped):
                    fields.append((field, float(current), float(snapped)))
            fields = _keep_loop_order(clip, fields, bar)
            if not fields:
                skipped += 1
                continue
            if _clip_label(clip) is None:
                unsupported.append({"target": target, "reason": "clip name is empty"})
                continue
            for field, previous, snapped in fields:
                _set_span(clip, field, snapped)
                changed.append(
                    {
                        "track_index": track.get("index"),
                        "expected_track_name": track.get("name"),
                        "clip_index": clip.get("index", 0),
                        "field": field,
                        "from": previous,
                        "to": snapped,
                        "units": units,
                    }
                )
                readback[f"{target}:{field}"] = snapped
            commands.append(
                {
                    "type": "write_access_object",
                    "params": dict(
                        _clip_address(track, clip),
                        object_type="clip",
                        properties={field: clip.get(field) for field, _, _ in fields},
                    ),
                }
            )
        arranged = [clip for clip in track.get("clips") or [] if clip.get("view") == "arrangement"]
        arranged.sort(key=lambda clip: (_clip_start(clip), clip.get("index") or 0))
        for earlier, later in zip(arranged, arranged[1:]):
            if _units_of(earlier) != _units_of(later) or _units_of(earlier) is None:
                continue
            start_a, end_a = _clip_start(earlier), _clip_end(earlier)
            start_b, end_b = _clip_start(later), _clip_end(later)
            if None in (end_a, end_b):
                continue
            if not overlaps(start_a, end_a, start_b, end_b):
                continue
            previous = end_a
            _set_span(earlier, "end", start_b)
            if "loop_end" in earlier:
                earlier["loop_end"] = start_b
            changed.append(
                {
                    "track_index": track.get("index"),
                    "expected_track_name": track.get("name"),
                    "clip_index": earlier.get("index", 0),
                    "field": "loop_end",
                    "from": previous,
                    "to": start_b,
                    "units": _units_of(earlier),
                }
            )
            readback[f"track:{track.get('index')}:clip:{earlier.get('index', 0)}:loop_end"] = (
                start_b
            )
    _commit(state, commands)
    return _finish("frame", changed, readback, unsupported, skipped)


def _sections(state, options):
    explicit = options.get("sections")
    if explicit:
        return list(explicit)
    energy = state.get("energy")
    reference = _reference_track(state, options)
    if energy is None and reference is not None:
        energy = reference.get("energy")
    if not energy:
        return []
    boundaries = [float(energy[0].get("time") or 0)]
    previous = energy[0].get("level") or 0
    for point in energy[1:]:
        level = point.get("level") or 0
        if abs(level - previous) >= 0.2:
            boundaries.append(float(point.get("time") or 0))
        previous = level
    return [
        {"name": SECTION_NAMES[index], "time": beat}
        for index, beat in enumerate(boundaries[: len(SECTION_NAMES)])
    ]


def _run_map(state, options):
    blocked = _guard(state, "map")
    if blocked:
        return blocked
    caps = state.get("capabilities")
    if isinstance(caps, (list, tuple, set)) and "create_locator" not in caps:
        return _refused("map", "create_locator is not loaded on this bridge")
    planned = _sections(state, options)
    if not planned:
        return _finish("map", [], {}, [], 0)
    changed = []
    readback = {}
    unsupported = []
    skipped = 0
    commands = []
    locators = state.setdefault("locators", [])
    names = {item.get("name") for item in locators}
    times = [float(item.get("time") or 0) for item in locators]
    for section in planned:
        name = section.get("name")
        beat = float(section.get("time") or 0)
        if name in names or any(abs(beat - existing) <= 0.001 for existing in times):
            skipped += 1
            continue
        locators.append({"name": name, "time": beat})
        names.add(name)
        times.append(beat)
        commands.append({"type": "create_locator", "params": {"name": name, "time": beat}})
        changed.append(
            {
                "field": "locator",
                "from": None,
                "to": name,
                "time": beat,
            }
        )
        readback[f"locator:{name}"] = beat
    _commit(state, commands)
    return _finish("map", changed, readback, unsupported, skipped)


def _run_check(state, options):
    from .song_lint import lint_state

    before = len(state.get("writes") or [])
    try:
        report = lint_state(state, {"lint": options.get("lint") or {}})
    except Exception:
        result = _finish("check", [], {}, [], 0)
        result["exit_code"] = 0
        return result
    if len(state.get("writes") or []) != before:
        del state.get("writes")[before:]
    code = int(report.get("exitCode") or 0)
    thin = not state.get("source")
    if thin and code == 2:
        result = _finish("check", [], {}, [], 0)
        result["exit_code"] = 0
        return result
    status = "unchanged" if code == 0 else "partial" if code == 1 else "refused"
    result = _result("check", status, [], {}, [], 0)
    result["exit_code"] = code
    result["lint"] = {
        "exitCode": code,
        "status": report.get("status"),
        "findings": len(report.get("findings") or []),
    }
    return result


_RUNNERS = {
    "adopt": _run_adopt,
    "name": _run_name,
    "label": _run_label,
    "voice": _run_voice,
    "level": _run_level,
    "lock": _run_lock,
    "frame": _run_frame,
    "map": _run_map,
    "check": _run_check,
}


def _open(source):
    if isinstance(source, dict):
        source.setdefault("writes", [])
        source.setdefault("tracks", [])
        return source
    if not callable(source):
        raise TypeError("source must be a state dict or a Live dispatch callable")
    from .song_lint import collect_live

    class _Connection:
        def send_command(self, kind, params):
            return source(kind, params or {})

    raw = collect_live(_Connection(), include_session=True)
    info = source("get_script_info", {})
    raw["capabilities"] = list(info.get("capabilities") or [])
    raw["writes"] = []
    raw["_dispatch"] = source
    raw.setdefault("locators", [])
    return raw


def run(op_id, source, options=None):
    """Run one op. A dict is mutated. ``plan`` mutates only a copy."""

    options = dict(options or {})
    if op_id not in _RUNNERS:
        raise ValueError(f"unknown op: {op_id}")
    state = _open(source)
    if options.get("plan"):
        shadow = deepcopy({key: value for key, value in state.items() if key != "_dispatch"})
        result = _RUNNERS[op_id](shadow, dict(options, plan=False))
        if result["status"] != "refused":
            result["status"] = "planned"
        return result
    return _RUNNERS[op_id](state, options)


def run_all(source, options=None):
    """Run every op in order on one state. Skipped ids are omitted."""

    options = dict(options or {})
    skip = set()
    raw_skip = options.get("skip") or []
    if isinstance(raw_skip, str):
        raw_skip = [part for part in raw_skip.split(",") if part.strip()]
    for item in raw_skip:
        resolved = resolve(item) or str(item).strip()
        skip.add(resolved)
    planning = bool(options.get("plan"))
    state = _open(source)
    if planning:
        state = deepcopy({key: value for key, value in state.items() if key != "_dispatch"})
    step_options = dict(options, plan=False)
    results = []
    for op in OPS:
        if op["id"] in skip:
            continue
        result = _RUNNERS[op["id"]](state, step_options)
        if planning and result["status"] != "refused":
            result["status"] = "planned"
        results.append(result)
        dispatch = state.get("_dispatch")
        # Recapture only after an op that actually wrote. A skipped or unchanged
        # op cannot have moved Live, so re-reading the whole set is pure cost.
        if dispatch is not None and not planning and result.get("changed"):
            kept = list(state.get("writes") or [])
            fresh = _open(dispatch)
            state.clear()
            state.update(fresh)
            state["writes"] = kept
    return results


def process_exit(payload):
    rows = payload if isinstance(payload, list) else [payload]
    code = 0
    for row in rows:
        if row.get("op") == "check" and "exit_code" in row:
            code = max(code, int(row["exit_code"]))
            continue
        status = row.get("status")
        if status == "partial":
            code = max(code, 1)
        elif status in {"refused", "error"}:
            code = max(code, 2)
    return code


def handoff(request):
    """Two lines and exit 0. This does not call Live and does not invent an edit."""

    text = str(request).strip()
    print(text)
    print(f"Hand this to your assistant: {text} (MCP server EnAbleton)")
    return 0


def _parser():
    parser = argparse.ArgumentParser(prog="enableton", add_help=False)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--track", action="append", default=[])
    parser.add_argument("--clip", action="append", default=[])
    parser.add_argument("--reference")
    parser.add_argument("--skip", default="")
    parser.add_argument("--section", action="append", default=[])
    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--rules", action="append", default=[])
    parser.add_argument("--config", type=Path)
    parser.add_argument("extra", nargs="*")
    return parser


def _options_from(args):
    tracks = []
    for item in args.track:
        if str(item).isdigit():
            tracks.append(int(item))
    sections = []
    for item in args.section:
        name, _, raw = str(item).partition("=")
        sections.append({"name": name.strip(), "time": float(raw)})
    return {
        "plan": bool(args.plan),
        "tracks": tracks,
        "reference": args.reference,
        "skip": args.skip,
        "sections": sections,
    }


def _source_from(args):
    if args.snapshot:
        return json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    from .server import dispatch

    return dispatch


def _emit(payload, report):
    raw = json.dumps(payload, indent=2, allow_nan=False)
    if report is not None:
        path = Path(report)
        if path.exists() or not path.parent.is_dir():
            raise ValueError("Report parent must exist and report path must be new")
        path.write_text(raw + "\n", encoding="utf-8")
    print(raw)


def _execute(op_ids, args):
    options = _options_from(args)
    source = _source_from(args)
    if op_ids == ["all"]:
        payload = run_all(source, options)
    elif len(op_ids) == 1:
        payload = run(op_ids[0], source, options)
    else:
        payload = [run(op_id, source, options) for op_id in op_ids]
    _emit(payload, args.report)
    return process_exit(payload)


def route(argv=None):
    """Return an exit code, or None when the legacy parser owns ``argv``."""

    if argv is None:
        argv = sys.argv[1:]
    argv = list(argv)
    if not argv:
        from .song_start import run as start

        return start(None)
    head = argv[0]
    if head in {"-h", "--help", "--version"} or head in _LEGACY:
        return None
    if head == "start":
        from .song_start import run as start

        return start(argv[1:])
    if head == "list":
        public = [
            {
                key: op[key]
                for key in ("id", "title", "writes", "phase", "needs", "idempotent", "words")
            }
            for op in OPS
        ]
        print(json.dumps(public, indent=2))
        return 0
    if head == "prep":
        return _workspace(argv[1:])
    if head == "lint":
        print(_DEPRECATED_LINE["lint"], file=sys.stderr)
        from .song_init import main as workflow_main

        extra = [] if "--lint" in argv[1:] else ["--lint"]
        return workflow_main(argv[1:] + extra)
    if head in _DEPRECATED:
        print(_DEPRECATED_LINE[head], file=sys.stderr)
        try:
            args = _parser().parse_args(argv[1:])
            return _execute(list(_DEPRECATED[head]), args)
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            print(json.dumps({"error": str(error)}), file=sys.stderr)
            return 2
    if head == "all" or resolve(head):
        try:
            args = _parser().parse_args(argv[1:])
            op_ids = ["all"] if head == "all" else [resolve(head)]
            return _execute(op_ids, args)
        except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
            print(json.dumps({"error": str(error)}), file=sys.stderr)
            return 2
    return handoff(" ".join(argv))


def _workspace(argv):
    parser = argparse.ArgumentParser(prog="enableton prep workspace")
    parser.add_argument("kind", nargs="?", choices=("workspace",))
    parser.add_argument("--song-root", required=True)
    parser.add_argument("--song-name", required=True)
    parser.add_argument("--plan", action="store_true")
    try:
        args = parser.parse_args(argv)
    except SystemExit as escaped:
        return int(escaped.code or 2)
    if args.kind not in {None, "workspace"}:
        print(
            json.dumps({"error": "prep workspace is the only optional prep step"}), file=sys.stderr
        )
        return 2
    from .song_init import create_folder, song_folder

    spec = song_folder({"root": args.song_root, "name": args.song_name, "onExists": "error"})
    if args.plan:
        print(json.dumps({"op": "workspace", "status": "planned", "live_changes": False}, indent=2))
        return 0
    create_folder(spec)
    print(json.dumps({"op": "workspace", "status": "applied", "path": spec["path"]}, indent=2))
    return 0


def _register_processes():
    def _make(op_id):
        @register(f"prep_{op_id}")
        def _process(state, params, target):
            return Result()

        return _process

    for op_id in _ORDER:
        _make(op_id)


_register_processes()
