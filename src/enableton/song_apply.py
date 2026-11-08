"""Guarded Live adapter for the YAML song-init workflow.

The planners in ``song_processes`` only describe changes. This adapter is the one
place where those descriptions become bridge commands, so every write reuses the
captured target locators (track/clip names and Arrangement starts), the bridge's
own validation and readback, and one undo step per command.

Executable changes: track and clip properties, song properties, note
reconciliation by ID (insert, modify, delete), track and clip deletion, Session
clip length, and audio Warp state. Live has no API for creating or populating
group tracks, so ``group_tracks`` is reported rather than silently faked; it is
the only kind this adapter declines, and the pipeline records it as a per-step
skip instead of aborting the run.
"""

from copy import deepcopy
from types import SimpleNamespace

from .song_init import UnsupportedOperations

TRACK_PROPERTIES = {"name", "color_index", "mute", "solo", "arm", "current_monitoring_state"}
CLIP_PROPERTIES = {
    "name",
    "color_index",
    "looping",
    "loop_start",
    "loop_end",
    "gain",
    "pitch_coarse",
    "pitch_fine",
    "warping",
}
WARP_PROPERTIES = {"warping", "warp_mode", "gain", "pitch_coarse", "pitch_fine"}
SESSION_PROPERTIES = {
    "tempo": "tempo",
    "numerator": "signature_numerator",
    "denominator": "signature_denominator",
    "swing_amount": "swing_amount",
    "loop": "loop",
    "loop_start": "loop_start",
    "loop_length": "loop_length",
    "metronome": "metronome",
}
NOTE_FIELDS = (
    "pitch",
    "start_time",
    "duration",
    "velocity",
    "mute",
    "probability",
    "velocity_deviation",
    "release_velocity",
)
SUPPORTED_KINDS = {
    "set_track",
    "set_clip",
    "set_session",
    "replace_midi",
    "delete_track",
    "delete_clip",
    "resize_clip",
    "set_warp",
}
PLATFORM_LIMITS = {
    "group_tracks": (
        "Live's API cannot create group tracks or move tracks into one: "
        "Track.group_track is read-only and Song has no grouping call"
    ),
}


def note_identity(note):
    """Identity used to compare a planned note with Live's readback."""
    return (
        int(note["pitch"]),
        round(float(note["start_time"]), 4),
        round(float(note["duration"]), 4),
        round(float(note["velocity"]), 4),
        bool(note.get("mute", False)),
    )


class LiveAdapter:
    """Apply planner changes to the running set through the EXT bridge."""

    def __init__(self, dispatch, state, refresh=None):
        self._dispatch = dispatch
        self._state = deepcopy(state)
        self._refresh_state = refresh

    # ---- adapter contract -------------------------------------------------
    def snapshot(self):
        return deepcopy(self._state)

    def supports(self, change):
        return change["kind"] in SUPPORTED_KINDS

    def reason(self, change):
        """Why an unsupported change cannot run, in platform terms."""
        kind = change["kind"]
        return PLATFORM_LIMITS.get(kind, "no guarded writer for " + kind)

    def apply(self, change):
        kind = change["kind"]
        if kind not in SUPPORTED_KINDS:
            raise UnsupportedOperations(self.reason(change))
        {
            "set_track": self._set_track,
            "set_clip": self._set_clip,
            "set_session": self._set_session,
            "replace_midi": self._replace_midi,
            "delete_track": self._delete_track,
            "delete_clip": self._delete_clip,
            "resize_clip": self._resize_clip,
            "set_warp": self._set_warp,
        }[kind](change)
        self._refresh()

    # ---- capture lookups --------------------------------------------------
    def _track(self, track_id):
        for track in self._state.get("tracks", []):
            if track["id"] == track_id:
                return track
        raise ValueError("Track is no longer in the capture: " + str(track_id))

    def _clip(self, clip_id):
        for track in self._state.get("tracks", []):
            for clip in track.get("clips", []):
                if clip["id"] == clip_id:
                    return clip
        raise ValueError("Clip is no longer in the capture: " + str(clip_id))

    # ---- writers ----------------------------------------------------------
    def _set_track(self, change):
        track = self._track(change["target"])
        patch = dict(change.get("patch", {}))
        unknown = sorted(set(patch) - TRACK_PROPERTIES)
        if unknown:
            raise UnsupportedOperations("track properties: " + ", ".join(unknown))
        if not patch:
            return
        self._dispatch(
            "write_access_object",
            dict(
                object_type="track",
                track_index=track["index"],
                expected_track_name=track["name"],
                properties=patch,
            ),
        )

    def _set_clip(self, change):
        clip = self._clip(change["target"])
        patch = dict(change.get("patch", {}))
        warp = {}
        if "warp_mode" in patch:
            # Live only exposes warp_mode on audio clips; the Warp writer owns that
            # validation, so route it there instead of refusing the whole change.
            warp["warp_mode"] = patch.pop("warp_mode")
        unknown = sorted(set(patch) - CLIP_PROPERTIES)
        if unknown:
            raise UnsupportedOperations("clip properties: " + ", ".join(unknown))
        if warp:
            if clip["type"] != "audio":
                raise ValueError("warp_mode applies to audio clips only")
            self._dispatch("set_access_warp", dict(clip["locator"], properties=warp))
        if patch:
            self._dispatch(
                "write_access_object", dict(object_type="clip", **clip["locator"], properties=patch)
            )

    def _set_session(self, change):
        patch = {}
        for key, value in change.get("patch", {}).items():
            if key not in SESSION_PROPERTIES:
                raise UnsupportedOperations("song property: " + key)
            patch[SESSION_PROPERTIES[key]] = value
        if patch:
            self._dispatch("write_access_object", dict(object_type="song", properties=patch))

    def _replace_midi(self, change):
        """Reconcile a clip's notes: modify by ID, delete missing, insert new.

        Planned notes without ``note_id`` are inserts, so planners can add notes;
        planned notes with an ID must still exist in the clip.
        """
        clip = self._clip(change["target"])
        planned = change.get("patch", {}).get("notes")
        if not isinstance(planned, list):
            raise ValueError("replace_midi requires a note list")
        locator = clip["locator"]
        current = self._dispatch("get_access_notes", locator)["notes"]
        by_id = {note["note_id"]: note for note in current}
        keyed, inserts = {}, []
        for note in planned:
            if "note_id" not in note:
                missing = [
                    field for field in ("pitch", "start_time", "duration") if field not in note
                ]
                if missing:
                    raise ValueError("Insert requires " + ", ".join(missing))
                inserts.append({key: note[key] for key in NOTE_FIELDS if key in note})
                continue
            ident = note["note_id"]
            if ident in keyed:
                raise ValueError("Duplicate planned note ID")
            if ident not in by_id:
                raise ValueError("Planned note left the clip; recapture before applying")
            keyed[ident] = note
        deletes, modifies = [], []
        for ident, before in by_id.items():
            after = keyed.get(ident)
            if after is None:
                deletes.append(ident)
                continue
            row = {"note_id": ident}
            for field in NOTE_FIELDS:
                if field in after and after[field] != before.get(field):
                    row[field] = after[field]
            if len(row) > 1:
                modifies.append(row)
        if not deletes and not modifies and not inserts:
            return
        if deletes:
            self._dispatch(
                "delete_access_notes",
                dict(locator, notes=[{"note_id": ident} for ident in deletes]),
            )
        if modifies:
            self._dispatch("modify_access_notes", dict(locator, notes=modifies))
        if inserts:
            self._dispatch("insert_access_notes", dict(locator, notes=inserts))
        after = self._dispatch("get_access_notes", locator)["notes"]
        if sorted(map(note_identity, after)) != sorted(map(note_identity, planned)):
            raise RuntimeError(
                "Note reconciliation did not match the planned set; inspect the clip and use Live Undo"
            )

    def _delete_track(self, change):
        track = self._track(change["target"])
        if track.get("is_return") or track.get("is_master"):
            raise ValueError("Return and master tracks cannot be deleted")
        before = len(self._state.get("tracks", []))
        self._dispatch(
            "delete_track",
            dict(track_index=track["index"], expected_track_name=track["name"]),
        )
        self._refresh()
        tracks = self._state.get("tracks", [])
        if len(tracks) != before - 1:
            raise RuntimeError("Track deletion did not reduce the track count")
        if any(
            item["index"] == track["index"] and item["name"] == track["name"] for item in tracks
        ):
            raise RuntimeError("Track deletion left the target in place")

    def _delete_clip(self, change):
        clip = self._clip(change["target"])
        locator = dict(clip["locator"])
        self._dispatch("read_access_object", dict(locator, object_type="clip"))
        if clip["view"] == "arrangement":
            self._dispatch(
                "delete_arrangement_clip",
                dict(
                    track_index=locator["track_index"],
                    arrangement_clip_index=locator["clip_index"],
                    expected_clip_name=locator["expected_clip_name"],
                    expected_start_time=locator["expected_start_time"],
                ),
            )
        else:
            self._dispatch(
                "delete_clip",
                dict(
                    track_index=locator["track_index"],
                    clip_index=locator["clip_index"],
                    expected_track_name=locator["expected_track_name"],
                    expected_clip_name=locator["expected_clip_name"],
                ),
            )
        self._refresh()
        for track in self._state.get("tracks", []):
            for item in track.get("clips", []):
                same_slot = (
                    item["view"] == clip["view"]
                    and item["locator"]["clip_index"] == locator["clip_index"]
                    and item["locator"]["track_index"] == locator["track_index"]
                )
                if same_slot and item["name"] == clip["name"]:
                    raise RuntimeError("Clip deletion left the target in place")

    def _resize_clip(self, change):
        clip = self._clip(change["target"])
        patch = dict(change.get("patch", {}))
        end = patch.pop("end_beats", None)
        unknown = sorted(set(patch) - CLIP_PROPERTIES)
        if unknown:
            raise UnsupportedOperations("clip properties: " + ", ".join(unknown))
        if end is None:
            raise ValueError("resize_clip requires end_beats")
        if clip["view"] == "arrangement":
            raise UnsupportedOperations(
                "arrangement clip extent: Live exposes no writable length, so a "
                "planned Arrangement resize cannot be applied"
            )
        end = float(end)
        start = float(clip.get("start_beats") or 0.0)
        if end <= start:
            raise ValueError("end_beats must be after the clip start")
        properties = dict(patch, loop_end=end)
        self._dispatch(
            "write_access_object",
            dict(object_type="clip", **clip["locator"], properties=properties),
        )
        actual = self._dispatch("read_access_object", dict(clip["locator"], object_type="clip"))[
            "properties"
        ]
        if abs(float(actual["loop_end"]) - end) > 1e-4:
            raise RuntimeError("Clip resize failed readback")

    def _set_warp(self, change):
        clip = self._clip(change["target"])
        if clip["type"] != "audio":
            raise ValueError("Warp settings apply to audio clips only")
        patch = dict(change.get("patch", {}))
        unknown = sorted(set(patch) - WARP_PROPERTIES)
        if unknown:
            raise UnsupportedOperations("warp properties: " + ", ".join(unknown))
        if not patch:
            return
        self._dispatch("set_access_warp", dict(clip["locator"], properties=patch))
        actual = self._dispatch("read_access_object", dict(clip["locator"], object_type="clip"))[
            "properties"
        ]
        for key, value in patch.items():
            if actual.get(key) != value:
                raise RuntimeError("Warp readback failed: " + key)

    # ---- state refresh ----------------------------------------------------
    def _refresh(self):
        if self._refresh_state is not None:
            self._state = deepcopy(self._refresh_state())
            return
        from .song_lint import collect_live

        self._state = collect_live(
            SimpleNamespace(send_command=self._dispatch), include_session=True
        )
