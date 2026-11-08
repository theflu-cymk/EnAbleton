"""Small pure correction planners. Writers live behind the runner's adapter boundary."""

from copy import deepcopy
import math
from pathlib import Path
import re
import string

from .song_init import REGISTRY, Result, clips, register, selected, song_folder
from .layer_processes import apply_layer_naming
from .warp_unwrap import unwrap_layers


def change(kind, item, patch):
    return {"kind": kind, "target": item["id"], "before": deepcopy(item), "patch": patch}


def text(template, values):
    if not isinstance(template, str):
        raise ValueError("Naming pattern must be a string")
    for _, field, spec, conversion in string.Formatter().parse(template):
        if field is not None and (field not in values or spec or conversion):
            raise ValueError("Unsupported naming placeholder or formatting expression")
    result = template.format(**values).strip()
    if not result or len(result) > 256:
        raise ValueError("Names must contain 1..256 characters")
    return result


def number(params, key, default, low, high):
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{key} outside {low}..{high}")
    return value


@register("create_song_folder")
def workspace(state, params, target):
    return Result([dict(kind="create_song_folder", **song_folder(params))])


@register("cleanup_unused")
def cleanup_unused(state, params, target):
    result = Result(notices=["Inventory only. No sample deletion or source-file moves."])
    if params.get("collect", False):
        result.changes.append(
            {"kind": "collect_assets", "target": "song", "before": {}, "patch": {"copyOnly": True}}
        )
    if params.get("save", False):
        result.changes.append({"kind": "save_set", "target": "song", "before": {}, "patch": {}})
    result.notices.append(
        "Unused-file proof requires project-wide reference inventory; not inferred from this set."
    )
    return result


@register("rename_tracks")
def rename_tracks(state, params, target):
    result = Result()
    if params.get("convention", False):
        return apply_layer_naming(state, params, target)
    pattern = params.get("pattern", "{type}_{name}")
    for track in selected(state, target):
        role = track.get("role", track["type"])
        current = track["name"]
        prefix = role + "_"
        name = current[len(prefix) :] if current.startswith(prefix) else current
        name = re.sub(r"^\d+[- ]", "", name).strip()
        if name.casefold() in {"audio", "midi", "track", "group"}:
            name = "Unassigned" if track["type"] != "group" else "Group"
        new = text(pattern, {"type": role, "role": role, "name": name})
        if new != current:
            result.changes.append(change("set_track", track, {"name": new}))
    return result


@register("normalize_clip_names")
def normalize_clip_names(state, params, target):
    result = Result()
    for track, clip in clips(state, target):
        # source_name must be immutable provenance, not the previously formatted name.
        source = clip.get("source_name")
        if not source:
            source = (
                Path(clip["audio_path"]).stem
                if clip.get("audio_path")
                else track.get("role", track["type"])
            )
        warp = "ON" if clip.get("warping") else "OFF" if clip["type"] == "audio" else "N/A"
        values = {
            "name": source,
            "role": track.get("role", track["type"]),
            "type": clip["type"],
            "bpm": state.get("session", {}).get("tempo", "unknown"),
            "warp": warp,
        }
        name = text(params.get("pattern", "{role} | {bpm} BPM | WARP {warp}"), values)
        if name != clip["name"]:
            result.changes.append(change("set_clip", clip, {"name": name}))
    return result


def midi_result(state, target, function):
    result = Result()
    for track, clip in clips(state, target):
        if clip["type"] != "midi":
            continue
        notes = deepcopy(clip.get("notes", []))
        updated = function(notes)
        if updated != clip.get("notes", []):
            result.changes.append(change("replace_midi", clip, {"notes": updated}))
    return result


@register("fix_midi_overlaps")
def fix_midi_overlaps(state, params, target):
    strategy = params.get("strategy", "trim")
    if strategy not in {"trim", "shortest_wins", "longest_wins"}:
        raise ValueError("Unknown overlap strategy")
    gap = number(params, "gapBeats", 0.01, 0, 1)

    def fix(notes):
        groups = {}
        for note in notes:
            key = 0 if params.get("monophonic", False) else note["pitch"]
            groups.setdefault(key, []).append(note)
        kept = []
        for group in groups.values():
            output = []
            for note in sorted(group, key=lambda n: n["start_time"]):
                while (
                    output
                    and output[-1]["start_time"] + output[-1]["duration"] > note["start_time"]
                ):
                    previous = output[-1]
                    if strategy == "trim" and note["start_time"] - previous["start_time"] > 0.001:
                        previous["duration"] = max(
                            0.001, note["start_time"] - previous["start_time"] - gap
                        )
                        break
                    previous_wins = (
                        previous["duration"] <= note["duration"]
                        if strategy == "shortest_wins"
                        else previous["duration"] >= note["duration"]
                    )
                    if previous_wins:
                        note = None
                        break
                    output.pop()
                if note is not None:
                    output.append(note)
            kept.extend(output)
        return sorted(kept, key=lambda n: (n["start_time"], n["pitch"]))

    return midi_result(state, target, fix)


@register("quantize_timing")
def quantize_timing(state, params, target):
    grids = {"1/4": 1.0, "1/8": 0.5, "1/16": 0.25, "1/32": 0.125, "1/8T": 1 / 3, "1/16T": 1 / 6}
    grid = params.get("grid", "1/16")
    if grid not in grids:
        raise ValueError("Unknown quantize grid")
    strength = number(params, "strength", 0.75, 0, 1)
    tolerance = number(params, "toleranceBeats", 0.03, 0, 4)

    def fix(notes):
        for note in notes:
            delta = round(note["start_time"] / grids[grid]) * grids[grid] - note["start_time"]
            if abs(delta) > tolerance:
                note["start_time"] = max(0.0, note["start_time"] + delta * strength)
        return notes

    return midi_result(state, target, fix)


@register("normalize_velocities")
def normalize_velocities(state, params, target):
    lo = number(params, "min", 40, 1, 127)
    hi = number(params, "max", 112, lo, 127)
    mode = params.get("mode", "clamp")
    if mode not in {"clamp", "scale"}:
        raise ValueError("mode must be clamp or scale")

    def fix(notes):
        for note in notes:
            value = note["velocity"]
            note["velocity"] = (
                min(hi, max(lo, value)) if mode == "clamp" else lo + (value - 1) / 126 * (hi - lo)
            )
        return notes

    return midi_result(state, target, fix)


@register("remove_empty_tracks")
def remove_empty_tracks(state, params, target):
    result = Result()
    for track in selected(state, target):
        if track.get("is_group") or track.get("type") == "group":
            continue
        if (
            not track.get("clips")
            and not track.get("devices")
            and track.get("has_automation") is False
            and not track.get("armed")
            and not track.get("live_input")
        ):
            result.changes.append(change("delete_track", track, {}))
    return result


@register("remove_empty_clips")
def remove_empty_clips(state, params, target):
    result = Result()
    for _, clip in clips(state, target):
        empty = clip["type"] == "midi" and "notes" in clip and not clip["notes"]
        empty |= clip["type"] == "audio" and clip.get("sample_frames") == 0
        if empty:
            result.changes.append(change("delete_clip", clip, {}))
    return result


@register("fix_clip_lengths")
def fix_clip_lengths(state, params, target):
    result = Result()
    session = state.get("session", {})
    bar = session.get("numerator", 4) * 4 / session.get("denominator", 4)
    tolerance = number(params, "toleranceBeats", 0.04, 0, bar)
    mode = params.get("mode", "report")
    if mode not in {"report", "extend", "nearest"}:
        raise ValueError("Unknown clip-length mode")
    if mode == "nearest" and not params.get("allowTrim", False):
        raise ValueError("nearest requires allowTrim: true; it can cut note/audio tails")
    for _, clip in clips(state, target):
        end = clip.get("end_beats")
        if end is None:
            result.notices.append(f"{clip['id']}: end_beats unavailable; no time-unit guessing")
            continue
        new = math.ceil(end / bar) * bar if mode == "extend" else round(end / bar) * bar
        if abs(new - end) > tolerance:
            if mode == "report":
                result.notices.append(f"{clip['id']}: end {end} is not near a bar boundary")
            else:
                result.changes.append(change("resize_clip", clip, {"end_beats": new}))
    return result


@register("color_tracks_by_type")
def color_tracks_by_type(state, params, target):
    colors = params.get("colors", {"drums": 6, "bass": 20, "vocals": 11, "melodic": 8})
    if not isinstance(colors, dict):
        raise ValueError("colors must be a role-to-index mapping")
    if any(type(v) is not int or not 0 <= v <= 69 for v in colors.values()):
        raise ValueError("Live color indexes must be integers in 0..69")
    result = Result()
    for track in selected(state, target):
        color = colors.get(track.get("role", track["type"]))
        if color is not None and track.get("color_index") != color:
            result.changes.append(change("set_track", track, {"color_index": color}))
    return result


@register("set_default_warp")
def set_default_warp(state, params, target):
    if params.get("enabled", False) is False and params.get("method", "render") != "toggle":
        # Removing Warp defaults to the render-first workflow in warp_unwrap.
        return unwrap_layers(state, params, target)
    mode = params.get("mode", 4)
    if type(params.get("enabled", False)) is not bool:
        raise ValueError("Warp enabled must be boolean")
    if mode not in {0, 1, 2, 3, 4, 6}:
        raise ValueError("Unsupported Live Warp mode")
    result = Result(
        notices=[
            "Matching lengths is not proof of alignment. Preserve multitrack phase and shared start offsets."
        ]
    )
    for _, clip in clips(state, target):
        if clip["type"] != "audio":
            continue
        patch = {"warping": params.get("enabled", False), "warp_mode": mode}
        if "baseTempo" in params:
            number(params, "baseTempo", 120, 20, 999)
            result.notices.append(
                "Live exposes no writable base tempo; baseTempo is validated but not applied."
            )
        if any(clip.get(k) != v for k, v in patch.items()):
            result.changes.append(change("set_warp", clip, patch))
    return result


@register("check_missing_samples")
def check_missing_samples(state, params, target):
    result = Result()
    for _, clip in clips(state, target):
        if clip["type"] != "audio":
            continue
        exists = clip.get("file_exists")
        if exists is None and clip.get("audio_path"):
            exists = Path(clip["audio_path"]).is_file()
        if exists is not True:
            result.notices.append(f"Missing or unresolved audio: {clip['id']}")
    return result


@register("organize_groups")
def organize_groups(state, params, target):
    result = Result(
        notices=[
            "Live exposes no group-creation API (Track.group_track is read-only), "
            "so grouping is reported as a skipped step instead of being written."
        ]
    )
    if params.get("apply", False):
        groups = {}
        for track in selected(state, target):
            if not track.get("group_id") and not track.get("is_group"):
                groups.setdefault(track.get("role", track["type"]), []).append(track["id"])
        for role, ids in groups.items():
            if len(ids) > 1:
                result.changes.append(
                    {
                        "kind": "group_tracks",
                        "target": ids,
                        "before": {},
                        "patch": {"name": role.upper()},
                    }
                )
    return result


@register("set_session_defaults")
def set_session_defaults(state, params, target):
    session = state.get("session", {})
    patch = {}
    for key in ("tempo", "key", "numerator", "denominator"):
        if key in params and (session.get(key) is None or params.get("force", False)):
            patch[key] = params[key]
    if "tempo" in patch:
        number(patch, "tempo", 120, 20, 999)
    if "numerator" in patch and (
        type(patch["numerator"]) is not int or not 1 <= patch["numerator"] <= 99
    ):
        raise ValueError("Invalid time-signature numerator")
    if "denominator" in patch and patch["denominator"] not in {1, 2, 4, 8, 16}:
        raise ValueError("Invalid time-signature denominator")
    return Result(
        [change("set_session", dict(session, id="session"), patch)] if patch else [],
        ["Live always has a tempo; defaults do not identify the song's true BPM/key."],
    )


@register("trim_overlapping_clips")
def trim_overlapping_clips(state, params, target):
    result = Result()
    for track in selected(state, target):
        arrangement = sorted(
            (c for c in track.get("clips", []) if c.get("view") == "arrangement"),
            key=lambda c: c.get("start_beats", 0),
        )
        for a, b in zip(arrangement, arrangement[1:]):
            if a.get("end_beats", 0) > b.get("start_beats", 0):
                if params.get("apply", False):
                    result.changes.append(change("resize_clip", a, {"end_beats": b["start_beats"]}))
                else:
                    result.notices.append(f"Overlapping clips: {a['id']} / {b['id']}")
    return result


assert len(REGISTRY) >= 15
