"""Live-side duplicate-only warp repair. Original clip is never edited."""

import uuid
from .envelope_support import number
from .warp_analysis import plan_moves, timing_fingerprint


class WarpSupportMixin(object):
    def _warp_clip_identity(self, clip):
        if not hasattr(self, "_warp_identities"):
            self._warp_identities = []
        for ref, identity in self._warp_identities:
            if ref == clip:
                return identity
        identity = uuid.uuid4().hex
        self._warp_identities.append((clip, identity))
        self._warp_identities = self._warp_identities[-512:]
        return identity

    def _repair_warp_duplicate(self, args):
        target = args.get("target", {})
        if not target.get("expected_track_name") or not target.get("expected_clip_name"):
            raise ValueError("Track and clip name guards required")
        if target.get("clip_view") == "arrangement" and target.get("expected_start_time") is None:
            raise ValueError("Arrangement start guard required")
        track, original = self._access_clip(target)
        if original.is_recording or getattr(track, "is_frozen", False):
            raise ValueError("Recording/frozen source cannot be repaired")
        before = self._get_audio_clip_timing(target)
        if args.get("expected_fingerprint") != timing_fingerprint(before):
            raise ValueError("Stale warp preview; inspect and preview again")
        if not before["marker_api"]["move_warp_marker"]:
            raise RuntimeError("This Live build has no warp marker move API")
        plan = plan_moves(before, args.get("moves"), args.get("max_shift_beats", 0.125))
        destination = number(args.get("destination_time"), "destination_time")
        length = (
            original.end_time - original.start_time
            if target.get("clip_view") == "arrangement"
            else original.length
        )
        if not 0 <= destination <= 1576800 or length <= 0 or destination + length > 1576800:
            raise ValueError("Invalid preview destination")
        existing = list(track.arrangement_clips)
        operation = args.get("operation_id", uuid.uuid4().hex)
        if (
            not isinstance(operation, str)
            or len(operation) != 32
            or any(ch not in "0123456789abcdef" for ch in operation)
        ):
            raise ValueError("Invalid operation ID")
        prefix = "Warp Preview " + operation[:8] + " | "
        if any(clip.name.startswith(prefix) for clip in existing):
            raise ValueError(
                "This preview operation already exists; inspect it instead of retrying"
            )
        if any(
            destination < clip.end_time - 1e-6 and destination + length > clip.start_time + 1e-6
            for clip in existing
        ):
            raise ValueError("Preview destination overlaps existing Arrangement content")
        mode = args.get("warp_mode")
        if mode is not None:
            if (
                isinstance(mode, bool)
                or not isinstance(mode, int)
                or mode not in before.get("available_warp_modes", [])
            ):
                raise ValueError("Warp mode unavailable for this clip")
        clone = None
        self._song.begin_undo_step()
        try:
            track.duplicate_clip_to_arrangement(original, destination)
            new = [
                clip for clip in track.arrangement_clips if not any(clip == old for old in existing)
            ]
            if len(new) != 1:
                raise RuntimeError("Could not identify exactly one new preview clip")
            clone = new[0]
            clone.name = (prefix + original.name)[:256]
            for move in plan["moves"]:
                clone.move_warp_marker(move["beat_time"], move["new_beat_time"] - move["beat_time"])
            if mode is not None:
                clone.warp_mode = mode
            clone_index = next(i for i, clip in enumerate(track.arrangement_clips) if clip == clone)
            clone_target = dict(
                target,
                clip_view="arrangement",
                clip_index=clone_index,
                expected_clip_name=clone.name,
                expected_start_time=destination,
            )
            after = self._get_audio_clip_timing(clone_target)
            if len(after["warp_markers"]) != len(plan["after_markers"]):
                raise RuntimeError("Marker count differs after repair")
            for actual, expected in zip(after["warp_markers"], plan["after_markers"]):
                if any(abs(actual[k] - expected[k]) > 1e-5 for k in ("beat_time", "sample_time")):
                    raise RuntimeError("Warp marker readback differs")
            if (
                abs(after["arrangement_start"] - destination) > 1e-5
                or abs(after["arrangement_end"] - (destination + length)) > 1e-4
            ):
                raise RuntimeError("Preview placement/length changed")
            if mode is not None and after["warp_mode"] != mode:
                raise RuntimeError("Warp mode readback differs")
            fresh_original = dict(target)
            if target.get("clip_view") == "arrangement":
                fresh_original["clip_index"] = next(
                    i for i, clip in enumerate(track.arrangement_clips) if clip == original
                )
            if (
                timing_fingerprint(self._get_audio_clip_timing(fresh_original))
                != plan["before_fingerprint"]
            ):
                raise RuntimeError("Original clip changed during preview creation")
        except Exception as error:
            cleanup = "no preview identified"
            if clone is not None:
                try:
                    track.delete_clip(clone)
                    cleanup = "new preview removed"
                except Exception:
                    cleanup = "preview cleanup failed; inspect track and use Live Undo"
            raise RuntimeError("Warp repair failed; " + cleanup + ": " + str(error)) from error
        finally:
            self._song.end_undo_step()
        return {
            "verified": True,
            "operation_id": operation,
            "original_preserved": True,
            "preview_target": clone_target,
            "before": before,
            "after": after,
            "next": "Audition original and preview at matched levels; this tool does not replace the original or start playback.",
        }
