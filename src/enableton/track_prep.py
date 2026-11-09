"""Prepare a new song's tracks for editing.

Lint reports problems and initiate applies a conservative preset. Neither one
parks an untouched copy before renaming. This planner does four things:

- name each working track from its content, not from a leftover ``Track 1``
- color that track by the inferred role
- duplicate it first, then mute the copy and name it ``ORIGINAL | ...``
- fold that original when Live can (group tracks only)

Notes, Warp, faders and Arrangement positions are not changed. Returns, the
Main track and group tracks are left alone. A regular track has no fold
property, so the original is muted and the fold is reported instead of faked.
"""

import re
from pathlib import Path

from .align_safety import base_name, is_protected, protection_name
from .layer_naming import ROLE_COLORS, ROLE_LABELS

ARCHIVE_COLOR = 13
GENERIC_CLIPS = {"", "track 1", "audio", "midi", "clip", "untitled"}
FOLD_LIMIT = (
    "Live can fold a group track only. This original is not a group, so it was "
    "muted and left unfolded."
)

EXTRA_COLORS = {"reference": 14, "fx": 9}
EXTRA_LABELS = {"reference": "Reference", "fx": "FX"}

# Name and filename phrases. Product names stay in the detail; generic role
# words are removed from it below.
_TEXT_ROLES = (
    ("reference", ("instrumental", "full mix", "mixdown", "reference")),
    ("fx", ("riser", "impact", "sfx")),
    ("bg_vox", ("backing", "bgv", "bg vox", "harmon")),
    ("lead_vox", ("vocals", "vocal", "vox")),
    ("percussion", ("shaker", "tamb")),
    ("woodwinds", ("flute", "sax", "clarinet")),
    ("strings", ("violin", "cello", "viola")),
    ("drums", ("drums", "drum", "kick", "snare", "clap", "kit", "beat")),
    ("bass", ("bass", "sub")),
    ("guitar", ("guitar", "gtr")),
    ("keys", ("piano", "organ", "rhodes")),
    ("synth", ("synth", "serum", "hive", "vital", "massive", "wavetable", "operator")),
    ("fx", ("fx",)),
)

_DEVICE_ROLES = (
    ("drums", ("drum rack", "drum sampler", "impulse")),
    ("keys", ("piano", "electric piano")),
    ("synth", ("serum", "hive", "vital", "massive", "wavetable", "operator", "analog")),
)

_ROLE_WORDS = {
    "reference": ("instrumental", "mixdown", "reference"),
    "fx": ("riser", "impact", "sfx", "fx"),
    "bg_vox": ("backing", "bgv", "harmon"),
    "lead_vox": ("vocal", "vocals", "vox"),
    "percussion": ("percussion", "perc", "shaker"),
    "woodwinds": ("woodwind", "woodwinds", "flute", "sax"),
    "strings": ("string", "strings", "violin", "cello"),
    "drums": ("drum", "drums", "kit", "beat", "kick", "snare"),
    "bass": ("bass", "sub"),
    "guitar": ("guitar", "gtr"),
    "keys": ("key", "keys", "piano", "organ", "rhodes"),
    "synth": ("synth",),
    "other": ("other",),
}

_PREFIX = re.compile(r"^\d+\s*[-.:]\s*")
_BPM = re.compile(r"\b\d{2,3}\s*bpm\b", re.IGNORECASE)
_KEY = re.compile(r"\b(?:key\s*)?[A-G](?:#|b)?(?:min|maj|m)\b", re.IGNORECASE)
_NOISE = re.compile(
    r"\b(?:loops?|one[\s-]?shots?|audio|midi|tracks?|full)\b",
    re.IGNORECASE,
)
_SKU = re.compile(r"\b(?=[A-Za-z]+\d|\d+[A-Za-z])[A-Za-z0-9]{5,}\b")
_DRUM_PITCHES = {35, 36, 37, 38, 39, 40, 42, 44, 46, 49, 51}


def role_label(role):
    return EXTRA_LABELS.get(role) or ROLE_LABELS.get(role, ROLE_LABELS["other"])


def role_color(role):
    if role in EXTRA_COLORS:
        return EXTRA_COLORS[role]
    return ROLE_COLORS.get(role, ROLE_COLORS["other"])


def _contains(text, phrase):
    return re.search(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])", text) is not None


def _role_in(text):
    key = (text or "").casefold()
    for role, phrases in _TEXT_ROLES:
        if any(_contains(key, phrase) for phrase in phrases):
            return role
    return None


def tidy(text):
    """Turn a filename or numbered stem into a short readable label."""

    raw = str(text or "").replace("_", " ").replace("+", " ").replace("|", " ")
    raw = _PREFIX.sub("", raw.strip())
    raw = _BPM.sub(" ", raw)
    raw = _KEY.sub(" ", raw)
    raw = _NOISE.sub(" ", raw)
    raw = _SKU.sub(" ", raw)
    raw = re.sub(r"[^A-Za-z0-9# ]", " ", raw)
    parts = []
    for part in raw.split():
        if (part.isdigit() and len(part) >= 3) or (part.isupper() and len(part) > 3):
            continue
        parts.append(part.capitalize() if part.isalpha() else part)
    return " ".join(parts).strip()


def _strip_role_words(text, role):
    cleaned = text
    for word in _ROLE_WORDS.get(role, ()):
        cleaned = re.sub(
            rf"(?<![A-Za-z0-9]){re.escape(word)}(?![A-Za-z0-9])", " ", cleaned, flags=re.I
        )
    return " ".join(cleaned.split())


def _file_stem(clip):
    path = clip.get("audio_path") or ""
    if not path:
        return ""
    return Path(path).stem


def _devices(track):
    names = []
    for device in track.get("devices") or []:
        if isinstance(device, str) and device.strip():
            names.append(device.strip())
        elif isinstance(device, dict) and str(device.get("name") or "").strip():
            names.append(str(device["name"]).strip())
    return names


def _midi_role(notes):
    active = [note for note in notes or [] if not note.get("mute")]
    if len(active) < 8:
        return None, ""
    pitches = []
    for note in active:
        try:
            pitches.append(int(note["pitch"]))
        except (KeyError, TypeError, ValueError):
            return None, ""
    drum_share = sum(pitch in _DRUM_PITCHES for pitch in pitches) / len(pitches)
    short = sum(float(note.get("duration", 1) or 1) <= 0.5 for note in active) / len(active)
    if drum_share >= 0.75 and short >= 0.6:
        return "drums", "MIDI pitches match a drum kit"
    buckets = {}
    for note, pitch in zip(active, pitches):
        try:
            start = round(float(note["start_time"]), 2)
        except (KeyError, TypeError, ValueError):
            continue
        buckets.setdefault(start, set()).add(pitch)
    chords = sum(len(group) >= 3 for group in buckets.values())
    ordered = sorted(pitches)
    median = ordered[len(ordered) // 2]
    span = ordered[-1] - ordered[0]
    if chords >= 2 and span >= 12:
        return "keys", "MIDI notes stack into chords"
    if median <= 48 and span <= 18:
        return "bass", "MIDI notes sit in the bass register"
    return None, ""


def infer_content(track):
    """Role, detail and evidence for one regular track. Does not rename it."""

    texts = [track.get("name") or ""]
    texts.extend(clip.get("name") or "" for clip in track.get("clips") or [])
    texts.extend(_file_stem(clip) for clip in track.get("clips") or [])
    role = None
    evidence = ""
    for text in texts:
        found = _role_in(text)
        if found:
            role = found
            evidence = "name mentions " + found.replace("_", " ")
            break
    if role is None:
        for device in _devices(track):
            key = device.casefold()
            for candidate, phrases in _DEVICE_ROLES:
                if any(phrase in key for phrase in phrases):
                    role = candidate
                    evidence = "device " + device
                    break
            if role:
                break
    if role is None:
        notes = [
            note
            for clip in track.get("clips") or []
            if clip.get("type") == "midi"
            for note in clip.get("notes") or []
        ]
        role, evidence = _midi_role(notes)
    if role is None:
        role = "other"
        evidence = evidence or "no role keyword, device or pitch pattern"
    if role == "other":
        detail = tidy(track.get("name") or "")[:42]
    else:
        detail = ""
        for text in [track.get("name") or "", *_devices(track)]:
            cleaned = tidy(text)
            stripped = _strip_role_words(cleaned, role)
            if len(stripped) >= 3 and stripped.casefold() != role_label(role).casefold():
                detail = stripped[:42]
                break
    return {"role": role, "detail": detail, "evidence": evidence, "confidence": evidence}


def _generic_clip(name):
    return str(name or "").strip().casefold() in GENERIC_CLIPS


def _drop_shared_suffix(rows):
    """Drop one trailing word shared by several tracks, such as the song title.

    A role that already has a label may lose that word entirely. A track whose
    only identity is that word keeps it, so it does not collapse to Other.
    """

    suffixes = []
    for _role, detail in rows:
        parts = detail.split()
        if parts:
            suffixes.append(parts[-1].casefold())
    if len(suffixes) < 3:
        return [detail for _role, detail in rows]
    word = max(set(suffixes), key=suffixes.count)
    if suffixes.count(word) < 3:
        return [detail for _role, detail in rows]
    updated = []
    for role, detail in rows:
        parts = detail.split()
        if parts and parts[-1].casefold() == word and (role != "other" or len(parts) > 1):
            parts = parts[:-1]
        updated.append(" ".join(parts))
    return updated


def plan_tracks(tracks):
    """Plan content names and muted originals. No Live calls."""

    if not isinstance(tracks, list):
        raise ValueError("tracks must be a list")
    names = {str(track.get("name") or "") for track in tracks}
    chosen = []
    skipped = []
    for track in tracks:
        name = str(track.get("name") or "")
        index = track.get("index")
        if is_protected(name):
            skipped.append({"index": index, "name": name, "reason": "already an original"})
            continue
        if track.get("is_return") or track.get("is_master") or track.get("is_group"):
            skipped.append({"index": index, "name": name, "reason": "return, main or group"})
            continue
        clips = track.get("clips") or []
        if not clips and not _devices(track):
            skipped.append({"index": index, "name": name, "reason": "no clips or devices"})
            continue
        content = infer_content(track)
        chosen.append((track, content))
    details = _drop_shared_suffix([(content["role"], content["detail"]) for _, content in chosen])
    actions = []
    order = 0
    for (track, content), detail in zip(chosen, details):
        order += 1
        label = role_label(content["role"]) if content["role"] != "other" else (detail or "Other")
        if content["role"] != "other" and detail:
            label = role_label(content["role"]) + " | " + detail
        working = f"{order:02d} {label}"[:80]
        original = protection_name(working)
        clip_renames = []
        for clip in track.get("clips") or []:
            if clip.get("view") not in (None, "arrangement"):
                continue
            if not str(clip.get("name") or "").strip() or not _generic_clip(clip.get("name")):
                continue
            if clip.get("start_beats", clip.get("start_time")) is None:
                continue
            clip_renames.append(
                {
                    "clip_index": clip.get("index", clip.get("clip_index", 0)),
                    "expected_name": clip.get("name") or "",
                    "start_beats": clip.get("start_beats", clip.get("start_time")),
                    "name": working,
                }
            )
        current = str(track.get("name") or "")
        if current == working and original in names:
            status = "ready"
        elif original in names:
            status = "conflict"
        else:
            status = "prepare"
        actions.append(
            {
                "status": status,
                "source_index": track.get("index"),
                "source_name": current,
                "role": content["role"],
                "evidence": content["evidence"],
                "working_name": working,
                "color_index": role_color(content["role"]),
                "original_name": original,
                "original_color": ARCHIVE_COLOR,
                "clip_renames": clip_renames,
            }
        )
    return {
        "method": "prepare-tracks",
        "live_changes": False,
        "playback_started": False,
        "writes": [
            "rename the working track from its content",
            "color the working track by role",
            "mute the untouched original",
            "fold a group original",
        ],
        "leaves_unchanged": [
            "notes",
            "warp",
            "faders",
            "arrangement positions",
            "returns",
            "groups",
        ],
        "fold_limit": FOLD_LIMIT,
        "tracks": actions,
        "skipped": skipped,
    }


def tracks_from_capture(state):
    """Adapt a lint capture to the planner. Session originals are not renamed."""

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
                    "audio_path": clip.get("audio_path"),
                    "notes": clip.get("notes") or [],
                }
            )
        rows.append(
            {
                "index": track.get("index"),
                "name": track.get("name") or "",
                "is_group": bool(track.get("is_group")),
                "is_return": bool(track.get("is_return")),
                "is_master": bool(track.get("is_master")),
                "devices": track.get("devices") or [],
                "clips": clips,
            }
        )
    return rows


def _find_copy(send, track_index, source_name, count, previous_count=None):
    """Return the duplicate Live just inserted.

    Live inserts at ``track_index + 1``. A numbered stem may be renumbered, and
    a generic name such as ``13-Audio`` may be replaced with the first clip's
    file name. When the caller proves the set grew by exactly one track, that
    neighbor is the copy. Without that proof, only a matching base name counts,
    so an unrelated neighbor is never renamed.
    """

    target = track_index + 1

    def row(index):
        return send("get_track_info", {"track_index": index})

    if previous_count is not None and count == previous_count + 1:
        if not 0 <= target < count:
            raise RuntimeError("duplicate track not found; nothing else was renamed")
        candidate = row(target)
        if is_protected(candidate.get("name")):
            raise RuntimeError("duplicate track not found; nothing else was renamed")
        return target, candidate.get("name")

    if not 0 <= target < count:
        raise RuntimeError("duplicate track not found; nothing else was renamed")
    candidate = row(target)
    if not is_protected(candidate.get("name")) and base_name(candidate.get("name")) == base_name(
        source_name
    ):
        return target, candidate.get("name")
    for index in range(count):
        if index == track_index:
            continue
        candidate = row(index)
        if is_protected(candidate.get("name")):
            continue
        if base_name(candidate.get("name")) == base_name(source_name):
            return index, candidate.get("name")
    raise RuntimeError("duplicate track not found; nothing else was renamed")


def _apply_one(send, action, known_count=None):
    index = action["source_index"]
    source = send("get_track_info", {"track_index": index})
    if source.get("name") != action["source_name"]:
        raise RuntimeError("track changed before prepare; nothing was duplicated")
    # The caller proves the count when it already holds one; otherwise read it.
    before = (
        known_count if known_count is not None else send("get_session_info", {})["track_count"]
    )
    send("duplicate_track", {"track_index": index})
    count = send("get_session_info", {})["track_count"]
    if count != before + 1:
        raise RuntimeError("duplicate did not create exactly one track")
    copy_index, copy_name = _find_copy(
        send, index, action["source_name"], count, previous_count=before
    )
    properties = {
        "name": action["original_name"],
        "mute": True,
        "solo": False,
        "color_index": ARCHIVE_COLOR,
    }
    if isinstance(source.get("arm"), bool):
        properties["arm"] = False
    group = send("get_group_info", {"track_index": copy_index})
    foldable = bool(group.get("is_foldable"))
    # Every guarded write for this track goes out in one ordered bridge batch:
    # the copy first, then its fold, then the working name the clip guards expect.
    commands = [
        {
            "type": "write_access_object",
            "params": {
                "object_type": "track",
                "track_index": copy_index,
                "expected_track_name": copy_name,
                "properties": properties,
            },
        }
    ]
    if foldable:
        commands.append(
            {"type": "set_fold_state", "params": {"track_index": copy_index, "folded": True}}
        )
    commands.append(
        {
            "type": "write_access_object",
            "params": {
                "object_type": "track",
                "track_index": index,
                "expected_track_name": action["source_name"],
                "properties": {
                    "name": action["working_name"],
                    "color_index": action["color_index"],
                },
            },
        }
    )
    for clip in action["clip_renames"]:
        commands.append(
            {
                "type": "write_access_object",
                "params": {
                    "object_type": "clip",
                    "track_index": index,
                    "clip_index": clip["clip_index"],
                    "clip_view": "arrangement",
                    "expected_track_name": action["working_name"],
                    "expected_clip_name": clip["expected_name"],
                    "expected_start_time": clip["start_beats"],
                    "properties": {"name": clip["name"]},
                },
            }
        )
    send("batch", {"commands": commands})
    folded = False
    fold_note = FOLD_LIMIT
    if foldable:
        checked = send("get_group_info", {"track_index": copy_index})
        folded = checked.get("fold_state") is True
        fold_note = "folded" if folded else "fold was requested and the readback was still open"
    return {
        "source_index": index,
        "working_name": action["working_name"],
        "original_index": copy_index,
        "original_name": action["original_name"],
        "muted": True,
        "fold_applied": folded,
        "fold": fold_note,
        "color_index": action["color_index"],
    }


def apply_plan(send, plan, confirm=True):
    """Duplicate, mute and rename from a plan. One track at a time, bottom up."""

    if confirm is not True:
        return {
            "applied": False,
            "live_changes": False,
            "playback_started": False,
            "results": [],
            "skipped": plan.get("skipped") or [],
            "not_applied": list(plan.get("tracks") or []),
        }
    session = send("get_session_info", {})
    if session.get("is_playing") or session.get("record_mode"):
        raise ValueError("Stop playback and recording before preparing tracks")
    ready = [action for action in plan.get("tracks") or [] if action.get("status") == "prepare"]
    results = []
    # Duplicating inserts exactly one track, so the count this loop already holds
    # is the next track's "before" value; only an unproven count is re-read.
    count = session.get("track_count")
    for action in sorted(ready, key=lambda item: -int(item["source_index"])):
        results.append(_apply_one(send, action, count))
        if count is not None:
            count += 1
    return {
        "applied": True,
        "live_changes": bool(results),
        "playback_started": False,
        "results": results,
        "skipped": plan.get("skipped") or [],
        "not_applied": [
            action for action in plan.get("tracks") or [] if action.get("status") != "prepare"
        ],
        "undo": "Each duplicate and each rename is its own undo step, from the last write backward.",
    }


def plan_live(send):
    from .song_lint import collect_live

    state = collect_live(include_session=False)
    plan = plan_tracks(tracks_from_capture(state))
    plan["captured_tracks"] = len(state.get("tracks") or [])
    plan["capture_errors"] = state.get("capture_errors") or []
    return plan


def apply_live(send, confirm=True):
    if confirm is not True:
        plan = plan_live(send)
        plan["applied"] = False
        plan["live_changes"] = False
        return plan
    session = send("get_session_info", {})
    if session.get("is_playing") or session.get("record_mode"):
        raise ValueError("Stop playback and recording before preparing tracks")
    plan = plan_live(send)
    applied = apply_plan(send, plan, confirm=True)
    applied["method"] = "prepare-tracks"
    return applied


def register_track_prep(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def plan_track_preparation() -> dict:
        """Optional preview of content names, role colors and muted originals.
        Does not write, play, or change notes, Warp or faders. A regular track cannot
        be folded; the preview says so instead of grouping tracks Live cannot group.
        """
        return plan_live(dispatch)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def apply_track_preparation(confirm: bool = True) -> dict:
        """Duplicate each working track, mute the untouched copy, fold it when it is a
        group, then rename and color the working track from its content. Writes unless
        confirm is false. Refuses while playing or recording. Notes, Warp and faders stay.
        """
        return apply_live(dispatch, confirm=confirm)
