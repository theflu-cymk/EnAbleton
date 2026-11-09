"""Place a stock placeholder on MIDI tracks that have notes and no instrument.

The placeholder is there so the part can be heard. It is not a finished sound,
and an instrument that is already loaded, including an unknown plug-in, is left
alone. An empty Drum Rack is not used: it would stay silent. Notes, Warp and
faders are not changed, and playback is not started.
"""

import time

from .align_safety import is_protected
from .track_prep import infer_content

POLL_ATTEMPTS = 12
POLL_SECONDS = 0.15
_INTERNAL_OUTPUT = {"", "no output", "none", "main", "master", "sends only"}
_EFFECT_NAMES = {
    "align delay",
    "amp",
    "arpeggiator",
    "audio effect rack",
    "auto filter",
    "auto pan",
    "beat repeat",
    "cabinet",
    "channel eq",
    "chord",
    "chorus",
    "chorus-ensemble",
    "compressor",
    "corpus",
    "delay",
    "drum buss",
    "dynamic tube",
    "echo",
    "eq eight",
    "eq three",
    "erosion",
    "external audio effect",
    "filter delay",
    "flanger",
    "frequency shifter",
    "gate",
    "glue compressor",
    "grain delay",
    "hybrid reverb",
    "limiter",
    "looper",
    "midi effect rack",
    "multiband dynamics",
    "note length",
    "overdrive",
    "pedal",
    "phaser",
    "phaser-flanger",
    "pitch",
    "random",
    "redux",
    "resonator",
    "reverb",
    "roar",
    "saturator",
    "scale",
    "shaper",
    "shifter",
    "spectral resonator",
    "spectral time",
    "spectrum",
    "tuner",
    "utility",
    "velocity",
    "vinyl distortion",
    "vocoder",
}
_INSTRUMENT_TYPES = {"instrument", "drum_machine", "unknown", "plugin"}
_EFFECT_TYPES = {"audio_effect", "midi_effect"}
_ROLES = {
    "reference",
    "fx",
    "bg_vox",
    "lead_vox",
    "percussion",
    "woodwinds",
    "strings",
    "drums",
    "bass",
    "guitar",
    "keys",
    "synth",
    "other",
}

PLACEHOLDER_REASON = (
    "Placeholder so the part can be heard. Replace it with the instrument you want."
)
CHOICES = {
    "drums": "Impulse. An empty Drum Rack is silent.",
    "percussion": "Impulse. An empty Drum Rack is silent.",
    "bass": "Operator",
    "keys": "Electric, then Wavetable if Electric is not installed",
    "other": "Wavetable",
}


def candidates_for(role):
    """Stock browser names, in the order they should be tried. Category is instruments."""

    if role in {"drums", "percussion"}:
        return ("Impulse",)
    if role == "bass":
        return ("Operator",)
    if role == "keys":
        return ("Electric", "Wavetable")
    return ("Wavetable",)


def _device_rows(devices):
    rows = []
    for device in devices or []:
        if isinstance(device, str):
            rows.append({"name": device, "class_name": "", "type": ""})
        elif isinstance(device, dict):
            rows.append(device)
    return rows


def _name_blocks_assignment(name):
    key = str(name or "").casefold().strip()
    if not key:
        return False
    if key in _EFFECT_NAMES or "audio effect" in key or "midi effect" in key:
        return False
    return True


def has_instrument(devices):
    """True when the chain already has something that can sound the notes.

    Audio and MIDI effects do not count. A rack counts only when its class or
    type says it is an instrument or a drum machine. An unknown or plug-in
    device counts, so a placeholder is not stacked on Serum or a missing class.
    """

    for device in _device_rows(devices):
        kind = str(device.get("type") or "").casefold()
        class_name = str(device.get("class_name") or "").casefold()
        if kind in _INSTRUMENT_TYPES:
            return True
        if "instrument" in class_name or "plugin" in class_name or "drumgroup" in class_name:
            return True
        if kind in _EFFECT_TYPES or kind == "rack":
            continue
        if _name_blocks_assignment(device.get("name")):
            return True
    return False


def _active_notes(track):
    notes = []
    for clip in track.get("clips") or []:
        if clip.get("type") not in (None, "midi"):
            continue
        for note in clip.get("notes") or []:
            if isinstance(note, dict) and not note.get("mute"):
                notes.append(note)
    return notes


def _routing_state(track, track_names):
    """Return (skip, label). Main and other tracks are not hardware outputs.

    Live reports ``Main`` for a MIDI track whose audio goes to the mix. That is
    the normal destination, so it does not block a placeholder. A name that
    matches neither an internal destination nor a track in the set is treated
    as an external port.
    """

    if "midi_output" not in track:
        return False, "not confirmed"
    output = track.get("midi_output")
    if output is None:
        return False, "not confirmed"
    text = str(output).strip()
    folded = text.casefold()
    if folded in _INTERNAL_OUTPUT or folded in track_names:
        return False, text or "no output"
    return True, text


def plan_assignments(tracks):
    """Choose placeholders. No Live calls and no device loads."""

    if not isinstance(tracks, list):
        raise ValueError("tracks must be a list")
    chosen = []
    skipped = []
    track_names = {str(track.get("name") or "").strip().casefold() for track in tracks}
    track_names.discard("")
    for track in tracks:
        name = str(track.get("name") or "")
        index = track.get("index")
        if is_protected(name):
            skipped.append({"index": index, "name": name, "reason": "already an original"})
            continue
        if track.get("is_return") or track.get("is_master") or track.get("is_group"):
            skipped.append({"index": index, "name": name, "reason": "return, main or group"})
            continue
        if track.get("is_frozen"):
            skipped.append({"index": index, "name": name, "reason": "track is frozen"})
            continue
        if track.get("type") not in (None, "midi"):
            skipped.append({"index": index, "name": name, "reason": "not a MIDI track"})
            continue
        if not _active_notes(track):
            skipped.append({"index": index, "name": name, "reason": "no active notes"})
            continue
        routed, routing = _routing_state(track, track_names)
        if routed:
            skipped.append(
                {
                    "index": index,
                    "name": name,
                    "reason": "MIDI output is routed away from this track",
                    "midi_output": routing,
                }
            )
            continue
        if has_instrument(track.get("devices")):
            skipped.append({"index": index, "name": name, "reason": "already has an instrument"})
            continue
        content = infer_content(track)
        role = content["role"]
        chosen.append(
            {
                "status": "assign",
                "track_index": index,
                "track_name": name,
                "role": role,
                "evidence": content["evidence"],
                "candidates": list(candidates_for(role)),
                "category": "instruments",
                "routing": routing,
                "reason": PLACEHOLDER_REASON,
            }
        )
    return {
        "method": "assign-instruments",
        "live_changes": False,
        "playback_started": False,
        "choices": dict(CHOICES),
        "writes": ["load one stock placeholder instrument on a MIDI track that has none"],
        "leaves_unchanged": [
            "existing instruments",
            "notes",
            "warp",
            "faders",
            "audio tracks",
            "originals",
            "returns",
            "groups",
        ],
        "tracks": chosen,
        "skipped": skipped,
    }


def tracks_from_capture(state):
    """Adapt a lint capture. Session clips are not part of this plan."""

    rows = []
    for track in state.get("tracks") or []:
        clips = []
        for clip in track.get("clips") or []:
            if clip.get("protected"):
                continue
            locator = clip.get("locator") or {}
            clips.append(
                {
                    "name": clip.get("name") or "",
                    "view": clip.get("view"),
                    "index": locator.get("clip_index", 0),
                    "start_beats": clip.get("start_beats"),
                    "type": clip.get("type"),
                    "notes": clip.get("notes") or [],
                }
            )
        rows.append(
            {
                "index": track.get("index"),
                "name": track.get("name") or "",
                "type": track.get("type"),
                "is_group": bool(track.get("is_group")),
                "is_return": bool(track.get("is_return")),
                "is_master": bool(track.get("is_master")),
                "is_frozen": bool(track.get("is_frozen")),
                "devices": track.get("devices") or [],
                "clips": clips,
            }
        )
    return rows


def _output_name(routing):
    if not isinstance(routing, dict) or "output_routing_type" not in routing:
        return None
    field = routing.get("output_routing_type")
    if field is None:
        return ""
    if isinstance(field, dict):
        return str(field.get("display_name") or "")
    if isinstance(field, str):
        return field
    return None


def _require_stopped(send):
    session = send("get_session_info", {})
    if session.get("is_playing") or session.get("record_mode"):
        raise ValueError("Stop playback and recording before assigning instruments")


def _index(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(label + " is missing")
    return value


def resolve_browser_item(send, category, name):
    """Return the URI only when exactly one loadable item has this name."""

    data = send("get_browser_items_at_path", {"path": category})
    matches = [
        item
        for item in data.get("items") or []
        if item.get("name") == name and item.get("is_loadable") and item.get("uri")
    ]
    if len(matches) != 1:
        return None
    return matches[0]["uri"]


def _load_device(send, track_index, track_name, uri, device_name, before_count, sleeper):
    send("load_browser_item", {"track_index": track_index, "item_uri": uri})
    for _attempt in range(POLL_ATTEMPTS):
        seen = send("get_track_info", {"track_index": track_index})
        if seen.get("name") != track_name:
            raise RuntimeError("Track changed while loading. Inspect it before loading again.")
        devices = seen.get("devices") or []
        if len(devices) == before_count + 1 and devices[-1].get("name") == device_name:
            return devices[-1]
        sleeper(POLL_SECONDS)
    raise RuntimeError(
        device_name
        + " was not confirmed on "
        + track_name
        + ". Inspect that track before loading it again. Earlier tracks in this "
        "apply may already have changed; each load is its own undo."
    )


def apply_plan(send, plan, confirm=True, sleeper=None):
    """Load the planned placeholders. One device at a time."""

    if confirm is not True:
        preview = dict(plan)
        preview["applied"] = False
        preview["live_changes"] = False
        preview["playback_started"] = False
        return preview
    if sleeper is None:
        sleeper = time.sleep
    _require_stopped(send)
    results = []
    not_applied = []
    for action in plan.get("tracks") or []:
        if action.get("status") != "assign":
            not_applied.append(action)
            continue
        _require_stopped(send)
        index = _index(action.get("track_index"), "track index")
        expected = action.get("track_name")
        fresh = send("get_track_info", {"track_index": index})
        if fresh.get("name") != expected:
            raise RuntimeError("track changed before assign; nothing was loaded on it")
        if fresh.get("is_frozen"):
            not_applied.append({**action, "reason": "track is frozen"})
            continue
        if has_instrument(fresh.get("devices")):
            not_applied.append({**action, "reason": "already has an instrument"})
            continue
        role = action.get("role")
        if role not in _ROLES:
            not_applied.append({**action, "reason": "role is not recognized"})
            continue
        loaded_name = None
        uri = None
        for name in candidates_for(role):
            uri = resolve_browser_item(send, "instruments", name)
            if uri:
                loaded_name = name
                break
        if uri is None:
            not_applied.append(
                {
                    **action,
                    "reason": "stock placeholder is not available: "
                    + ", ".join(candidates_for(role)),
                }
            )
            continue
        before = len(fresh.get("devices") or [])
        device = _load_device(send, index, expected, uri, loaded_name, before, sleeper)
        results.append(
            {
                "track_index": index,
                "track_name": expected,
                "role": role,
                "device_name": device.get("name"),
                "message": PLACEHOLDER_REASON,
            }
        )
    return {
        "method": "assign-instruments",
        "applied": True,
        "live_changes": bool(results),
        "playback_started": False,
        "results": results,
        "not_applied": not_applied,
        "skipped": plan.get("skipped") or [],
        "undo": "Each device load is its own undo step, from the last load backward.",
    }


def plan_live(send):
    from .song_lint import collect_live

    state = collect_live(include_session=False)
    rows = tracks_from_capture(state)
    unconfirmed = False
    for row in rows:
        if row["type"] != "midi" or row["is_group"] or row["is_return"] or row["is_master"]:
            continue
        if is_protected(row["name"]) or row["is_frozen"]:
            continue
        try:
            output = _output_name(send("get_track_routing", {"track_index": row["index"]}))
        except (OSError, RuntimeError, ValueError, KeyError, TypeError):
            output = None
        if output is None:
            unconfirmed = True
        else:
            row["midi_output"] = output
    plan = plan_assignments(rows)
    plan["captured_tracks"] = len(state.get("tracks") or [])
    plan["capture_errors"] = state.get("capture_errors") or []
    plan["routing_unconfirmed"] = unconfirmed
    return plan


def apply_live(send, confirm=True):
    if confirm is not True:
        plan = plan_live(send)
        plan["applied"] = False
        plan["live_changes"] = False
        return plan
    _require_stopped(send)
    applied = apply_plan(send, plan_live(send), confirm=True)
    applied["method"] = "assign-instruments"
    return applied


def register_instruments(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def plan_instrument_assignment() -> dict:
        """Optional preview of a stock placeholder for each MIDI track that has notes
        and no instrument. Does not replace a loaded instrument, including an unknown
        plug-in. Does not write or start playback.
        """
        return plan_live(dispatch)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def apply_instrument_assignment(confirm: bool = True) -> dict:
        """Load a stock placeholder on each MIDI track that still has notes and no
        instrument. Writes unless confirm is false. Refuses while playing or recording.
        The placeholder is there so the part can be heard; replace it. Does not change
        notes, Warp, or faders.
        """
        return apply_live(dispatch, confirm=confirm)
