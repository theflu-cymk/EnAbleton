"""Guarded Arrangement clip edits: move, split, delete and audio import.

`Clip.start_time` is get-only, so a move is a duplicate at the destination plus a
delete of the original. Every entry point requires `expected_start_time`, verifies
the result, and refuses unwarped audio where markers are seconds rather than beats.
"""

import math
import os

from .clip_geometry import conflicts, plan_move, plan_split


def _number(value, key):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(key + " must be a number")
    if not math.isfinite(value):
        raise ValueError(key + " must be finite")
    return float(value)


class ClipEditMixin(object):
    def _require_beat_units(self, clip):
        if clip.is_audio_clip and not clip.warping:
            raise ValueError(
                "unwarped audio measures markers in seconds; warp or render it before "
                "moving or slicing in beats"
            )

    def _clip_at(self, clips, start):
        for position, clip in enumerate(clips):
            if abs(float(clip.start_time) - start) < 1e-6:
                return position
        raise ValueError("clip not found at the guarded start")

    def _guarded_clip(self, args):
        track = self._access_track(args)
        clips = list(track.arrangement_clips)
        if args.get("expected_start_time") is None:
            raise ValueError("expected_start_time guard required")
        position = self._clip_at(clips, float(args["expected_start_time"]))
        clip = clips[position]
        if args.get("expected_clip_name") is not None and clip.name != args["expected_clip_name"]:
            raise ValueError("expected_clip_name no longer matches")
        return track, clips, position, clip

    def _move_arrangement_clip(self, args):
        track, clips, position, clip = self._guarded_clip(args)
        self._require_beat_units(clip)
        start, end = float(clip.start_time), float(clip.end_time)
        destination, target_end, length = plan_move(
            start, end, _number(args.get("destination_start"), "destination_start")
        )
        spans = [(float(other.start_time), float(other.end_time)) for other in clips]
        blocked = conflicts(destination, target_end, spans, position)
        if blocked:
            raise ValueError("destination would overwrite clips at index " + str(blocked))
        self._song.begin_undo_step()
        try:
            placed = track.duplicate_clip_to_arrangement(clip, destination)
            if placed is None:
                raise RuntimeError("duplicate_clip_to_arrangement returned no clip")
            track.delete_clip(clip)
            matches = [
                other
                for other in track.arrangement_clips
                if abs(float(other.start_time) - destination) < 1e-3
            ]
            if not matches:
                raise RuntimeError("moved clip not found after the write")
            placed = matches[0]
        except Exception as error:
            raise RuntimeError(
                "move failed; a copy may remain, use Live Undo: " + str(error)
            ) from error
        finally:
            self._song.end_undo_step()
        return {
            "moved": True,
            "name": placed.name,
            "start_time": float(placed.start_time),
            "end_time": float(placed.end_time),
            "length": length,
            "destination": destination,
            "units": "beats",
        }

    def _split_arrangement_clip(self, args):
        track, _, _, clip = self._guarded_clip(args)
        self._require_beat_units(clip)
        start, end = float(clip.start_time), float(clip.end_time)
        marker_start, marker_end = float(clip.start_marker), float(clip.end_marker)
        (_, left_end), (right_start, _) = plan_split(
            start, end, _number(args.get("split_at"), "split_at")
        )
        offset = left_end - start
        split_marker = marker_start + offset
        self._song.begin_undo_step()
        right = None
        try:
            right = track.duplicate_clip_to_arrangement(clip, right_start)
            if right is None:
                raise RuntimeError("duplicate_clip_to_arrangement returned no clip")
            # A head trim needs a start_marker write. Live ignores it on warped
            # audio, which would leave the right half at the whole clip length.
            right.start_marker = split_marker
            right.end_marker = marker_end
            if abs(float(right.start_marker) - split_marker) > 1e-3:
                raise RuntimeError(
                    "Live ignored the right half's start marker; a split would leave "
                    "the whole clip in place"
                )
            if abs(float(right.start_time) - right_start) > 1e-3:
                raise RuntimeError("right half did not start at the split point")
            if abs(float(right.end_time) - end) > 1e-3:
                raise RuntimeError("right half did not keep the remaining length")
            clip.end_marker = split_marker
            if abs(float(clip.end_time) - left_end) > 1e-3:
                raise RuntimeError("left half did not end at the split point")
        except Exception as error:
            if right is not None:
                try:
                    track.delete_clip(right)
                except Exception as cleanup:
                    raise RuntimeError(
                        "split failed and the duplicate could not be removed; use Live Undo: "
                        + str(cleanup)
                    ) from error
            raise RuntimeError("split cancelled; no change kept: " + str(error)) from error
        finally:
            self._song.end_undo_step()
        return {
            "split": True,
            "left": {"start": start, "end": float(clip.end_time)},
            "right": {"start": float(right.start_time), "end": float(right.end_time)},
            "units": "beats",
        }

    def _delete_arrangement_clip_guarded(self, args):
        track, _, _, clip = self._guarded_clip(args)
        info = {"name": clip.name, "start_time": float(clip.start_time)}
        self._song.begin_undo_step()
        try:
            track.delete_clip(clip)
        finally:
            self._song.end_undo_step()
        info["deleted"] = True
        info["remaining"] = len(list(track.arrangement_clips))
        return info

    def _create_arrangement_audio_clip(self, args):
        """Import a file onto an audio track's Arrangement at a free beat.

        Live's Track.create_audio_clip writes straight to the timeline. The
        length is only known after the import, so an overlap discovered then
        is removed before the command returns.
        """
        if not isinstance(args.get("expected_track_name"), str) or not args.get(
            "expected_track_name"
        ):
            raise ValueError("expected_track_name is required")
        path = args.get("path", args.get("file_path"))
        if not isinstance(path, str) or not path:
            raise ValueError("path is required")
        if not os.path.isabs(path):
            raise ValueError("path must be an absolute file path")
        if not os.path.isfile(path):
            raise ValueError("audio file does not exist")
        position = _number(args.get("position"), "position")
        if position < 0:
            raise ValueError("position must be >= 0 beats")
        track = self._access_track(args)
        if getattr(track, "has_midi_input", False) or not getattr(track, "has_audio_input", False):
            raise ValueError("track is not an audio track")
        creator = getattr(track, "create_audio_clip", None)
        if not callable(creator):
            raise RuntimeError(
                "This Live build does not expose Track.create_audio_clip; "
                "import into a Session slot with create_audio_clip instead"
            )
        for clip in list(track.arrangement_clips):
            start, end = float(clip.start_time), float(clip.end_time)
            if start - 1e-6 <= position < end:
                raise ValueError(
                    "position is inside an existing arrangement clip; choose a free beat"
                )
        self._song.begin_undo_step()
        try:
            # Live builds a new wrapper every time arrangement_clips is read, so
            # object identity cannot tell the import from a clip that was already there.
            before = [
                (float(clip.start_time), float(clip.end_time))
                for clip in list(track.arrangement_clips)
            ]
            creator(path, position)
            fresh = []
            pool = list(before)
            for clip in list(track.arrangement_clips):
                start, end = float(clip.start_time), float(clip.end_time)
                match_at = None
                for index, (old_start, old_end) in enumerate(pool):
                    if abs(old_start - start) < 1e-3 and abs(old_end - end) < 1e-3:
                        match_at = index
                        break
                if match_at is None:
                    fresh.append(clip)
                else:
                    pool.pop(match_at)
            at_position = [clip for clip in fresh if abs(float(clip.start_time) - position) < 1e-3]
            if len(at_position) != 1 or len(fresh) != 1:
                for clip in fresh:
                    track.delete_clip(clip)
                raise RuntimeError(
                    "imported clip was not found at the requested beat; "
                    "inspect the track and undo if a clip remains"
                )
            created = at_position[0]
            start, end = float(created.start_time), float(created.end_time)
            skipped = False
            for other in list(track.arrangement_clips):
                other_start, other_end = float(other.start_time), float(other.end_time)
                if not skipped and abs(other_start - start) < 1e-3 and abs(other_end - end) < 1e-3:
                    skipped = True
                    continue
                if start < other_end - 1e-6 and other_start < end - 1e-6:
                    track.delete_clip(created)
                    raise ValueError(
                        "imported clip overlapped an existing arrangement clip; it was removed"
                    )
        finally:
            self._song.end_undo_step()
        return {
            "imported": True,
            "name": created.name,
            "start_time": start,
            "end_time": end,
            "length": end - start,
            "is_audio_clip": bool(getattr(created, "is_audio_clip", True)),
            "path": path,
            "units": "beats",
            "playback_started": False,
        }
