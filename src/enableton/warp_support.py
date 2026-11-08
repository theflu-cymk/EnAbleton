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

    def _live_warp_marker(self, beat, sample):
        """Build Live's WarpMarker, which current builds require instead of two floats."""
        try:
            from Live.Clip import WarpMarker
        except Exception:
            try:
                import Live

                WarpMarker = Live.Clip.WarpMarker
            except Exception:
                return None
        try:
            return WarpMarker(beat, sample)
        except Exception:
            return None

    def _add_terminal_marker(self, clip, beat, sample):
        """Add one warp marker, probing the marker shapes Live accepts."""
        started = len(clip.warp_markers)
        marker = self._live_warp_marker(beat, sample)
        attempts = []
        if marker is not None:
            attempts.append(("WarpMarker", (marker,)))
        attempts.append(("beat,sample", (beat, sample)))
        attempts.append(("sample,beat", (sample, beat)))
        last_error = None
        for order, arguments in attempts:
            try:
                clip.add_warp_marker(*arguments)
            except Exception as error:
                last_error = error
                if len(clip.warp_markers) != started:
                    raise RuntimeError("A rejected marker add changed the map") from error
                continue
            markers = list(clip.warp_markers)
            if len(markers) == started + 1:
                for marker in markers:
                    if (
                        abs(float(marker.sample_time) - sample) < 0.01
                        and abs(float(marker.beat_time) - beat) < 0.125
                    ):
                        return {
                            "argument_order": order,
                            "beat_time": float(marker.beat_time),
                            "sample_time": float(marker.sample_time),
                        }
            if len(markers) != started and hasattr(clip, "remove_warp_marker"):
                clip.remove_warp_marker(float(markers[-1].beat_time))
            if len(clip.warp_markers) != started:
                raise RuntimeError("Could not restore the map after a rejected add")
        raise RuntimeError(
            "add_warp_marker placed nothing usable" + (": " + str(last_error) if last_error else "")
        )

    def _retime_warp_clip(self, args):
        """Rewrite one clip's marker map to a single source-to-beat rate.

        Keeps the first marker's sample position, so only the rate changes; any
        constant source offset is reported and can be corrected by placement or
        by the loop span. A retime that fails verification leaves the clip part
        edited, so callers retime a fresh duplicate and delete it on failure.
        """
        target = args.get("target", {})
        if not target.get("expected_track_name") or not target.get("expected_clip_name"):
            raise ValueError("Track and clip name guards required")
        if target.get("clip_view") == "arrangement" and target.get("expected_start_time") is None:
            raise ValueError("Arrangement start guard required")
        slope = number(args.get("beats_per_second"), "beats_per_second")
        if not 0.2 <= slope <= 8.0:
            raise ValueError("beats_per_second must be in 0.2..8.0")
        anchor_reference = args.get("anchor_sample")
        if anchor_reference is not None:
            anchor_reference = number(anchor_reference, "anchor_sample")
            if anchor_reference < 0:
                raise ValueError("anchor_sample must be >= 0")
        track, clip = self._access_clip(target)
        if not clip.is_audio_clip:
            raise ValueError("Audio clip required")
        if not clip.warping:
            raise ValueError("Enable Warp before retiming")
        if clip.is_recording or getattr(track, "is_frozen", False):
            raise ValueError("Recording or frozen clip cannot be retimed")
        before = self._get_audio_clip_timing(target)
        api = before.get("marker_api", {})
        if not api.get("move_warp_marker"):
            raise RuntimeError("This Live build has no warp marker move API")
        rows = [(float(m["beat_time"]), float(m["sample_time"])) for m in before["warp_markers"]]
        if len(rows) < 2:
            raise ValueError("Need at least two warp markers")
        for (beat_a, sample_a), (beat_b, sample_b) in zip(rows, rows[1:]):
            if beat_b <= beat_a or sample_b <= sample_a:
                raise ValueError("Warp markers must strictly increase")
        snap = 0.05
        anchor = rows[0][1]
        file_end = None
        if before.get("sample_length") and before.get("sample_rate"):
            file_end = float(before["sample_length"]) / float(before["sample_rate"])
        added = None
        if file_end is not None and file_end - rows[-1][1] > 0.5:
            if not api.get("add_warp_marker"):
                raise RuntimeError(
                    "Clip does not reach the end of its audio and this build cannot add markers"
                )
            added = self._add_terminal_marker(clip, (file_end - anchor) * slope, file_end)
            rows = [(float(m.beat_time), float(m.sample_time)) for m in clip.warp_markers]
        planned = [
            {"beat_time": (sample - anchor) * slope, "sample_time": sample} for _, sample in rows
        ]
        moves = [
            {"beat_time": beat, "new_beat_time": want["beat_time"]}
            for (beat, _), want in zip(rows, planned)
            if abs(want["beat_time"] - beat) > snap / 2
        ]
        if len(moves) > 4096:
            raise ValueError("Too many marker moves for one retime")
        deltas = [move["new_beat_time"] - move["beat_time"] for move in moves]
        if deltas and any(d > 0 for d in deltas) and any(d < 0 for d in deltas):
            raise ValueError("Mixed marker directions are not supported by one retime")
        moves.sort(key=lambda move: move["beat_time"], reverse=bool(deltas) and deltas[0] > 0)
        content = planned[-1]["beat_time"]
        loop_start = 0.0
        if anchor_reference is not None:
            loop_start = max(0.0, (anchor_reference - anchor) * slope)
        self._song.begin_undo_step()
        try:
            for move in moves:
                clip.move_warp_marker(move["beat_time"], move["new_beat_time"] - move["beat_time"])
            clip.loop_start = loop_start
            clip.loop_end = content
            clip.looping = True
            after = self._get_audio_clip_timing(target)
        finally:
            self._song.end_undo_step()
        marks = after["warp_markers"]
        if len(marks) < 2:
            raise RuntimeError("Retime left fewer than two markers")
        first, last = marks[0], marks[-1]
        span_sample = last["sample_time"] - first["sample_time"]
        if span_sample <= 0:
            raise RuntimeError("Retimed markers do not advance in source time")
        tolerance = max(snap, content * 1e-4)
        for marker in marks:
            if abs(marker["beat_time"] - (marker["sample_time"] - anchor) * slope) > tolerance:
                raise RuntimeError("Marker readback differs from the requested rate")
        measured = (last["beat_time"] - first["beat_time"]) / span_sample
        if abs(measured - slope) > 0.002 * slope:
            raise RuntimeError("Measured rate differs from the requested rate")
        if file_end is not None and file_end - last["sample_time"] > 0.5:
            raise RuntimeError("Retimed map does not reach the end of the audio")
        if (
            abs(after["loop_end"] - content) > snap
            or abs(after["loop_start"] - loop_start) > snap
            or not after["looping"]
        ):
            raise RuntimeError("Loop span readback differs")
        residual = 0.0
        if anchor_reference is not None:
            residual = anchor + after["loop_start"] / slope - anchor_reference
        return {
            "verified": True,
            "track_name": target.get("expected_track_name"),
            "clip_name": before["clip_name"],
            "beats_per_second": slope,
            "anchor_sample": anchor,
            "anchor_reference_sample": anchor_reference,
            "content_beats": content,
            "loop_start": after["loop_start"],
            "loop_end": after["loop_end"],
            "marker_moves": len(moves),
            "added_marker": added,
            "residual_source_offset_seconds": residual,
            "before": {
                "markers": before["marker_count"],
                "loop_end": before["loop_end"],
                "warp_mode": before["warp_mode"],
            },
            "after": {"markers": len(marks), "warp_mode": after["warp_mode"]},
            "next": "Audition against the reference and place it. A failed retime leaves this clip partly edited; delete it and start again from the source.",
        }
