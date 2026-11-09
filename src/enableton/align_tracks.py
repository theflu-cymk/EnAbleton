"""Set Warp mode from layer content. Markers, starts, and the mix stay put.

Beats is for drums and percussion. Tones is for bass. Complex Pro, or Complex
when Pro is missing, is for tonal layers and full mixes. Re-Pitch is left
alone because it changes pitch with tempo. Warp that is off stays off: turning
it on, moving markers, or sliding a clip needs a reference and a render.

Phase, EQ, panning, reverb, delay, automation, racks, and group buses are not
guessed. This command cannot hear a mix, and Live cannot create a group here.
"""

from .align_safety import is_protected
from .track_prep import infer_content

BEATS = 0
TONES = 1
REPITCH = 3
COMPLEX = 4
COMPLEX_PRO = 6
MODE_NAMES = {
    BEATS: "Beats",
    TONES: "Tones",
    2: "Texture",
    REPITCH: "Re-Pitch",
    COMPLEX: "Complex",
    COMPLEX_PRO: "Complex Pro",
}
PERCUSSIVE = {"drums", "percussion"}
MONOPHONIC = {"bass"}
NOT_AUTOMATED = (
    {
        "method": "transients and phase",
        "reason": (
            "Clip starts and warp markers stay. Off-grid hits can be musical, and "
            "this command cannot hear phase, so it does not flip polarity or load "
            "a Transient Shaper."
        ),
    },
    {
        "method": "frequency and space",
        "reason": (
            "EQ, panning, reverb, and delay stay. A guessed carve or send would "
            "change the mix without a measurement."
        ),
    },
    {
        "method": "automation",
        "reason": "Volume, pan, effect rides, and clip envelopes stay. Those are musical moves.",
    },
    {
        "method": "racks, audio-to-MIDI, and group buses",
        "reason": (
            "Those stay separate. This command does not create a group, a rack, "
            "or a MIDI copy of the audio."
        ),
    },
)


def mode_name(mode):
    return MODE_NAMES.get(mode, "mode " + str(mode))


def preferred_mode(role):
    """Warp mode for a role. Complex Pro is mode 6 on this Live build."""

    if role in PERCUSSIVE:
        return BEATS
    if role in MONOPHONIC:
        return TONES
    return COMPLEX_PRO


def resolve_mode(preferred, available):
    """Keep the preferred mode, or Complex when Complex Pro is absent."""

    if preferred == REPITCH:
        return None
    if not available:
        return preferred
    modes = []
    for item in available:
        if isinstance(item, bool) or not isinstance(item, int):
            continue
        modes.append(item)
    if not modes or preferred in modes:
        return preferred
    if preferred == COMPLEX_PRO and COMPLEX in modes:
        return COMPLEX
    return None


def _reason(role, mode, evidence, fell_back):
    label = mode_name(mode)
    if role in PERCUSSIVE:
        why = "this layer reads as drums or percussion"
    elif role in MONOPHONIC:
        why = "this layer reads as bass"
    else:
        why = "this layer is tonal or a full mix"
    text = "Set Warp to " + label + " because " + why + ". " + evidence + "."
    if fell_back:
        text += " Complex Pro is not available on this clip, so Complex is used."
    return text + " Markers and the clip start stay."


def plan_alignment(tracks):
    """Turn captured tracks into Warp-mode actions. No Live calls."""

    if not isinstance(tracks, list):
        raise ValueError("tracks must be a list")
    actions = []
    reports = []
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
        if track.get("type") not in (None, "audio"):
            skipped.append({"index": index, "name": name, "reason": "not an audio track"})
            continue
        clips = [
            clip
            for clip in track.get("clips") or []
            if clip.get("type") in (None, "audio") and clip.get("view") in (None, "arrangement")
        ]
        if not clips:
            skipped.append({"index": index, "name": name, "reason": "no arrangement audio"})
            continue
        content = infer_content(track)
        role = content["role"]
        preferred = preferred_mode(role)
        for clip in clips:
            label = clip.get("name") or ""
            if clip.get("start_beats") is None:
                skipped.append(
                    {
                        "index": index,
                        "name": name,
                        "clip": label,
                        "reason": "arrangement start is missing",
                    }
                )
                continue
            if "warp_mode" not in clip or "warping" not in clip:
                skipped.append(
                    {
                        "index": index,
                        "name": name,
                        "clip": label,
                        "reason": "warp mode was not read",
                    }
                )
                continue
            current = clip.get("warp_mode")
            row = {
                "track_index": index,
                "track_name": name,
                "clip_name": label,
                "clip_index": clip.get("index", clip.get("locator", {}).get("clip_index", 0)),
                "start_beats": clip.get("start_beats"),
                "role": role,
                "evidence": content["evidence"],
            }
            if not clip.get("warping"):
                reports.append(
                    {
                        **row,
                        "code": "warp_off",
                        "message": (
                            "Warp is off, so the mode was left unset. Turning Warp on "
                            "needs a reference and a rendered replacement."
                        ),
                    }
                )
                continue
            if current == REPITCH:
                reports.append(
                    {
                        **row,
                        "code": "repitch",
                        "message": "Re-Pitch stays. It changes pitch when the tempo changes.",
                    }
                )
                continue
            mode = resolve_mode(preferred, clip.get("available_warp_modes"))
            if mode is None:
                reports.append(
                    {
                        **row,
                        "code": "warp_mode_unavailable",
                        "message": mode_name(preferred) + " is not available on this clip.",
                    }
                )
                continue
            if current == mode:
                reports.append(
                    {
                        **row,
                        "code": "warp_mode_ready",
                        "warp_mode": mode,
                        "warp_mode_name": mode_name(mode),
                        "message": "Warp is already " + mode_name(mode) + ".",
                    }
                )
                continue
            fell_back = preferred == COMPLEX_PRO and mode == COMPLEX
            actions.append(
                {
                    **row,
                    "status": "set_warp_mode",
                    "warp_mode": mode,
                    "warp_mode_name": mode_name(mode),
                    "message": _reason(role, mode, content["evidence"], fell_back),
                }
            )
    return {
        "method": "align-tracks",
        "live_changes": False,
        "playback_started": False,
        "writes": [
            "set Warp mode on arrangement audio that is already warped",
        ],
        "leaves_unchanged": [
            "warp markers",
            "clip starts",
            "warping on/off",
            "Re-Pitch",
            "notes",
            "faders",
            "EQ",
            "panning",
            "reverb",
            "delay",
            "automation",
            "groups",
        ],
        "not_automated": [dict(item) for item in NOT_AUTOMATED],
        "actions": actions,
        "reports": reports,
        "skipped": skipped,
    }


def _require_stopped(send):
    session = send("get_session_info", {})
    if session.get("is_playing") or session.get("record_mode"):
        raise ValueError("Stop playback and recording before aligning tracks")


def _index(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(label + " is missing")
    return value


def _target(action):
    return {
        "track_index": _index(action.get("track_index"), "track index"),
        "clip_index": _index(action.get("clip_index"), "clip index"),
        "clip_view": "arrangement",
        "expected_track_name": action.get("track_name"),
        "expected_clip_name": action.get("clip_name") or "",
        "expected_start_time": action.get("start_beats"),
    }


def _apply_mode(send, action):
    target = _target(action)
    fresh = send("get_track_info", {"track_index": target["track_index"]})
    if fresh.get("name") != action.get("track_name"):
        raise RuntimeError("track changed before the warp mode change")
    timing = send("get_audio_clip_timing", target)
    result = {
        "status": "ready",
        "wrote": False,
        "verified": False,
        "track_index": target["track_index"],
        "track_name": action.get("track_name"),
        "clip_name": action.get("clip_name"),
        "reason": action.get("message"),
    }
    if not timing.get("warping"):
        result["reason"] = (
            "Warp is off, so the mode was left unset. Turning Warp on needs a "
            "reference and a rendered replacement."
        )
        return result
    current = timing.get("warp_mode")
    if current == REPITCH:
        result["reason"] = "Re-Pitch stays. It changes pitch when the tempo changes."
        return result
    mode = resolve_mode(action.get("warp_mode"), timing.get("available_warp_modes"))
    if mode is None:
        result["status"] = "unavailable"
        result["reason"] = "The planned Warp mode is not available on this clip."
        return result
    fell_back = action.get("warp_mode") == COMPLEX_PRO and mode == COMPLEX
    if current == mode:
        result["warp_mode"] = mode
        result["warp_mode_name"] = mode_name(mode)
        result["reason"] = "Warp is already " + mode_name(mode) + "."
        return result
    try:
        send("set_access_warp", {**target, "properties": {"warp_mode": mode}})
    except RuntimeError as error:
        result["status"] = "unavailable"
        result["reason"] = "Warp mode was not changed: " + str(error)
        return result
    after = send("get_audio_clip_timing", target)
    verified = after.get("warp_mode") == mode and bool(after.get("warping"))
    result.update(
        status="set_warp_mode" if verified else "review",
        wrote=True,
        verified=verified,
        warp_mode=mode,
        warp_mode_name=mode_name(mode),
        reason=_reason(action.get("role"), mode, action.get("evidence") or "", fell_back),
    )
    return result


def apply_plan(send, plan, confirm=True):
    """Write the planned Warp modes. Markers and clip starts are not written."""

    if confirm is not True:
        preview = dict(plan)
        preview["applied"] = False
        preview["live_changes"] = False
        preview["playback_started"] = False
        return preview
    _require_stopped(send)
    results = []
    for action in plan.get("actions") or []:
        _require_stopped(send)
        if action.get("status") == "set_warp_mode":
            results.append(_apply_mode(send, action))
    return {
        "method": "align-tracks",
        "applied": True,
        "live_changes": any(row.get("wrote") for row in results),
        "playback_started": False,
        "results": results,
        "reports": plan.get("reports") or [],
        "skipped": plan.get("skipped") or [],
        "not_automated": plan.get("not_automated") or [dict(item) for item in NOT_AUTOMATED],
        "undo": "Each Warp-mode change is its own undo step, from the last write backward.",
    }


def plan_live(send):
    from .song_lint import collect_live

    state = collect_live(include_session=False)
    plan = plan_alignment(state.get("tracks") or [])
    plan["captured_tracks"] = len(state.get("tracks") or [])
    plan["capture_errors"] = state.get("capture_errors") or []
    return plan


def apply_live(send, confirm=True):
    if confirm is not True:
        plan = plan_live(send)
        plan["applied"] = False
        plan["live_changes"] = False
        return plan
    _require_stopped(send)
    applied = apply_plan(send, plan_live(send), confirm=True)
    applied["method"] = "align-tracks"
    return applied


def register_track_alignment(mcp, dispatch):
    @mcp.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def plan_track_alignment() -> dict:
        """Optional preview of Warp modes for arrangement audio that is already warped.
        Drums and percussion use Beats, bass uses Tones, and tonal or full-mix layers
        use Complex Pro. Re-Pitch and unwarped clips stay. Does not move markers or
        clip starts, flip polarity, load EQ or sends, or start playback.
        """
        return plan_live(dispatch)

    @mcp.tool(annotations={"readOnlyHint": False, "destructiveHint": True})
    def apply_track_alignment(confirm: bool = True) -> dict:
        """Set Warp modes on arrangement audio that is already warped. Writes unless
        confirm is false. Refuses while playing or recording. Does not enable Warp,
        move markers, slide clips, or change notes, faders, polarity, EQ, sends,
        automation, racks, or groups.
        """
        return apply_live(dispatch, confirm=confirm)
