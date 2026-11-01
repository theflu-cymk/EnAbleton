import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

pkg = ModuleType("bass_test_package")
pkg.__path__ = [str(Path(__import__("enableton").__file__).parent)]
sys.modules["bass_test_package"] = pkg
Mixin = importlib.import_module("bass_test_package.sound_design_support").SoundDesignSupportMixin


class Param:
    name = "Drive"
    min = 0
    max = 1
    is_quantized = False
    is_enabled = True
    automation_state = 0
    value_items = ()

    def __init__(self, name="Drive", snap=False):
        self.name = name
        self.raw = 0.5
        self.snap = snap

    @property
    def value(self):
        return self.raw

    @value.setter
    def value(self, value):
        self.raw = round(value) if self.snap else value

    def str_for_value(self, value):
        return str(round(value * 100, 2)) + "%"


class ParameterTests(unittest.TestCase):
    def test_master_inspection_nested_and_read_only(self):
        parameter = Param("Threshold")
        gain = Param("Chain Gain")
        limiter = SimpleNamespace(
            name="Limiter", class_name="Limiter", parameters=[parameter], can_have_chains=False
        )
        chain = SimpleNamespace(
            name="Mastering",
            mute=False,
            solo=False,
            mixer_device=SimpleNamespace(volume=gain),
            devices=[limiter],
        )
        rack = SimpleNamespace(
            name="Rack",
            class_name="AudioEffectGroupDevice",
            parameters=[],
            can_have_chains=True,
            chains=[chain],
        )
        bridge = Mixin()
        bridge._song = SimpleNamespace(
            master_track=SimpleNamespace(
                name="Main", mixer_device=SimpleNamespace(volume=gain), devices=[rack]
            )
        )
        result = bridge._inspect_master_chain({})
        nested = result["devices"][0]["chains"][0]["devices"][0]
        self.assertEqual(nested["path"], [0, 0, 0])
        self.assertEqual(nested["parameters"][0]["display_value"], "50.0%")
        self.assertTrue(result["read_only"])
        self.assertEqual(parameter.value, 0.5)
        self.assertEqual(gain.value, 0.5)

    def setUp(self):
        self.p = Param()
        self.q = Param("Output")
        self.undo = []
        self.bridge = Mixin()
        device = SimpleNamespace(
            name="808 Shaper", class_name="Saturator", parameters=[self.p, self.q]
        )
        self.bridge._song = SimpleNamespace(
            tracks=[SimpleNamespace(name="SUB", devices=[device])],
            begin_undo_step=lambda: self.undo.append("begin"),
            end_undo_step=lambda: self.undo.append("end"),
        )
        self.args = dict(
            track_index=0,
            device_index=0,
            expected_track_name="SUB",
            expected_device_name="808 Shaper",
        )

    def test_success_grouped_and_displayed(self):
        result = self.bridge._set_sound_design_parameters(
            dict(self.args, parameters={"Drive": 0.6, "Output": 0.7})
        )
        self.assertTrue(result["verified"])
        self.assertEqual(self.undo, ["begin", "end"])
        self.assertEqual(result["parameters"][0]["display_value"], "60.0%")

    def test_invalid_batch_has_no_partial_write(self):
        with self.assertRaises(ValueError):
            self.bridge._set_sound_design_parameters(
                dict(self.args, parameters={"Drive": 0.6, "Output": 2})
            )
        self.assertEqual(self.p.value, 0.5)
        self.assertEqual(self.undo, [])

    def test_snapping_restores_previous_batch(self):
        self.q.snap = True
        self.q.raw = 1
        with self.assertRaisesRegex(RuntimeError, "restored"):
            self.bridge._set_sound_design_parameters(
                dict(self.args, parameters={"Drive": 0.6, "Output": 0.7})
            )
        self.assertEqual(self.p.value, 0.5)
        self.assertEqual(self.q.value, 1)
        self.assertEqual(self.undo, ["begin", "end"])

    def test_automation_preserved(self):
        self.p.automation_state = 1
        with self.assertRaisesRegex(ValueError, "automation"):
            self.bridge._set_sound_design_parameters(dict(self.args, parameters={"Drive": 0.6}))
        self.assertEqual(self.undo, [])

    def test_stale_device_rejected(self):
        with self.assertRaises(ValueError):
            self.bridge._set_sound_design_parameters(
                dict(self.args, expected_device_name="Operator", parameters={"Drive": 0.6})
            )

    def test_ambiguous_parameter_rejected(self):
        self.q.name = "Drive"
        with self.assertRaises(ValueError):
            self.bridge._set_sound_design_parameters(dict(self.args, parameters={"Drive": 0.6}))

    def test_disabled_control_undo_closes(self):
        self.q.is_enabled = False
        with self.assertRaises(RuntimeError):
            self.bridge._set_sound_design_parameters(
                dict(self.args, parameters={"Drive": 0.6, "Output": 0.7})
            )
        self.assertEqual(self.p.value, 0.5)
        self.assertEqual(self.undo, ["begin", "end"])

    def test_inspection_is_nonmutating(self):
        result = self.bridge._get_sound_design_parameters(self.args)
        self.assertEqual(result["parameters"][0]["min"], 0)
        self.assertEqual(self.undo, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
