"""Unit tests for the EXT.12 Live-side commands using fake Live objects."""

import unittest

from enableton import device_support


class Param:
    def __init__(self, name, low, high, display):
        self.name = name
        self.min = low
        self.max = high
        self.value = low
        self._display = display

    def str_for_value(self, value):
        return self._display(value)


def hz_param(name, low=10.0, high=22000.0):
    return Param(name, 0.0, 1.0, lambda value: "%.2f Hz" % (low + value * (high - low)))


def db_param(name):
    return Param(name, 0.0, 1.0, lambda value: "%.2f dB" % (-30.0 + value * 60.0))


def q_param(name):
    return Param(name, 0.0, 1.0, lambda value: "%.3f" % (0.1 + value * 17.9))


class Device:
    def __init__(self, name, parameters, class_name=""):
        self.name = name
        self.parameters = parameters
        self.class_name = class_name


class Track:
    def __init__(self, devices):
        self.devices = devices


class Song:
    def __init__(self, tracks=()):
        self.tracks = list(tracks)

    def begin_undo_step(self):
        pass

    def end_undo_step(self):
        pass


class Dummy(device_support.DeviceSupportMixin):
    def __init__(self, song):
        self._song = song


def eq_parameters():
    return [
        hz_param("1 Frequency A"),
        db_param("1 Gain A"),
        q_param("1 Resonance A"),
        Param("1 Filter On A", 0.0, 1.0, lambda value: "On" if value else "Off"),
        hz_param("2 Frequency A"),
        hz_param("1 Frequency B"),
    ]


def eq_device(name="EQ Eight"):
    return Device(name, eq_parameters(), class_name="Eq8")


class DisplayTests(unittest.TestCase):
    def test_reaches_displayed_hertz(self):
        param = hz_param("1 Frequency A")
        value = device_support._value_for(param, 1000.0)
        self.assertAlmostEqual(float(param.str_for_value(value).split()[0]), 1000.0, places=1)

    def test_parameter_lookup_requires_band_kind_and_mode(self):
        device = eq_device()
        self.assertIs(
            device_support.eq_parameter(device, 1, "Frequency", "B"), device.parameters[5]
        )
        with self.assertRaises(ValueError):
            device_support.eq_parameter(device, 3, "Frequency", "A")
        with self.assertRaises(ValueError):
            device_support.eq_parameter(device, 1, "Frequency", "C")


class EqBandTests(unittest.TestCase):
    def test_writes_and_reads_back(self):
        device = eq_device()
        dummy = Dummy(Song([Track([device])]))
        report = dummy._set_eq_bands(
            {
                "track_index": 0,
                "device_index": 0,
                "mode": "A",
                "bands": [{"band": 1, "filter_on": True, "frequency_hz": 1000, "gain_db": -3.0}],
            }
        )
        self.assertTrue(report["verified"])
        self.assertEqual(report["device_class"], "Eq8")
        self.assertEqual(report["bands"][0]["written"]["frequency_hz"], 1000.0)
        self.assertAlmostEqual(
            float(device.parameters[0].str_for_value(device.parameters[0].value).split()[0]),
            1000.0,
            places=1,
        )
        self.assertAlmostEqual(
            float(device.parameters[1].str_for_value(device.parameters[1].value).split()[0]),
            -3.0,
            places=1,
        )

    def test_accepts_eq_eight_loaded_as_a_named_preset(self):
        device = eq_device(name="Remove Mud")
        dummy = Dummy(Song([Track([device])]))
        report = dummy._set_eq_bands(
            {"track_index": 0, "device_index": 0, "bands": [{"band": 1, "gain_db": -4.0}]}
        )
        self.assertEqual(report["device"], "Remove Mud")
        self.assertEqual(report["device_class"], "Eq8")

    def test_refuses_non_eq_and_band_without_fields(self):
        dummy = Dummy(Song([Track([Device("Compressor", [], class_name="Compressor2")])]))
        with self.assertRaises(ValueError):
            dummy._set_eq_bands({"track_index": 0, "device_index": 0, "bands": [{"band": 1}]})
        eq_dummy = Dummy(Song([Track([eq_device()])]))
        with self.assertRaises(ValueError):
            eq_dummy._set_eq_bands({"track_index": 0, "device_index": 0, "bands": [{"band": 2}]})


class ChainTests(unittest.TestCase):
    def test_insert_chain_requires_capability(self):
        rack = Device("Audio Effect Rack", [], class_name="AudioEffectGroupDevice")
        rack.can_have_chains = True
        rack.chains = [object()]
        dummy = Dummy(Song([Track([rack])]))
        with self.assertRaises(RuntimeError):
            dummy._insert_chain({"track_index": 0, "device_index": 0})

    def test_insert_then_refuse_last_delete(self):
        class Chain:
            def __init__(self):
                self.name = "Chain 1"
                self.devices = []

        class Rack(Device):
            def __init__(self):
                super().__init__("Audio Effect Rack", [], class_name="AudioEffectGroupDevice")
                self.can_have_chains = True
                self.chains = [Chain()]

            def insert_chain(self, position):
                self.chains.insert(position, Chain())

            def delete_chain(self, position):
                self.chains.pop(position)

        rack = Rack()
        dummy = Dummy(Song([Track([rack])]))
        report = dummy._insert_chain({"track_index": 0, "device_index": 0})
        self.assertEqual(report["chains"], 2)
        report = dummy._delete_chain(
            {
                "track_index": 0,
                "device_index": 0,
                "chain_index": 1,
                "expected_chain_name": "Chain 1",
            }
        )
        self.assertEqual(report["chains"], 1)
        with self.assertRaises(ValueError):
            dummy._delete_chain({"track_index": 0, "device_index": 0, "chain_index": 0})
        with self.assertRaises(ValueError):
            dummy._delete_chain(
                {
                    "track_index": 0,
                    "device_index": 0,
                    "chain_index": 0,
                    "expected_chain_name": "Nope",
                }
            )


class CueTests(unittest.TestCase):
    def test_deletes_cue_and_never_reads_the_dead_handle(self):
        class Cue:
            def __init__(self, name, time):
                self.name = name
                self._time = time
                self.dead = False

            @property
            def time(self):
                if self.dead:
                    raise TypeError("None.None(CuePoint) did not match C++ signature")
                return self._time

        class CueSong(Song):
            def __init__(self):
                super().__init__()
                self.cue_points = [Cue("drop", 4.0), Cue("outro", 32.0)]
                self.current_song_time = 4.0

            def set_or_delete_cue(self):
                keep = []
                for cue in self.cue_points:
                    if abs(cue.time - self.current_song_time) < 1e-3:
                        cue.dead = True
                    else:
                        keep.append(cue)
                self.cue_points = keep

        song = CueSong()
        report = Dummy(song)._delete_cue_point({"time": 4.0})
        self.assertEqual(report["deleted"], "drop")
        self.assertEqual(report["time"], 4.0)
        self.assertEqual(report["remaining"], 1)
        self.assertEqual([cue.time for cue in song.cue_points], [32.0])

    def test_refuses_when_playhead_is_elsewhere(self):
        class CueSong(Song):
            def __init__(self):
                super().__init__()
                self.cue_points = [type("C", (), {"name": "drop", "time": 4.0})()]
                self.current_song_time = 0.0

        with self.assertRaises(ValueError):
            Dummy(CueSong())._delete_cue_point({"time": 4.0})

    def test_refuses_unknown_time(self):
        class CueSong(Song):
            cue_points = []
            current_song_time = 0.0

        with self.assertRaises(ValueError):
            Dummy(CueSong())._delete_cue_point({"time": 12.0})


class SceneTests(unittest.TestCase):
    def test_lists_scenes_with_clip_counts(self):
        class Slot:
            def __init__(self, has_clip):
                self.has_clip = has_clip

        class Scene:
            def __init__(self, name, tempo):
                self.name = name
                self.color_index = 3
                self.tempo = tempo

        class SceneSong(Song):
            def __init__(self):
                super().__init__()
                self.scenes = [Scene("Intro", 120.0), Scene("Drop", 128.0)]
                self.tracks = [
                    type("T", (), {"clip_slots": [Slot(True), Slot(False)]})(),
                    type("T", (), {"clip_slots": [Slot(True), Slot(True)]})(),
                ]

        report = Dummy(SceneSong())._get_scenes({})
        self.assertEqual(report["count"], 2)
        self.assertEqual(report["scenes"][0]["clips"], 2)
        self.assertEqual(report["scenes"][1]["clips"], 1)
        self.assertEqual(report["scenes"][1]["tempo"], 128.0)


if __name__ == "__main__":
    unittest.main()
