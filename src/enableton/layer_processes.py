"""Layer naming/colour step built on the canonical convention."""

from copy import deepcopy

from .layer_naming import plan as layer_plan
from .song_init import Result, register, selected


def change(kind, item, patch):
    return {"kind": kind, "target": item["id"], "before": deepcopy(item), "patch": patch}


@register("apply_layer_naming")
def apply_layer_naming(state, params, target):
    """Rename and colour audio layers with the canonical ``NN Label`` convention."""

    result = Result()
    tracks = [track for track in selected(state, target) if track.get("type") == "audio"]
    by_id = {track["id"]: track for track in tracks}
    for row in layer_plan(tracks):
        track = by_id[row["id"]]
        patch = {}
        if track.get("name") != row["name"]:
            patch["name"] = row["name"]
        if track.get("color_index") != row["color_index"]:
            patch["color_index"] = row["color_index"]
        if patch:
            result.changes.append(change("set_track", track, patch))
    return result
