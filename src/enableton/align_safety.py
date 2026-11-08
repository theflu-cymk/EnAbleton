"""Safety protocol before an alignment edit: duplicate, name, mute, fold.

The duplicate is the escape hatch: if an alignment move is wrong, the untouched
copy is one track away. Order matters -- duplicate first, then rename the copy so
it can never be mistaken for the working track, then mute it so it cannot sound.

Folding is a Live *view* state and is not exposed through the Live Object Model,
so it is reported as a manual step rather than silently skipped.
"""

import re

SUFFIX = "ORIGINAL"

_NUMBERED = re.compile(r"^\d+\s*[-.]\s*")

FOLD_NOTE = (
    "Live exposes no fold write; fold the protection copy by hand (or group it) before auditioning."
)


def protection_name(name, suffix=SUFFIX):
    """Name for the protection copy; never applied to the working track."""

    if not isinstance(name, str) or not name.strip():
        raise ValueError("track name is required")
    return f"{suffix} | {name.strip()}"


def base_name(name):
    """Name without a numbered-stem prefix; Live renumbers a duplicated ``7-X`` as ``8-X``."""

    return _NUMBERED.sub("", (name or "").strip())


def is_protected(name, suffix=SUFFIX):
    return isinstance(name, str) and name.startswith(f"{suffix} | ")


def protect(send, track_index, suffix=SUFFIX):
    """Duplicate ``track_index``, rename and mute the copy. Returns the record.

    Refuses to protect a track that is already a copy, and verifies the readback
    before returning, so a partially applied protection is never reported as done.
    """

    info = send("get_track_info", {"track_index": track_index})
    name = info.get("name")
    if is_protected(name, suffix):
        raise ValueError(f"track {track_index} is already a protection copy")
    before = send("get_session_info", {})["track_count"]
    send("duplicate_track", {"track_index": track_index})
    count = send("get_session_info", {})["track_count"]
    if count != before + 1:
        raise RuntimeError("duplicate did not create exactly one track")

    target = track_index + 1

    def identified(index):
        row = send("get_track_info", {"track_index": index})
        return row, not is_protected(row.get("name"))

    candidate, fresh = identified(target)
    if not fresh or base_name(candidate.get("name")) != base_name(name):
        target = next(
            (
                index
                for index in range(count)
                if index != track_index
                and identified(index)[1]
                and base_name(identified(index)[0].get("name")) == base_name(name)
            ),
            None,
        )
        if target is None:
            raise RuntimeError("duplicate track not found; refusing to rename another track")
        candidate, _ = identified(target)

    duplicate = protection_name(name, suffix)
    # Live renumbers a duplicated "7-X" as "8-X", so guard the copy by its own current name.
    locator = {"track_index": target, "expected_track_name": candidate.get("name")}
    send(
        "write_access_object",
        dict(locator, object_type="track", properties={"name": duplicate, "mute": True}),
    )
    after = send("read_access_object", {"track_index": target, "object_type": "track"})[
        "properties"
    ]
    applied = after.get("name") == duplicate and after.get("mute") is True
    return {
        "track_index": track_index,
        "track_name": name,
        "duplicate_index": target,
        "duplicate_name": duplicate,
        "muted": after.get("mute") is True,
        "verified": applied,
        "fold": FOLD_NOTE,
        "fold_applied": False,
    }


def release(send, duplicate_index, duplicate_name):
    """Delete a protection copy after the alignment edit has been accepted."""

    if not is_protected(duplicate_name):
        raise ValueError("refusing to delete a track that is not a protection copy")
    send(
        "delete_track",
        {"track_index": duplicate_index, "expected_track_name": duplicate_name},
    )
    remaining = send(
        "get_track_info",
        {"track_index": duplicate_index},
    )
    return {"deleted": duplicate_name, "remaining_at_index": remaining.get("name")}
