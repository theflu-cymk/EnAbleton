"""Explicit Live Object Model access; no arbitrary Python or undocumented UI calls."""

from .envelope_support import index, number

PROPERTIES = {
    "song": {
        "tempo": (20, 999),
        "swing_amount": (0, 1),
        "loop": bool,
        "loop_start": (0, 1576800),
        "loop_length": (0.001, 1576800),
        "metronome": bool,
        "signature_numerator": (1, 99),
        "signature_denominator": (1, 16),
    },
    "track": {"name": str, "mute": bool, "solo": bool, "arm": bool, "color_index": (0, 69)},
    "scene": {"name": str, "color_index": (0, 69), "tempo": (20, 999)},
    "clip": {
        "name": str,
        "color_index": (0, 69),
        "looping": bool,
        "loop_start": (-16384, 1576800),
        "loop_end": (-16384, 1576800),
        "gain": (0, 1),
        "pitch_coarse": (-48, 48),
        "pitch_fine": (-50, 50),
        "warping": bool,
    },
    "chain": {"name": str, "mute": bool, "solo": bool},
}


class AccessSupportMixin(object):
    def _get_audio_clip_timing(self, args):
        track, clip = self._access_clip(args)
        if not clip.is_audio_clip:
            raise ValueError("Audio clip required")
        markers = []
        for marker in clip.warp_markers:
            if len(markers) >= 20000:
                raise ValueError("More than 20000 warp markers; refusing truncated read")
            markers.append(
                {"beat_time": float(marker.beat_time), "sample_time": float(marker.sample_time)}
            )
        result = {
            "track_name": track.name,
            "clip_name": clip.name,
            "file_path": clip.file_path,
            "warping": bool(clip.warping),
            "warp_mode": int(clip.warp_mode),
            "looping": bool(clip.looping),
            "loop_start": float(clip.loop_start),
            "loop_end": float(clip.loop_end),
            "start_marker": float(clip.start_marker),
            "end_marker": float(clip.end_marker),
            "pitch_coarse": int(clip.pitch_coarse),
            "pitch_fine": float(clip.pitch_fine),
            "warp_markers": markers,
            "marker_count": len(markers),
            "units": "warp beat_time in clip beats; sample_time in source seconds. Loop/marker positions are beats when warped, seconds when unwarped.",
            "read_only": True,
            "limits": "Coordinates only; not a claim that transients or musical downbeats are correct.",
        }
        for key in ("sample_length", "sample_rate", "signature_numerator", "signature_denominator"):
            if hasattr(clip, key):
                result[key] = getattr(clip, key)
        if hasattr(clip, "available_warp_modes"):
            result["available_warp_modes"] = list(clip.available_warp_modes)
        if hasattr(self, "_warp_clip_identity"):
            result["clip_identity"] = self._warp_clip_identity(clip)
        result["marker_api"] = {
            name: callable(getattr(clip, name, None))
            for name in ("move_warp_marker", "add_warp_marker", "remove_warp_marker")
        }
        if args.get("clip_view") == "arrangement":
            result.update(
                arrangement_start=float(clip.start_time), arrangement_end=float(clip.end_time)
            )
        return result

    def _access_clip(self, args):
        track = self._access_track(args)
        if args.get("clip_view", "session") == "arrangement":
            clip = index(args.get("clip_index"), list(track.arrangement_clips), "clip_index")
            if (
                args.get("expected_start_time") is not None
                and abs(clip.start_time - args["expected_start_time"]) > 1e-5
            ):
                raise ValueError("Arrangement clip start changed")
        elif args.get("clip_view", "session") == "session":
            slot = index(args.get("clip_index"), track.clip_slots, "clip_index")
            if not slot.has_clip:
                raise ValueError("Session slot is empty")
            clip = slot.clip
        else:
            raise ValueError("clip_view must be session or arrangement")
        if args.get("expected_clip_name") is not None and clip.name != args["expected_clip_name"]:
            raise ValueError("expected_clip_name no longer matches")
        return track, clip

    def _access_object(self, args):
        kind = args.get("object_type")
        if kind == "song":
            return self._song
        if kind == "track":
            return self._access_track(args)
        if kind == "scene":
            return index(args.get("scene_index"), self._song.scenes, "scene_index")
        if kind == "clip":
            return self._access_clip(args)[1]
        if kind == "chain":
            track, device = self._sound_design_target(args)
            chain = index(args.get("chain_index"), device.chains, "chain_index")
            if (
                args.get("expected_chain_name") is not None
                and chain.name != args["expected_chain_name"]
            ):
                raise ValueError("expected_chain_name no longer matches")
            return chain
        raise ValueError("Unsupported object_type")

    def _read_access_object(self, args):
        kind = args.get("object_type")
        obj = self._access_object(args)
        values, unavailable = {}, []
        for key in PROPERTIES[kind]:
            try:
                values[key] = getattr(obj, key)
            except (AttributeError, RuntimeError):
                unavailable.append(key)
        return {"object_type": kind, "properties": values, "unavailable": unavailable}

    def _write_access_object(self, args):
        kind = args.get("object_type")
        obj = self._access_object(args)
        changes = args.get("properties")
        if not isinstance(changes, dict) or not 1 <= len(changes) <= 16:
            raise ValueError("Provide 1..16 property changes")
        if kind in ("track", "clip") and not args.get("expected_track_name"):
            raise ValueError("Track name guard required")
        if kind == "clip" and not args.get("expected_clip_name"):
            raise ValueError("Clip name guard required")
        if (
            kind == "clip"
            and args.get("clip_view") == "arrangement"
            and args.get("expected_start_time") is None
        ):
            raise ValueError("Arrangement start guard required")
        if kind == "chain" and not args.get("expected_chain_name"):
            raise ValueError("Chain name guard required")
        planned = []
        for key, value in changes.items():
            rule = PROPERTIES[kind].get(key)
            if rule is None:
                raise ValueError("Property is not exposed for writing: " + key)
            if rule is bool:
                if not isinstance(value, bool):
                    raise ValueError(key + " must be boolean")
            elif rule is str:
                if not isinstance(value, str) or len(value) > 256:
                    raise ValueError("Name must be <=256 characters")
            else:
                value = number(value, key)
                if not rule[0] <= value <= rule[1]:
                    raise ValueError(key + " out of range")
                if key in (
                    "color_index",
                    "pitch_coarse",
                    "pitch_fine",
                    "signature_numerator",
                    "signature_denominator",
                ):
                    if value != int(value):
                        raise ValueError(key + " must be integer")
                    value = int(value)
                if key == "signature_denominator" and value not in (1, 2, 4, 8, 16):
                    raise ValueError("Invalid time signature denominator")
            planned.append((key, value, getattr(obj, key)))
        self._song.begin_undo_step()
        applied = []
        try:
            for key, value, old in planned:
                applied.append((key, old))
                setattr(obj, key, value)
                actual = getattr(obj, key)
                if isinstance(value, (float, int)) and not isinstance(value, bool):
                    if abs(actual - value) > 1e-5:
                        raise RuntimeError(key + " readback differs")
                elif actual != value:
                    raise RuntimeError(key + " readback differs")
        except Exception as error:
            failed = []
            for key, old in reversed(applied):
                try:
                    setattr(obj, key, old)
                except Exception:
                    failed.append(key)
            raise RuntimeError(
                "Write failed; "
                + ("rollback incomplete, use Live Undo" if failed else "previous values restored")
                + ": "
                + str(error)
            )
        finally:
            self._song.end_undo_step()
        return {"verified": True, "properties": {key: getattr(obj, key) for key in changes}}

    def _get_access_mixer(self, args):
        obj = self._access_object(
            dict(args, object_type="chain" if args.get("chain_index") is not None else "track")
        )
        mixer = obj.mixer_device
        return {
            "name": obj.name,
            "parameters": {
                "volume": self._sound_design_parameter_info(mixer.volume, 0),
                "pan": self._sound_design_parameter_info(mixer.panning, 0),
            },
            "sends": [self._sound_design_parameter_info(p, i) for i, p in enumerate(mixer.sends)],
        }

    def _set_access_mixer(self, args):
        is_chain = args.get("chain_index") is not None
        if not args.get("expected_track_name") or (
            is_chain and not args.get("expected_chain_name")
        ):
            raise ValueError("Expected track and chain names required")
        obj = self._access_object(dict(args, object_type="chain" if is_chain else "track"))
        changes = args.get("parameters")
        if not isinstance(changes, dict) or not 1 <= len(changes) <= 32:
            raise ValueError("Provide 1..32 mixer changes")
        mixer = obj.mixer_device
        planned = []
        for key, value in changes.items():
            if key == "volume":
                p = mixer.volume
            elif key == "pan":
                p = mixer.panning
            elif key.startswith("send:"):
                p = index(int(key[5:]), mixer.sends, "send_index")
            else:
                raise ValueError("Use volume, pan or send:N")
            value = number(value, key)
            if (
                not p.min <= value <= p.max
                or not p.is_enabled
                or int(getattr(p, "automation_state", 0))
            ):
                raise ValueError("Disabled, automated or out-of-range mixer parameter: " + key)
            planned.append((p, value, p.value))
        self._song.begin_undo_step()
        applied = []
        try:
            for p, value, old in planned:
                applied.append((p, old))
                p.value = value
                if abs(p.value - value) > 1e-5:
                    raise RuntimeError("Mixer readback differs")
        except Exception as error:
            failed = []
            for p, old in reversed(applied):
                try:
                    p.value = old
                except Exception:
                    failed.append(p.name)
            raise RuntimeError(
                "Mixer failed; "
                + ("rollback incomplete; use Live Undo" if failed else "previous values restored")
                + ": "
                + str(error)
            )
        finally:
            self._song.end_undo_step()
        return dict(self._get_access_mixer(args), verified=True)

    def _get_access_notes(self, args):
        track, clip = self._access_clip(args)
        if not clip.is_midi_clip:
            raise ValueError("MIDI clip required")
        if not hasattr(clip, "get_all_notes_extended"):
            raise RuntimeError("Full-range note API unavailable; refusing a partial read")
        notes = []
        for n in clip.get_all_notes_extended():
            notes.append(
                {
                    k: getattr(n, k)
                    for k in (
                        "note_id",
                        "pitch",
                        "start_time",
                        "duration",
                        "velocity",
                        "mute",
                        "probability",
                        "velocity_deviation",
                        "release_velocity",
                    )
                    if hasattr(n, k)
                }
            )
        return {
            "track_name": track.name,
            "clip_name": clip.name,
            "loop_start": clip.loop_start,
            "loop_end": clip.loop_end,
            "note_count": len(notes),
            "notes": notes,
        }

    def _modify_access_notes(self, args):
        if not args.get("expected_track_name") or not args.get("expected_clip_name"):
            raise ValueError("Track and clip name guards required")
        if args.get("clip_view") == "arrangement" and args.get("expected_start_time") is None:
            raise ValueError("Arrangement start guard required")
        track, clip = self._access_clip(args)
        if clip.is_recording:
            raise ValueError("Stop clip recording first")
        current = self._get_access_notes(args)["notes"]
        by_id = {n["note_id"]: n for n in current}
        changes = args.get("notes")
        allowed = {
            "pitch": (0, 127),
            "start_time": (-16384, 16384),
            "duration": (0.001, 32768),
            "velocity": (1, 127),
            "probability": (0, 1),
            "velocity_deviation": (-127, 127),
            "release_velocity": (0, 127),
        }
        if not isinstance(changes, list) or not 1 <= len(changes) <= 10000:
            raise ValueError("Provide 1..10000 note modifications")
        updates = []
        seen = set()
        for change in changes:
            ident = change.get("note_id")
            if (
                isinstance(ident, bool)
                or not isinstance(ident, int)
                or ident not in by_id
                or ident in seen
            ):
                raise ValueError("Unknown or duplicate note ID")
            seen.add(ident)
            note = dict(by_id[ident])
            for key, value in change.items():
                if key == "note_id":
                    continue
                if key == "mute":
                    if not isinstance(value, bool):
                        raise ValueError("mute must be boolean")
                elif key in allowed:
                    value = number(value, key)
                    lo, hi = allowed[key]
                    if not lo <= value <= hi or (key == "pitch" and value != int(value)):
                        raise ValueError("Invalid " + key)
                    if key == "pitch":
                        value = int(value)
                else:
                    raise ValueError("Unsupported note field")
                note[key] = value
            updates.append(note)
        if not callable(getattr(clip, "apply_note_modifications", None)):
            raise RuntimeError("Note modification API unavailable")
        raw_notes = {n.note_id: n for n in clip.get_all_notes_extended()}

        def apply(rows):
            objects = []
            for row in rows:
                obj = raw_notes[row["note_id"]]
                for key, value in row.items():
                    if key != "note_id":
                        setattr(obj, key, value)
                objects.append(obj)
            clip.apply_note_modifications(tuple(objects))

        self._song.begin_undo_step()
        try:
            apply(updates)
            after = {n["note_id"]: n for n in self._get_access_notes(args)["notes"]}
            for note in updates:
                for key, value in note.items():
                    actual = after[note["note_id"]][key]
                    if isinstance(value, (int, float)) and abs(actual - value) > 1e-4:
                        raise RuntimeError("Note verification failed")
                    elif not isinstance(value, (int, float)) and actual != value:
                        raise RuntimeError("Note verification failed")
        except Exception as error:
            try:
                apply([by_id[n["note_id"]] for n in updates])
            except Exception:
                raise RuntimeError("Note edit rollback incomplete; use Live Undo")
            raise RuntimeError("Note edit failed; previous notes restored: " + str(error))
        finally:
            self._song.end_undo_step()
        return {"verified": True, "modified_notes": len(updates), "note_count": len(current)}
