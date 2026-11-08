"""Default Warp removal: align to a reference, render, place, then switch Warp off.

Disabling Warp is not a cosmetic toggle. For warped audio Live maps source
seconds to Arrangement beats through the clip's warp markers, so clearing the
Warp flag throws that mapping away. The safe order is:

1. Align each layer to the reference and measure its offset in the audio.
2. Render/bounce the correctly timed layer at the project tempo.
3. Place the rendered WAV at the measured beat.
4. Only then switch Warp off and verify the readback.

This module makes that sequence the default. A blind ``warping = False`` write is
only emitted for clips that carry no marker-based timing, or when the caller
explicitly asks for ``method: toggle``.
"""

from copy import deepcopy

from .song_init import Result, clips, register, selected


def change(kind, item, patch):
    return {"kind": kind, "target": item["id"], "before": deepcopy(item), "patch": patch}


def _reference_exists(state, reference, target):
    identifier = reference.get("id") if isinstance(reference, dict) else reference
    role = reference.get("role") if isinstance(reference, dict) else None
    for track in selected(state, target):
        if identifier and track.get("id") == identifier:
            return True
        if role and track.get("role") == role:
            return True
    return False


@register("unwrap_layers")
def unwrap_layers(state, params, target):
    """Render-first Warp removal; reports what still needs a bounce."""

    result = Result(
        notices=[
            "Default method: align to the reference, render at the project tempo, place "
            "the rendered WAV at its measured beat, then switch Warp off. Pass "
            "method: toggle only for clips with no marker-based timing.",
        ]
    )
    reference = params.get("reference")
    if not reference or not _reference_exists(state, reference, target):
        result.notices.append(
            "No valid reference layer was supplied, so no Warp state was changed."
        )
        return result
    renders = params.get("renders") or {}
    if not isinstance(renders, dict):
        raise ValueError("renders must map a clip or track id to a rendered WAV path")
    for track, clip in clips(state, target):
        if clip["type"] != "audio":
            continue
        markers = clip.get("warp_markers") or []
        rendered = renders.get(clip["id"]) or renders.get(track["id"])
        if clip.get("warping") and len(markers) > 2 and not rendered:
            result.notices.append(
                "Render required for "
                + clip["id"]
                + " ("
                + str(clip.get("name"))
                + "): bounce this layer at the project tempo, place the WAV at its "
                "measured beat, then re-run with renders."
            )
            continue
        if rendered:
            result.notices.append(
                "Place the rendered WAV for "
                + clip["id"]
                + " at its measured beat before switching Warp off: "
                + str(rendered)
            )
            continue
        if clip.get("warping"):
            result.changes.append(change("set_warp", clip, {"warping": False}))
    return result
