import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace as NS
import unittest
from test_parameters import Param

pkg = ModuleType("access_test_pkg")
pkg.__path__ = [str(Path(__import__("enableton").__file__).parent)]
sys.modules[pkg.__name__] = pkg
Sound = importlib.import_module("access_test_pkg.sound_design_support").SoundDesignSupportMixin
Access = importlib.import_module("access_test_pkg.access_support").AccessSupportMixin
access_module = importlib.import_module("access_test_pkg.access_support")


class Bridge(Access, Sound):
    pass


class AccessTests(unittest.TestCase):
    def test_audio_timing_complete_and_guarded(self):
        target = self.clip_fixture()
        self.clip.is_audio_clip = True
        self.clip.warp_markers = [
            NS(beat_time=0.0, sample_time=0.02),
            NS(beat_time=4.0, sample_time=1.72),
        ]
        for key, value in dict(
            file_path="kick.wav",
            warping=True,
            warp_mode=0,
            looping=True,
            start_marker=580.0,
            end_marker=644.0,
            pitch_coarse=0,
            pitch_fine=0,
            end_time=288.0,
        ).items():
            setattr(self.clip, key, value)
        result = self.bridge._get_audio_clip_timing(target)
        self.assertEqual(result["marker_count"], 2)
        self.assertEqual(result["warp_markers"][0]["sample_time"], 0.02)
        self.assertEqual(result["arrangement_start"], 224.0)
        self.assertTrue(result["read_only"])
        with self.assertRaises(ValueError):
            self.bridge._get_audio_clip_timing(dict(target, expected_start_time=225.0))

    def setUp(self):
        self.p = Param("Threshold")
        self.device = NS(
            name="Limiter", class_name="Limiter", parameters=[self.p], can_have_chains=False
        )
        self.chain = NS(
            name="Mastering",
            mute=False,
            solo=False,
            mixer_device=NS(volume=Param("Gain"), panning=Param("Pan"), sends=[Param("Send")]),
            devices=[self.device],
        )
        self.rack = NS(
            name="Rack",
            class_name="AudioEffectGroupDevice",
            parameters=[],
            can_have_chains=True,
            chains=[self.chain],
        )
        self.track = NS(
            name="Track",
            devices=[self.rack],
            mixer_device=self.chain.mixer_device,
            mute=False,
            solo=False,
            arm=False,
            color_index=0,
        )
        self.main = NS(name="Main", devices=[self.rack], mixer_device=self.chain.mixer_device)
        self.undo = []
        self.bridge = Bridge()
        self.bridge._song = NS(
            tracks=[self.track],
            return_tracks=[self.track],
            master_track=self.main,
            scenes=[],
            tempo=140,
            begin_undo_step=lambda: self.undo.append("begin"),
            end_undo_step=lambda: self.undo.append("end"),
        )
        self.target = dict(
            track_index=0,
            device_path=[0, 0, 0],
            expected_track_name="Track",
            expected_device_name="Limiter",
        )

    def test_nested_read_all_track_scopes(self):
        for kind in ("track", "return", "master"):
            target = dict(
                self.target,
                track_type=kind,
                expected_track_name="Main" if kind == "master" else "Track",
            )
            self.assertEqual(
                self.bridge._get_sound_design_parameters(target)["device_name"], "Limiter"
            )

    def test_nested_write_verified(self):
        self.assertTrue(
            self.bridge._set_sound_design_parameters(
                dict(self.target, parameters={"Threshold": 0.3})
            )["verified"]
        )
        self.assertEqual(self.p.value, 0.3)
        self.assertEqual(self.undo, ["begin", "end"])

    def test_nested_automated_write_refused(self):
        self.p.automation_state = 1
        with self.assertRaisesRegex(ValueError, "automation"):
            self.bridge._set_sound_design_parameters(
                dict(self.target, parameters={"Threshold": 0.3})
            )
        self.assertEqual(self.p.value, 0.5)
        self.assertEqual(self.undo, [])

    def test_bad_paths_and_names_refused(self):
        for path in ([], [0, 0], [-1], [0, False, 0], [0] * 19):
            with self.assertRaises((ValueError, AttributeError)):
                self.bridge._get_sound_design_parameters(dict(self.target, device_path=path))
        with self.assertRaisesRegex(ValueError, "no longer matches"):
            self.bridge._get_sound_design_parameters(dict(self.target, expected_device_name="EQ"))

    def test_tree_main_and_regular(self):
        self.assertEqual(self.bridge._inspect_master_chain({})["track_name"], "Main")
        self.assertEqual(
            self.bridge._inspect_master_chain({"track_type": "track", "track_index": 0})[
                "track_name"
            ],
            "Track",
        )

    def test_scalar_write_and_no_arbitrary_attribute(self):
        target = dict(object_type="track", track_index=0, expected_track_name="Track")
        self.assertTrue(
            self.bridge._write_access_object(dict(target, properties={"name": "Named"}))["verified"]
        )
        with self.assertRaisesRegex(ValueError, "not exposed"):
            self.bridge._write_access_object(
                dict(target, expected_track_name="Named", properties={"__class__": "bad"})
            )

    def test_scalar_preflight_no_partial_write(self):
        with self.assertRaises(ValueError):
            self.bridge._write_access_object(
                dict(
                    object_type="track",
                    track_index=0,
                    expected_track_name="Track",
                    properties={"name": "Changed", "color_index": 99},
                )
            )
        self.assertEqual(self.track.name, "Track")
        self.assertEqual(self.undo, [])

    def test_chain_mixer(self):
        target = dict(
            track_index=0,
            expected_track_name="Track",
            device_path=[0],
            expected_device_name="Rack",
            chain_index=0,
            expected_chain_name="Mastering",
        )
        result = self.bridge._set_access_mixer(
            dict(target, parameters={"volume": 0.7, "pan": 0.25, "send:0": 0.2})
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["parameters"]["volume"]["value"], 0.7)
        self.assertEqual(result["sends"][0]["value"], 0.2)

    def test_mixer_preflight_and_guards(self):
        target = dict(track_index=0, expected_track_name="Track")
        with self.assertRaises(ValueError):
            self.bridge._set_access_mixer(dict(target, parameters={"volume": 0.7, "pan": 9}))
        self.assertEqual(self.track.mixer_device.volume.value, 0.5)
        with self.assertRaises(ValueError):
            self.bridge._set_access_mixer(dict(track_index=0, parameters={"volume": 0.7}))

    def clip_fixture(self):
        self.note = NS(
            note_id=71,
            pitch=60,
            start_time=600.0,
            duration=1.0,
            velocity=90.0,
            mute=False,
            probability=1.0,
            velocity_deviation=0.0,
            release_velocity=64.0,
        )
        self.clip = NS(
            name="Offset clip",
            is_midi_clip=True,
            is_recording=False,
            loop_start=580.0,
            loop_end=644.0,
            start_time=224.0,
            get_all_notes_extended=lambda: [NS(**vars(self.note))],
        )

        original_spec = access_module._note_spec
        access_module._note_spec = lambda note: NS(**note)
        self.addCleanup(setattr, access_module, "_note_spec", original_spec)

        def all_notes():
            return [] if self.note is None else [NS(**vars(self.note))]

        def add(specs):
            self.assertEqual(len(specs), 1)
            self.note = NS(**vars(specs[0]), note_id=99)

        def remove(pitch, span, start, timespan):
            self.assertLessEqual(pitch, self.note.pitch)
            self.assertLess(self.note.pitch, pitch + span)
            self.assertLessEqual(start, self.note.start_time)
            self.assertLess(self.note.start_time, start + timespan)
            self.note = None

        self.clip.get_all_notes_extended = all_notes
        self.clip.add_new_notes = add
        self.clip.remove_notes_extended = remove
        self.track.arrangement_clips = [self.clip]
        return dict(
            track_index=0,
            clip_view="arrangement",
            clip_index=0,
            expected_track_name="Track",
            expected_clip_name="Offset clip",
            expected_start_time=224.0,
        )

    def test_full_range_notes_and_targeted_rewrite(self):
        target = self.clip_fixture()
        self.assertEqual(self.bridge._get_access_notes(target)["notes"][0]["start_time"], 600.0)
        result = self.bridge._modify_access_notes(
            dict(target, notes=[{"note_id": 71, "pitch": 62, "start_time": 600.5}])
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["modified_notes"], 1)
        self.assertEqual(result["note_ids"], [99])
        self.assertEqual(self.note.pitch, 62)
        self.assertEqual(self.note.start_time, 600.5)
        self.assertNotEqual(self.note.note_id, 71)
        self.assertEqual(self.clip.loop_start, 580.0)
        self.assertEqual(self.clip.start_time, 224.0)

    def test_ambiguous_duplicate_pitch_start_refused(self):
        target = self.clip_fixture()
        duplicate = NS(**dict(vars(self.note), note_id=72))
        self.clip.get_all_notes_extended = lambda: [self.note, duplicate]
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.bridge._modify_access_notes(dict(target, notes=[{"note_id": 71, "pitch": 62}]))
        self.assertEqual(self.note.pitch, 60)

    def test_note_guard_and_invalid_id(self):
        target = self.clip_fixture()
        with self.assertRaises(ValueError):
            self.bridge._get_access_notes(dict(target, expected_start_time=225.0))
        with self.assertRaises(ValueError):
            self.bridge._modify_access_notes(dict(target, notes=[{"note_id": 72, "pitch": 62}]))
        self.assertEqual(self.note.pitch, 60)


class NoteLifecycleTests(unittest.TestCase):
    """Insert and delete are verified by ID and refuse ambiguity before writing."""

    def setUp(self):
        self.original_spec = access_module._note_spec
        access_module._note_spec = lambda note: NS(**note)
        self.addCleanup(setattr, access_module, "_note_spec", self.original_spec)
        self.notes = [self.note(71, 60, 600.0, 1.0, 90), self.note(72, 64, 604.0, 0.5, 80)]
        self.undo = []

        def all_notes():
            return [NS(**vars(item)) for item in self.notes]

        def add(specs):
            for spec in specs:
                self.notes.append(
                    self.note(
                        200 + len(self.notes),
                        spec.pitch,
                        spec.start_time,
                        spec.duration,
                        spec.velocity,
                    )
                )

        def remove(pitch, span, start, timespan):
            self.notes = [
                item
                for item in self.notes
                if not (
                    pitch <= item.pitch < pitch + span
                    and start <= item.start_time < start + timespan
                )
            ]

        self.clip = NS(
            name="Notes",
            is_midi_clip=True,
            is_recording=False,
            start_time=224.0,
            loop_start=580.0,
            loop_end=644.0,
            get_all_notes_extended=all_notes,
            add_new_notes=add,
            remove_notes_extended=remove,
        )
        self.bridge = Bridge()
        self.bridge._song = NS(
            tracks=[NS(name="Track", arrangement_clips=[self.clip], clip_slots=[])],
            return_tracks=[],
            master_track=NS(name="Main"),
            scenes=[],
            begin_undo_step=lambda: self.undo.append("begin"),
            end_undo_step=lambda: self.undo.append("end"),
        )
        self.target = dict(
            track_index=0,
            clip_view="arrangement",
            clip_index=0,
            expected_track_name="Track",
            expected_clip_name="Notes",
            expected_start_time=224.0,
        )

    @staticmethod
    def note(ident, pitch, start, duration, velocity, mute=False):
        return NS(
            note_id=ident,
            pitch=pitch,
            start_time=start,
            duration=duration,
            velocity=float(velocity),
            mute=mute,
            probability=1.0,
            velocity_deviation=0.0,
            release_velocity=64.0,
        )

    def test_insert_is_verified_and_undo_bracketed(self):
        result = self.bridge._insert_access_notes(
            dict(
                self.target,
                notes=[{"pitch": 67, "start_time": 600.0, "duration": 2.0, "velocity": 100}],
            )
        )
        self.assertTrue(result["verified"])
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(len(self.notes), 3)
        self.assertEqual(self.undo, ["begin", "end"])

    def test_insert_refuses_missing_api_and_bad_notes(self):
        self.clip.add_new_notes = None
        with self.assertRaisesRegex(RuntimeError, "cannot insert"):
            self.bridge._insert_access_notes(
                dict(self.target, notes=[{"pitch": 60, "start_time": 0.0, "duration": 1.0}])
            )
        self.clip.add_new_notes = lambda specs: None
        for note in (
            {"pitch": 200, "start_time": 0.0, "duration": 1.0},
            {"pitch": 60, "start_time": 0.0},
            {"pitch": True, "start_time": 0.0, "duration": 1.0},
            {"pitch": 60, "start_time": 0.0, "duration": 1.0, "colour": 1},
        ):
            with self.subTest(note=note), self.assertRaises(ValueError):
                self.bridge._insert_access_notes(dict(self.target, notes=[note]))
        self.assertEqual(len(self.notes), 2)
        self.assertEqual(self.undo, [])

    def test_delete_removes_only_requested_ids(self):
        result = self.bridge._delete_access_notes(dict(self.target, notes=[{"note_id": 71}]))
        self.assertTrue(result["verified"])
        self.assertEqual([item.note_id for item in self.notes], [72])
        self.assertEqual(self.undo, ["begin", "end"])

    def test_delete_refuses_ambiguous_duplicates(self):
        self.notes.append(self.note(73, 60, 600.0, 0.5, 70))
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            self.bridge._delete_access_notes(dict(self.target, notes=[{"note_id": 71}]))
        self.assertEqual(len(self.notes), 3)
        self.assertEqual(self.undo, [])

    def test_delete_refuses_unknown_and_repeated_ids(self):
        for notes in ([{"note_id": 99}], [{"note_id": 71}, 71]):
            with self.subTest(notes=notes), self.assertRaises(ValueError):
                self.bridge._delete_access_notes(dict(self.target, notes=notes))
        self.assertEqual(self.undo, [])


if __name__ == "__main__":
    unittest.main()


class WarpCommandTests(unittest.TestCase):
    """Warp writes are audio-only, guarded, undo-bracketed and verified."""

    def setUp(self):
        self.undo = []

        self.clip = NS(
            name="Take",
            is_midi_clip=False,
            is_audio_clip=True,
            is_recording=False,
            warping=False,
            warp_mode=0,
            gain=0.5,
            pitch_coarse=0,
            pitch_fine=0.0,
            start_time=0.0,
        )

        self.bridge = Bridge()

        self.bridge._song = NS(
            tracks=[
                NS(
                    name="Vox",
                    clip_slots=[
                        NS(has_clip=True, clip=self.clip),
                        NS(has_clip=False, clip=None),
                    ],
                    arrangement_clips=[],
                )
            ],
            return_tracks=[],
            master_track=NS(name="Main"),
            scenes=[],
            begin_undo_step=lambda: self.undo.append("begin"),
            end_undo_step=lambda: self.undo.append("end"),
        )

        self.target = dict(
            track_index=0,
            clip_view="session",
            clip_index=0,
            expected_track_name="Vox",
            expected_clip_name="Take",
        )

    def test_warp_write_is_verified_and_undo_bracketed(self):
        result = self.bridge._set_access_warp(
            dict(self.target, properties={"warping": True, "warp_mode": 2})
        )

        self.assertTrue(result["verified"])

        self.assertEqual(result["applied"], {"warping": True, "warp_mode": 2})

        self.assertTrue(self.clip.warping)

        self.assertEqual(self.clip.warp_mode, 2)

        self.assertEqual(self.undo, ["begin", "end"])

    def test_clip_read_exposes_warp_mode(self):
        """Object reads must return warp_mode so callers can verify Warp writes."""

        self.clip.warping = True

        self.clip.warp_mode = 4

        read = self.bridge._read_access_object(dict(self.target, object_type="clip"))

        self.assertEqual(read["properties"]["warp_mode"], 4)

        self.assertNotIn("warp_mode", read["unavailable"])

    def test_warp_refuses_midi_and_bad_values(self):
        self.clip.is_audio_clip = False

        with self.assertRaisesRegex(ValueError, "[Aa]udio"):
            self.bridge._set_access_warp(dict(self.target, properties={"warping": True}))

        self.clip.is_audio_clip = True

        for properties in (
            {"warp_mode": 9},
            {"warp_mode": True},
            {"gain": 2},
            {"tempo": 120},
            {},
        ):
            with self.subTest(properties=properties), self.assertRaises(ValueError):
                self.bridge._set_access_warp(dict(self.target, properties=properties))

        self.assertEqual(self.undo, [])

    def test_warp_guard_and_recording_refused(self):
        with self.assertRaises(ValueError):
            self.bridge._set_access_warp(dict(self.target, expected_clip_name="Other"))

        self.clip.is_recording = True

        with self.assertRaisesRegex(ValueError, "recording"):
            self.bridge._set_access_warp(dict(self.target, properties={"warping": True}))

        self.assertEqual(self.undo, [])

    def test_warp_readback_mismatch_raises_and_brackets_undo(self):
        class Frozen:
            name = "Take"

            is_midi_clip = False

            is_audio_clip = True

            is_recording = False

            warping = False

            gain = 0.5

            pitch_coarse = 0

            pitch_fine = 0.0

            start_time = 0.0

            @property
            def warp_mode(self):
                return 0

            @warp_mode.setter
            def warp_mode(self, value):
                pass

        self.bridge._song.tracks[0].clip_slots[0] = NS(has_clip=True, clip=Frozen())

        with self.assertRaisesRegex(RuntimeError, "readback"):
            self.bridge._set_access_warp(dict(self.target, properties={"warp_mode": 2}))

        self.assertEqual(self.undo, ["begin", "end"])
