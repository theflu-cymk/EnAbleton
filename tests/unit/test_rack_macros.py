"""Fake-Live tests for rack inspect and blend-macro mapping."""

import unittest

from enableton.device_support import DeviceSupportMixin


class Param:
    def __init__(self, name):
        self.name = name


class Device:
    def __init__(self, name, parameters=(), class_name=""):
        self.name = name
        self.parameters = list(parameters)
        self.class_name = class_name


class Chain:
    def __init__(self, name, devices):
        self.name = name
        self.devices = list(devices)


class Macro:
    def __init__(self, name):
        self.name = name


class Rack:
    def __init__(self, name="Rack", chains=(), visible=1, mapper=True, renamer=True):
        self.name = name
        self.can_have_chains = True
        self.chains = list(chains)
        self.visible_macro_count = visible
        self.parameters = [Macro("Device On")] + [Macro("Macro %d" % (i + 1)) for i in range(8)]
        self.macros_mapped = []
        self.mapped = []
        self.added = 0
        self.renames = []
        if mapper:
            self.macro_map = self._map
        if renamer:
            self.rename_macro = self._rename

    def add_macro(self):
        self.added += 1
        self.visible_macro_count += 1

    def _map(self, macro_index, parameter):
        self.mapped.append((macro_index, parameter))
        self.macros_mapped.append(parameter.name)

    def _rename(self, macro_index, name):
        self.renames.append((macro_index, name))
        self.parameters[macro_index + 1].name = name


class Song:
    def __init__(self, device):
        self.tracks = [type("Track", (), {"devices": [device]})()]
        self.undo = 0

    def begin_undo_step(self):
        self.undo += 1

    def end_undo_step(self):
        self.undo -= 1


class Host(DeviceSupportMixin):
    def __init__(self, device):
        self._song = Song(device)


class RackMacroTests(unittest.TestCase):
    def rack(self):
        wet = Device("Reverb", [Param("Dry/Wet")])
        plain = Device("Utility", [Param("Gain")])
        mix = Device("Delay", [Param("mix")])
        return Rack("Space", [Chain("A", [wet, plain]), Chain("B", [mix])])

    def test_inspect_reports_blend_names_and_missing_mapper(self):
        rack = self.rack()
        del rack.macro_map
        report = Host(rack)._inspect_rack({"track_index": 0, "device_index": 0})
        self.assertFalse(report["has_macro_map"])
        self.assertEqual(
            [row["blend_parameter"] for row in report["devices"]],
            ["Dry/Wet", None, "mix"],
        )
        self.assertEqual(report["chains"], 2)

    def test_empty_chains_are_not_an_error(self):
        rack = Rack("Empty", [])
        report = Host(rack)._map_rack_blend_macro(
            {"track_index": 0, "device_index": 0, "expected_device_name": "Empty"}
        )
        self.assertEqual(report["mapped"], [])
        self.assertEqual(report["skipped"], [])
        self.assertEqual(report["macro_name"], "Blend")
        self.assertEqual(rack.renames, [(0, "Blend")])

    def test_map_requires_identity_and_macro_map(self):
        host = Host(self.rack())
        with self.assertRaisesRegex(ValueError, "expected_device_name"):
            host._map_rack_blend_macro({"track_index": 0, "device_index": 0})
        rack = self.rack()
        del rack.macro_map
        with self.assertRaisesRegex(RuntimeError, "macro_map"):
            Host(rack)._map_rack_blend_macro(
                {"track_index": 0, "device_index": 0, "expected_device_name": "Space"}
            )

    def test_map_uses_exact_blend_name_and_skips_the_rest(self):
        rack = self.rack()
        host = Host(rack)
        report = host._map_rack_blend_macro(
            {
                "track_index": 0,
                "device_index": 0,
                "expected_device_name": "Space",
                "macro_name": "Blend",
            }
        )
        self.assertEqual([row["parameter"] for row in report["mapped"]], ["Dry/Wet", "mix"])
        self.assertEqual(report["macros_mapped"], ["Dry/Wet", "mix"])
        self.assertEqual(report["skipped"][0]["device_name"], "Utility")
        self.assertEqual(report["skipped"][0]["reason"], "no blend parameter")
        self.assertEqual(host._song.undo, 0)
        self.assertFalse(report["playback_started"])

    def test_map_exposes_one_macro_when_none_are_visible(self):
        rack = Rack("Space", [Chain("A", [Device("Reverb", [Param("Dry/Wet")])])], visible=0)
        host = Host(rack)
        report = host._map_rack_blend_macro(
            {"track_index": 0, "device_index": 0, "expected_device_name": "Space"}
        )
        self.assertEqual(rack.added, 1)
        self.assertEqual(report["mapped"][0]["parameter"], "Dry/Wet")
        self.assertEqual(host._song.undo, 0)

    def test_map_stops_when_add_macro_does_not_raise_the_count(self):
        rack = Rack("Space", [], visible=0)

        def stuck():
            rack.added += 1

        rack.add_macro = stuck
        with self.assertRaisesRegex(RuntimeError, "Could not expose macro"):
            Host(rack)._map_rack_blend_macro(
                {"track_index": 0, "device_index": 0, "expected_device_name": "Space"}
            )
        self.assertEqual(rack.added, 8)

    def test_rename_falls_back_to_the_macro_parameter(self):
        rack = Rack("Space", [], renamer=False)
        Host(rack)._map_rack_blend_macro(
            {
                "track_index": 0,
                "device_index": 0,
                "expected_device_name": "Space",
                "macro_index": 2,
                "macro_name": "Glue",
            }
        )
        self.assertEqual(rack.parameters[3].name, "Glue")

    def test_unreadable_macros_mapped_still_returns_the_mapping(self):
        rack = self.rack()

        def remember(macro_index, parameter):
            rack.mapped.append((macro_index, parameter))

        rack.macro_map = remember

        class Exploding:
            def __iter__(self):
                raise RuntimeError("live object")

        rack.macros_mapped = Exploding()
        report = Host(rack)._map_rack_blend_macro(
            {"track_index": 0, "device_index": 0, "expected_device_name": "Space"}
        )
        self.assertEqual([row["parameter"] for row in report["mapped"]], ["Dry/Wet", "mix"])
        self.assertEqual(report["macros_mapped"], [])
        self.assertEqual(report["skipped"][0]["reason"], "no blend parameter")

    def test_inspect_omits_macros_that_are_not_json(self):
        rack = self.rack()
        rack.macros_mapped = [object()]
        report = Host(rack)._inspect_rack({"track_index": 0, "device_index": 0})
        self.assertEqual(report["macros_mapped"], [])
        self.assertEqual(
            [row["blend_parameter"] for row in report["devices"]],
            ["Dry/Wet", None, "mix"],
        )

    def test_exact_blend_name_wins_over_a_different_case(self):
        device = Device("Delay", [Param("Mix"), Param("mix")])
        _, name = Host(Rack("R"))._blend_parameter(device)
        self.assertEqual(name, "Mix")
