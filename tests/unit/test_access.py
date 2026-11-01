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

        def apply(objects):
            self.assertEqual(len(objects), 1)
            self.note = NS(**vars(objects[0]))

        self.clip.apply_note_modifications = apply
        self.track.arrangement_clips = [self.clip]
        return dict(
            track_index=0,
            clip_view="arrangement",
            clip_index=0,
            expected_track_name="Track",
            expected_clip_name="Offset clip",
            expected_start_time=224.0,
        )

    def test_full_range_notes_and_id_preservation(self):
        target = self.clip_fixture()
        self.assertEqual(self.bridge._get_access_notes(target)["notes"][0]["start_time"], 600.0)
        result = self.bridge._modify_access_notes(
            dict(target, notes=[{"note_id": 71, "pitch": 62, "start_time": 600.5}])
        )
        self.assertTrue(result["verified"])
        self.assertEqual(self.note.note_id, 71)
        self.assertEqual(self.note.pitch, 62)
        self.assertEqual(self.clip.loop_start, 580.0)
        self.assertEqual(self.clip.start_time, 224.0)

    def test_note_guard_and_invalid_id(self):
        target = self.clip_fixture()
        with self.assertRaises(ValueError):
            self.bridge._get_access_notes(dict(target, expected_start_time=225.0))
        with self.assertRaises(ValueError):
            self.bridge._modify_access_notes(dict(target, notes=[{"note_id": 72, "pitch": 62}]))
        self.assertEqual(self.note.pitch, 60)


if __name__ == "__main__":
    unittest.main()
