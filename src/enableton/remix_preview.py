"""Bounded real-time Live resampling with explicit mixer/transport restoration."""

import math
from pathlib import Path
import time
from uuid import uuid4

from .bass_tools import _mutation_lock
from .live_reads import read_many
from .remix_assets import atomic_json, project, project_lock, save_project
from .remix_live import _track, _verify_owned_content, batch, command, worker
from .warp_analysis import beat_to_source


def capture(send, project_dir, bars=8, include_lead_in=True, sleep=time.sleep):
    if type(bars) is not int or not 1 <= bars <= 16:
        raise ValueError("Preview 1..16 drop bars")
    root, manifest = project(project_dir)
    with _mutation_lock, project_lock(root):
        if manifest.get("state") != "built":
            raise ValueError("Complete the current build before previewing")
        _verify_owned_content(send, manifest)
        original = send("get_session_info", {})
        if original["is_playing"] or original.get("record_mode"):
            raise ValueError("Stop existing playback/recording before a preview")
        plan = manifest["prepared"]["plan"]
        tempo = plan["grid"]["tempo"]
        if abs(original["tempo"] - tempo) > 0.001:
            raise ValueError("Preview tempo differs from build")
        start = plan["grid"]["drop_start_beat"] - (
            plan["config"]["lead_in_bars"] * 4 if include_lead_in else 0
        )
        end = plan["grid"]["drop_start_beat"] + min(bars, plan["config"]["drop_bars"]) * 4
        if start < 4:
            raise ValueError(
                "Leave at least one bar before the preview window for verified recording punch-in"
            )
        preroll = max(0, start - 16)
        duration = (end - preroll) * 60 / tempo
        if duration > 60:
            raise ValueError("Preview exceeds 60 seconds; reduce its length")
        reads = read_many(
            send, [command("get_track_info", track_index=i) for i in range(original["track_count"])]
        )
        if any(e for _, e in reads):
            raise ValueError("Cannot snapshot mixer state for preview")
        tracks = [t for t, _ in reads]
        if any(t.get("playing_slot_index", -1) >= 0 for t in tracks):
            raise ValueError("Stop Session clips before Arrangement preview capture")
        audible = {
            t["index"]
            for role, t in manifest["tracks"].items()
            if role != "control" and role in manifest.get("active_roles", manifest["tracks"])
        }
        # The manifest stores "index" for owned tracks, unlike Live's response.
        temp = None
        temp_name = "RMX PREVIEW " + uuid4().hex[:12]
        cleanup_errors = []
        result = None
        failure = None
        journal = dict(
            state="capturing",
            original=original,
            tracks=[{k: t[k] for k in ["index", "name", "arm", "mute", "solo"]} for t in tracks],
            temp_name=temp_name,
        )
        atomic_json(root / "preview-operation.json", journal)
        try:
            batch(
                send,
                [
                    command("set_track_arm", track_index=t["index"], arm=False)
                    for t in tracks
                    if t["arm"]
                ],
            )
            changes = []
            for t in tracks:
                changes.extend(
                    [
                        command("set_track_solo", track_index=t["index"], solo=False),
                        command(
                            "set_track_mute", track_index=t["index"], mute=t["index"] not in audible
                        ),
                    ]
                )
            batch(send, changes)
            created = send("create_audio_track", dict(index=-1))
            temp = created.get("index", created.get("track_count", original["track_count"] + 1) - 1)
            send("set_track_name", dict(track_index=temp, name=temp_name))
            fresh = send("get_track_info", dict(track_index=temp))
            if fresh["name"] != temp_name:
                raise ValueError("Temporary preview track identity changed")
            batch(
                send,
                [
                    command("set_track_monitoring", track_index=temp, state=2),
                    command(
                        "set_track_routing",
                        track_index=temp,
                        field="input_routing_type",
                        display_name="Resampling",
                    ),
                    command(
                        "set_track_routing",
                        track_index=temp,
                        field="output_routing_type",
                        display_name="Sends Only",
                    ),
                    command("set_track_arm", track_index=temp, arm=True),
                    command(
                        "set_loop",
                        start=original["loop_start"],
                        length=original["loop_length"],
                        enabled=False,
                    ),
                ],
            )
            # Move transport while NOT recording, verify it, then punch in early.
            # This avoids both the insert-marker reset and a jump during recording.
            send("start_playback", {})
            send("set_current_song_time", dict(time=preroll))
            observed = send("get_session_info", {})
            journal["transport_before_record"] = observed
            atomic_json(root / "preview-operation.json", journal)
            if (
                not observed["is_playing"]
                or observed["current_song_time"] >= start - 1
                or abs(observed["current_song_time"] - preroll) > max(8, tempo / 60 * 3)
            ):
                raise RuntimeError("Transport did not settle before the preview window")
            send("set_record_mode", dict(enabled=True))
            observed = send("get_session_info", {})
            journal["transport_after_record"] = observed
            atomic_json(root / "preview-operation.json", journal)
            if (
                not observed["is_playing"]
                or not observed["record_mode"]
                or observed["current_song_time"] >= start
            ):
                raise RuntimeError("Recording did not start before the requested window")
            deadline = time.monotonic() + duration + 10
            while observed["current_song_time"] < end + 0.15:
                if time.monotonic() > deadline:
                    raise TimeoutError("Preview transport did not reach its end")
                sleep(min(0.5, max(0.05, (end - observed["current_song_time"]) * 60 / tempo)))
                observed = send("get_session_info", {})
                if not observed["is_playing"]:
                    raise RuntimeError("Preview transport stopped early")
            send("set_record_mode", dict(enabled=False))
            send("stop_playback", {})
            clips = send("get_arrangement_clips", dict(track_index=temp))["clips"]
            journal["recorded_clips"] = clips
            atomic_json(root / "preview-operation.json", journal)
            covering = [
                (i, c)
                for i, c in enumerate(clips)
                if c["start_time"] <= start + 0.01
                and c["end_time"] >= end - 0.01
                and c.get("file_path")
            ]
            if len(covering) != 1:
                raise RuntimeError(
                    "Recorded clips do not cover the requested window; no success claim"
                )
            index, clip = covering[0]
            timing = send(
                "get_audio_clip_timing",
                dict(
                    track_index=temp,
                    clip_index=index,
                    clip_view="arrangement",
                    expected_track_name=temp_name,
                    expected_clip_name=clip["name"],
                    expected_start_time=clip["start_time"],
                ),
            )
            beat = timing["start_marker"] + (start - clip["start_time"])
            if timing["warping"]:
                seconds = beat_to_source(beat, timing["warp_markers"])
            else:
                seconds = timing["start_marker"] + (start - clip["start_time"]) * 60 / tempo
            journal["recording"] = dict(
                path=timing["file_path"],
                start_seconds=seconds,
                duration=(end - start) * 60 / tempo,
                timing=timing,
            )
            atomic_json(root / "preview-operation.json", journal)
            # On Windows Live may hold its recorded WAV exclusively until the
            # recording track releases it. Retain the verified map, then close it.
            fresh = send("get_track_info", dict(track_index=temp))
            if fresh["name"] != temp_name:
                raise ValueError("Temporary recording track identity changed")
            send("delete_track", dict(track_index=temp))
            temp = None
            journal["temporary_track_removed_before_analysis"] = True
            atomic_json(root / "preview-operation.json", journal)
            result = worker(
                "extract",
                root,
                path=timing["file_path"],
                start_seconds=seconds,
                duration=(end - start) * 60 / tempo,
            )
            result.update(
                start_beat=start,
                end_beat=end,
                build_fingerprint=manifest["built_fingerprint"],
                evidence="Captured Live Resampling output; measurements are not a musical listening verdict",
            )
            manifest.setdefault("previews", []).append(result)
            manifest["previews"] = manifest["previews"][-20:]
            save_project(root, manifest)
        except Exception as error:
            failure = error
        finally:
            for cmd, args in [("set_record_mode", dict(enabled=False)), ("stop_playback", {})]:
                try:
                    send(cmd, args)
                except Exception as error:
                    cleanup_errors.append(str(error))
            if temp is not None:
                try:
                    current = send("get_track_info", dict(track_index=temp))
                    if current["name"] != temp_name:
                        raise ValueError("Temporary track moved; not deleting an unverified track")
                    send("delete_track", dict(track_index=temp))
                except Exception as error:
                    cleanup_errors.append(str(error))
            current_rows = read_many(
                send, [command("get_track_info", track_index=t["index"]) for t in tracks]
            )
            restore = []
            for t, (current, error) in zip(tracks, current_rows):
                if error or current["name"] != t["name"]:
                    cleanup_errors.append(
                        "Original track identity changed; cannot restore a stale index"
                    )
                    continue
                for field in ["arm", "mute", "solo"]:
                    if current[field] != t[field]:
                        restore.append(
                            command(
                                "set_track_" + field, track_index=t["index"], **{field: t[field]}
                            )
                        )
            try:
                batch(send, restore)
            except Exception as error:
                cleanup_errors.append(str(error))
            try:
                send(
                    "set_loop",
                    dict(
                        start=original["loop_start"],
                        length=original["loop_length"],
                        enabled=original["loop"],
                    ),
                )
                send("set_current_song_time", dict(time=original["current_song_time"]))
                final = send("get_session_info", {})
                if final["is_playing"] or final.get("record_mode"):
                    raise RuntimeError("Transport did not restore to stopped/unarmed")
                if final["track_count"] != original["track_count"]:
                    raise RuntimeError("Temporary capture track was not removed")
                for key in ["loop", "loop_start", "loop_length", "current_song_time"]:
                    if final[key] != original[key]:
                        raise RuntimeError("Transport property not restored: " + key)
                restored = read_many(
                    send, [command("get_track_info", track_index=t["index"]) for t in tracks]
                )
                for before, (after, error) in zip(tracks, restored):
                    if error or any(after[k] != before[k] for k in ["name", "arm", "mute", "solo"]):
                        raise RuntimeError("Mixer/arm state failed final readback")
            except Exception as error:
                cleanup_errors.append(str(error))
            journal.update(
                state="restored" if not cleanup_errors else "needs_recovery",
                cleanup_errors=cleanup_errors,
                error=str(failure) if failure else None,
            )
            atomic_json(root / "preview-operation.json", journal)
        if failure or cleanup_errors:
            raise RuntimeError(
                "Preview failed or state restoration needs inspection: "
                + str(failure or cleanup_errors)
            ) from failure
        result["state_restored"] = True
        return result
