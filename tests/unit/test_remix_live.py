"""Fake-Live orchestration tests; these are not an Ableton compatibility certificate."""

from copy import deepcopy
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from enableton.bass_recipes import get_recipe
from enableton.remix_assets import project, read_json, worker_job
from enableton.remix_live import bind_sources, build, prepare
from enableton.remix_preview import capture
from test_remix_audio import sine


class FakeLive:
    def __init__(self, source):
        self.source = str(source)
        self.tempo = 120
        self.playing = False
        self.record = False
        self.time = 27
        self.loop = True
        self.loop_start = 8.0
        self.loop_length = 8.0
        self.calls = []
        self.tracks = []
        self.failed = None
        self.record_start = None
        self.add("Guitar MIDI", True)
        self.add("Guitar Audio", False)
        self.add("Singer", False)
        self.tracks[0]["arm"] = True
        self.tracks[1]["solo"] = True
        notes = [
            dict(
                pitch=37 if i % 2 == 0 else 40,
                start_time=i * 4,
                duration=4.0,
                velocity=90,
                mute=False,
            )
            for i in range(8)
        ]
        self.tracks[0]["arr"] = [self.clip("Guitar", 32, notes=notes, start=0)]
        for i, name in [(1, "Riff"), (2, "Vocal")]:
            self.tracks[i]["arr"] = [self.clip(name, 28, path=self.source, start=0)]

    def add(self, name, midi):
        self.tracks.append(
            dict(
                name=name,
                is_midi_track=midi,
                is_audio_track=not midi,
                arm=False,
                mute=False,
                solo=False,
                volume=0.85,
                devices=[],
                slots=[None] * 8,
                arr=[],
                monitoring=1,
                output="Main",
            )
        )

    def clip(self, name, length, notes=None, path=None, start=None):
        return dict(
            name=name,
            length=length,
            notes=deepcopy(notes or []),
            file_path=path,
            start_time=start,
            end_time=start + length if start is not None else None,
            looping=True,
            warping=bool(path),
            gain=0.4,
            start_marker=0.0,
            end_marker=length,
            loop_start=0.0,
            loop_end=length,
            envelopes={},
        )

    def info(self, i):
        t = self.tracks[i]
        return dict(
            index=i,
            **{
                k: deepcopy(t[k])
                for k in [
                    "name",
                    "is_midi_track",
                    "is_audio_track",
                    "arm",
                    "mute",
                    "solo",
                    "volume",
                ]
            },
            clip_slots=[
                dict(index=j, has_clip=c is not None, clip=dict(name=c["name"]) if c else None)
                for j, c in enumerate(t["slots"])
            ],
            devices=[
                dict(index=j, name=d["name"], class_name=d["class_name"])
                for j, d in enumerate(t["devices"])
            ],
            playing_slot_index=-1,
        )

    def getclip(self, p):
        t = self.tracks[p["track_index"]]
        if p.get("expected_track_name") and t["name"] != p["expected_track_name"]:
            raise ValueError("track guard")
        c = (
            t["arr"][p["clip_index"]]
            if p.get("clip_view") == "arrangement"
            else t["slots"][p["clip_index"]]
        )
        if p.get("expected_clip_name") and c["name"] != p["expected_clip_name"]:
            raise ValueError("clip guard")
        if p.get("expected_start_time") is not None and c["start_time"] != p["expected_start_time"]:
            raise ValueError("start guard")
        return c

    def send(self, kind, p=None):
        p = p or {}
        self.calls.append((kind, deepcopy(p)))
        if kind == "batch":
            rows = [
                dict(type=c["type"], result=self.send(c["type"], c["params"]))
                for c in p["commands"]
            ]
            return dict(executed=len(rows), results=rows)
        if kind == "get_session_info":
            if self.playing:
                self.time += 1.25
            return dict(
                track_count=len(self.tracks),
                tempo=self.tempo,
                signature_numerator=4,
                signature_denominator=4,
                scene_count=8,
                is_playing=self.playing,
                record_mode=self.record,
                current_song_time=self.time,
                loop=self.loop,
                loop_start=self.loop_start,
                loop_length=self.loop_length,
            )
        if kind == "get_track_info":
            return self.info(p["track_index"])
        if kind == "get_arrangement_clips":
            return dict(clips=deepcopy(self.tracks[p["track_index"]]["arr"]))
        if kind == "get_access_notes":
            c = self.getclip(p)
            return dict(
                notes=[
                    dict(
                        n,
                        start_time=float(n["start_time"]),
                        duration=float(n["duration"]),
                        velocity=float(n["velocity"]),
                    )
                    for n in c["notes"]
                ],
                loop_start=c["loop_start"],
                loop_end=c["loop_end"],
            )
        if kind == "get_audio_clip_timing":
            c = self.getclip(p)
            duration = c["length"] * 60 / self.tempo
            return dict(
                track_name=self.tracks[p["track_index"]]["name"],
                clip_name=c["name"],
                file_path=c["file_path"],
                warping=c["warping"],
                start_marker=0.0,
                end_marker=c["length"] if c["warping"] else duration,
                warp_markers=[
                    dict(beat_time=0.0, sample_time=0.0),
                    dict(beat_time=c["length"], sample_time=duration),
                ],
                arrangement_start=c["start_time"],
                arrangement_end=c["end_time"],
                pitch_coarse=0,
                pitch_fine=0,
            )
        if kind in ["read_access_object", "write_access_object"]:
            c = self.getclip(p)
            if kind == "read_access_object":
                return dict(properties={k: c[k] for k in ["gain", "warping", "looping"]})
            c.update(p["properties"])
            return dict(verified=True)
        if kind == "search_browser":
            return dict(matches=[dict(name=p["query"], uri=p["query"], is_loadable=True)])
        if kind in ["create_midi_track", "create_audio_track"]:
            self.add("New Track", kind == "create_midi_track")
            if kind == "create_midi_track":
                for track in self.tracks:
                    track["arm"] = False
                self.tracks[-1]["arm"] = True
            if self.failed == "create_after":
                self.failed = None
                raise TimeoutError("create reply lost")
            return dict(index=len(self.tracks) - 1)
        if kind == "set_track_name":
            self.tracks[p["track_index"]]["name"] = p["name"]
            return {}
        if kind in ["set_track_mute", "set_track_arm", "set_track_solo", "set_track_volume"]:
            field = kind.removeprefix("set_track_")
            self.tracks[p["track_index"]][field] = p[field]
            return {}
        if kind == "set_track_monitoring":
            self.tracks[p["track_index"]]["monitoring"] = p["state"]
            return {}
        if kind == "set_track_routing":
            self.tracks[p["track_index"]][p["field"]] = p["display_name"]
            return {}
        if kind == "load_browser_item":
            name = p["item_uri"]
            values = {}
            for role in ["dubstep_wobble", "clean_sub"]:
                for spec in get_recipe(role)["chain"]:
                    if spec["name"] == name:
                        values.update(spec["parameters"])
            if name == "Utility":
                values["Gain"] = 0.0
            if name == "Auto Filter":
                values.update(
                    {
                        "Type": 0,
                        "Frequency": 0.5,
                        "LFO Wave": 0,
                        "LFO T Mode": 0,
                        "LFO 16th": 4,
                        "LFO Amount": 0.5,
                    }
                )
            self.tracks[p["track_index"]]["devices"].append(
                dict(
                    name="Remove Mud" if name == "EQ Eight" else name,
                    class_name={
                        "Auto Filter": "AutoFilter2",
                        "EQ Eight": "Eq8",
                        "Utility": "StereoGain",
                    }.get(name, name),
                    parameters=values,
                )
            )
            return {}
        if kind == "get_sound_design_parameters":
            i = p.get("device_path", [p.get("device_index", 0)])[0]
            d = self.tracks[p["track_index"]]["devices"][i]
            return dict(
                device_name=d["name"],
                class_name=d["class_name"],
                parameters=[
                    dict(
                        name=k,
                        index=j,
                        value=v,
                        min=-1 if k == "Gain" else 0,
                        max=1 if k in ["Gain", "Volume"] else 64,
                        display_min="-inf dB" if k in ["Gain", "Volume"] else "0",
                        display_max="35 dB" if k == "Gain" else "6 dB",
                        is_quantized=False,
                        is_enabled=True,
                        automation_state=0,
                    )
                    for j, (k, v) in enumerate(d["parameters"].items())
                ],
            )
        if kind == "set_sound_design_parameters":
            self.tracks[p["track_index"]]["devices"][p["device_path"][0]]["parameters"].update(
                p["parameters"]
            )
            return dict(verified=True)
        if kind == "set_device_parameter":
            d = self.tracks[p["track_index"]]["devices"][p["device_index"]]
            value = p["value"]
            if isinstance(value, str):
                value = 1 if value == "High-pass" else float(value.split()[0])
            d["parameters"][p["parameter"]] = value
            if p["parameter"] == "Gain":
                db = (
                    20 * math.log10(1 + value)
                    if -1 < value < 0
                    else (35 * value if value >= 0 else -math.inf)
                )
            elif p["parameter"] == "Volume":
                db = 60 * math.log10(value) + 6 if value > 0 else -math.inf
            else:
                db = value
            return dict(value=value, warning=None, display=f"{db:.2f} dB")
        if kind == "get_drum_pads":
            return dict(
                pads=[
                    dict(note=36, name="Bass Drum"),
                    dict(note=38, name="Snare Drum"),
                    dict(note=42, name="Closed Hi Hat"),
                ]
            )
        if kind == "create_clip":
            t = self.tracks[p["track_index"]]
            if t["slots"][p["clip_index"]] is not None:
                raise ValueError("occupied")
            t["slots"][p["clip_index"]] = self.clip("New Clip", p["length"])
            return {}
        if kind == "create_audio_clip":
            import wave

            with wave.open(p["path"]) as f:
                length = f.getnframes() / f.getframerate() * self.tempo / 60
            self.tracks[p["track_index"]]["slots"][p["clip_index"]] = self.clip(
                "New Audio", length, path=p["path"]
            )
            return {}
        if kind == "set_clip_name":
            self.getclip(p)["name"] = p["name"]
            return {}
        if kind == "add_notes_to_clip":
            self.getclip(p)["notes"] = deepcopy(p["notes"])
            return {}
        if kind == "delete_clip":
            self.tracks[p["track_index"]]["slots"][p["clip_index"]] = None
            return {}
        if kind == "get_clip_envelope":
            return dict(
                exists=(p["device_index"], p["parameter_index"]) in self.getclip(p)["envelopes"]
            )
        if kind == "write_clip_envelope":
            self.getclip(p)["envelopes"][(p["device_index"], p["parameter_index"])] = deepcopy(
                p["points"]
            )
            return dict(verified=True)
        if kind == "duplicate_session_clip_to_arrangement":
            t = self.tracks[p["track_index"]]
            c = deepcopy(self.getclip(p))
            c["start_time"] = p["destination_time"]
            c["end_time"] = c["start_time"] + c["length"]
            t["arr"] = [
                x
                for x in t["arr"]
                if x["end_time"] <= c["start_time"] or x["start_time"] >= c["end_time"]
            ] + [c]
            t["arr"].sort(key=lambda x: x["start_time"])
            if self.failed == "duplicate_after":
                self.failed = None
                raise TimeoutError("duplicate reply lost")
            return {}
        if kind == "set_loop":
            self.loop = p["enabled"]
            self.loop_start = p["start"]
            self.loop_length = p["length"]
            return {}
        if kind == "set_record_mode":
            if p["enabled"] and self.playing and not self.record:
                self.record_start = self.time
            if self.record and not p["enabled"] and self.record_start is not None:
                i = len(self.tracks) - 1
                self.tracks[i]["arr"] = [
                    self.clip(
                        "Recording",
                        self.time - self.record_start,
                        path=self.source,
                        start=self.record_start,
                    )
                ]
            self.record = p["enabled"]
            return {}
        if kind == "continue_playing":
            self.playing = True
            if self.record:
                self.record_start = self.time
            return {}
        if kind == "start_playback":
            self.playing = True
            self.time = 99
            return {}
        if kind == "set_current_song_time":
            self.time = p["time"]
            if self.playing and self.record:
                self.record_start = self.time
            return {}
        if kind == "stop_playback":
            self.playing = False
            return {}
        if kind == "delete_track":
            self.tracks.pop(p["track_index"])
            return {}
        raise AssertionError("Unexpected command " + kind)


def inputs():
    def t(i, track, clip):
        return dict(
            target=dict(
                track_index=i,
                clip_index=0,
                clip_view="arrangement",
                expected_track_name=track,
                expected_clip_name=clip,
                expected_start_time=0,
            )
        )

    return dict(
        tempo=120, drop_bar=3, drop_bars=2, lead_in_bars=1, source_section_start_beat=8
    ), dict(
        riff_midi=t(0, "Guitar MIDI", "Guitar"),
        riff=t(1, "Guitar Audio", "Riff"),
        vocal=t(2, "Singer", "Vocal"),
        rock_context=t(1, "Guitar Audio", "Riff"),
    )


def direct_worker(operation, root, **kw):
    return worker_job(dict(operation=operation, project_dir=str(root), **kw))


class LiveRemixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audio = self.root / "source.wav"
        sine(self.audio, 14)
        self.live = FakeLive(self.audio)
        self.config, self.sources = inputs()
        self.project = str(self.root / "remix")
        self.patch = patch("enableton.remix_live.worker", direct_worker)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.preview_patch = patch("enableton.remix_preview.worker", direct_worker)
        self.preview_patch.start()
        self.addCleanup(self.preview_patch.stop)

    def ready(self):
        prepare(self.live.send, self.config, self.sources, self.project, False)
        return build(self.live.send, self.project)

    def test_shared_stem_timing_replaces_bad_map_without_editing_original(self):
        self.sources["vocal"]["timing_reference"] = deepcopy(self.sources["riff"]["target"])
        self.sources["vocal"]["source_offset_seconds"] = 0.02
        original = deepcopy(self.live.tracks)

        def send(kind, p):
            result = self.live.send(kind, p)
            if kind == "get_audio_clip_timing" and p["track_index"] == 2:
                result["warp_markers"] = [
                    dict(beat_time=0.0, sample_time=2.0),
                    dict(beat_time=28.0, sample_time=25.0),
                ]
            if kind == "batch":
                # Native batch already dispatches its reads; apply the same bad stem map.
                for request, row in zip(p["commands"], result["results"]):
                    if (
                        request["type"] == "get_audio_clip_timing"
                        and request["params"]["track_index"] == 2
                    ):
                        row["result"]["warp_markers"] = [
                            dict(beat_time=0.0, sample_time=2.0),
                            dict(beat_time=28.0, sample_time=25.0),
                        ]
            return result

        _, bound = bind_sources(send, self.config, self.sources)
        self.assertEqual(bound["vocal"]["native_timing"]["warp_markers"][0]["sample_time"], 2.0)
        self.assertEqual(bound["vocal"]["timing"]["warp_markers"][0]["sample_time"], 0.02)
        self.assertEqual(bound["vocal"]["timing_reference"]["target"]["track_index"], 1)
        self.assertEqual(self.live.tracks, original)

    def test_build_and_rebuild_reuse_tracks_and_preserve_sources(self):
        before = deepcopy(self.live.tracks)
        first = self.ready()
        count = len(self.live.tracks)
        created = sum(k.startswith("create_") for k, p in self.live.calls)
        second = build(self.live.send, self.project)
        self.assertEqual(len(self.live.tracks), count)
        self.assertEqual(first["state"], second["state"])
        self.assertEqual(created, sum(k.startswith("create_") for k, p in self.live.calls))
        self.assertEqual(before, self.live.tracks[:3])
        self.assertTrue(all(t["mute"] for t in self.live.tracks[3:]))

    def test_stale_source_refused_before_any_track_mutation(self):
        prepare(self.live.send, self.config, self.sources, self.project, False)
        self.live.tracks[0]["arr"][0]["notes"][0]["pitch"] += 1
        count = len(self.live.calls)
        with self.assertRaises(ValueError):
            build(self.live.send, self.project)
        self.assertFalse(
            any(k.startswith("create_") or k.startswith("set_") for k, p in self.live.calls[count:])
        )

    def test_foreign_owned_midi_edits_are_not_overwritten(self):
        result = self.ready()
        i = result["tracks"]["midbass"]["index"]
        self.live.tracks[i]["arr"][0]["notes"][0]["pitch"] += 1
        with self.assertRaises(ValueError):
            build(self.live.send, self.project)

    def test_control_midi_edit_regenerates_riff_without_duplicate_lanes(self):
        result = self.ready()
        i = result["tracks"]["control"]["index"]
        count = len(self.live.tracks)
        old = read_json(Path(self.project) / "remix-project.json")["prepared"]["assets"]["riff"][
            "path"
        ]
        self.live.tracks[i]["slots"][0]["notes"] = [
            dict(pitch=60, start_time=0, duration=1.0, velocity=100, mute=False)
        ]
        prepare(self.live.send, self.config, self.sources, self.project, False, True)
        new = read_json(Path(self.project) / "remix-project.json")["prepared"]["assets"]["riff"][
            "path"
        ]
        self.assertNotEqual(old, new)
        build(self.live.send, self.project)
        self.assertEqual(len(self.live.tracks), count)

    def test_uncertain_create_never_duplicates_on_retry(self):
        prepare(self.live.send, self.config, self.sources, self.project, False)
        self.live.failed = "create_after"
        with self.assertRaises(RuntimeError):
            build(self.live.send, self.project)
        count = len(self.live.tracks)
        with self.assertRaises(RuntimeError):
            build(self.live.send, self.project)
        self.assertEqual(len(self.live.tracks), count)
        self.assertTrue(read_json(Path(self.project) / "remix-project.json")["pending_create"])

    def test_lost_duplicate_reply_is_inspected_and_resumed(self):
        prepare(self.live.send, self.config, self.sources, self.project, False)
        self.live.failed = "duplicate_after"
        with self.assertRaises(RuntimeError):
            build(self.live.send, self.project)
        result = build(self.live.send, self.project)
        self.assertEqual(result["state"], "built")
        self.assertEqual(len(self.live.tracks), 10)

    def test_preview_jumps_after_start_and_restores_mixer_transport(self):
        self.ready()
        before = [self.live.info(i) for i in range(len(self.live.tracks))]
        initial = self.live.send("get_session_info")
        result = capture(self.live.send, self.project, bars=2, sleep=lambda _: None)
        self.assertTrue(result["state_restored"])
        self.assertTrue(Path(result["path"]).exists())
        after = [self.live.info(i) for i in range(len(self.live.tracks))]
        self.assertEqual(before, after)
        self.assertEqual(initial, self.live.send("get_session_info"))
        kinds = [k for k, p in self.live.calls]
        start = kinds.index("start_playback")
        jump = kinds.index("set_current_song_time", start)
        record = kinds.index("set_record_mode", jump)
        self.assertLess(start, jump)
        self.assertLess(jump, record)
        self.assertIsNotNone(result["measurements"]["integrated_lufs"])

    def test_preview_releases_recording_track_before_reading_wav(self):
        self.ready()
        count = len(self.live.tracks)

        def extract(operation, root, **kw):
            self.assertEqual(len(self.live.tracks), count)
            self.assertEqual(operation, "extract")
            return direct_worker(operation, root, **kw)

        with patch("enableton.remix_preview.worker", extract):
            result = capture(self.live.send, self.project, bars=2, sleep=lambda _: None)
        self.assertTrue(result["state_restored"])
        journal = read_json(Path(self.project) / "preview-operation.json")
        self.assertTrue(journal["temporary_track_removed_before_analysis"])
        self.assertIn("timing", journal["recording"])

    def test_preview_failure_still_restores_arm_mute_solo(self):
        self.ready()
        before = [self.live.info(i) for i in range(len(self.live.tracks))]
        with patch("enableton.remix_preview.worker", side_effect=RuntimeError("decode failed")):
            with self.assertRaises(RuntimeError):
                capture(self.live.send, self.project, bars=2, sleep=lambda _: None)
        self.assertEqual(before, [self.live.info(i) for i in range(len(self.live.tracks))])
        self.assertFalse(self.live.record)
        self.assertFalse(self.live.playing)


if __name__ == "__main__":
    unittest.main()
