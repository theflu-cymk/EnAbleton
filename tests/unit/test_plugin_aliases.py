"""Serum alias resolution. Values are not converted."""

import unittest

from enableton.plugin_aliases import (
    apply_plugin_parameter,
    matching_profiles,
    resolve_live_alias,
    resolve_name,
)


class ResolveTests(unittest.TestCase):
    def test_exact_live_name_wins_over_an_alias(self):
        resolved = resolve_name("Serum", "filter cutoff", ["filter cutoff", "Fil Cutoff"])
        self.assertEqual(resolved["resolved"], "filter cutoff")
        self.assertEqual(resolved["source"], "exact")

    def test_alias_requires_the_configured_control(self):
        resolved = resolve_name("Xfer Serum", "Filter Cutoff", ["Fil Cutoff", "Fil Reso"])
        self.assertEqual(resolved["resolved"], "Fil Cutoff")
        self.assertEqual(resolved["source"], "alias")
        with self.assertRaisesRegex(ValueError, "Configure"):
            resolve_name("Serum", "filter cutoff", ["Macro 1"])

    def test_unknown_device_keeps_an_exact_name_and_refuses_a_guess(self):
        resolved = resolve_name("Operator", "Frequency", ["Frequency"])
        self.assertEqual(resolved["source"], "exact")
        with self.assertRaisesRegex(ValueError, "get_sound_design_parameters"):
            resolve_name("Operator", "filter cutoff", ["Frequency"])

    def test_two_profiles_refuse(self):
        profiles = {
            "Serum": {"match": "serum", "aliases": {}, "categories": {}},
            "Serum FX": {"match": "serum", "aliases": {}, "categories": {}},
        }
        with self.assertRaisesRegex(ValueError, "more than one"):
            matching_profiles("Serum", profiles)


class ApplyTests(unittest.TestCase):
    def test_set_dispatches_the_resolved_native_value(self):
        calls = []

        def dispatch(command, params):
            calls.append((command, params))
            if command == "get_sound_design_parameters":
                return {
                    "device_name": "Serum",
                    "track_name": "Lead",
                    "parameters": [{"name": "Fil Cutoff"}],
                }
            self.assertEqual(params["parameters"], {"Fil Cutoff": 0.25})
            return {"verified": True, "parameters": [{"name": "Fil Cutoff", "value": 0.25}]}

        report = apply_plugin_parameter(dispatch, 1, 0, "filter cutoff", 0.25, "Lead", "Serum")
        self.assertEqual(report["alias"]["resolved"], "Fil Cutoff")
        self.assertEqual(report["native_value"], 0.25)
        self.assertEqual(calls[1][0], "set_sound_design_parameters")

    def test_set_does_not_invent_a_normalized_conversion(self):
        def dispatch(command, params):
            if command == "get_sound_design_parameters":
                return {"device_name": "Serum", "parameters": [{"name": "Fil Cutoff"}]}
            raise AssertionError(command)

        with self.assertRaisesRegex(ValueError, "native number"):
            apply_plugin_parameter(dispatch, 0, 0, "filter cutoff", True, "Lead", "Serum")

    def test_resolve_reads_live_names_and_does_not_write(self):
        calls = []

        def dispatch(command, params):
            calls.append(command)
            return {"device_name": "Serum", "parameters": [{"name": "Master Vol"}]}

        report = resolve_live_alias(dispatch, 0, 2, "master volume")
        self.assertEqual(report["resolution"]["resolved"], "Master Vol")
        self.assertFalse(report["live_changes"])
        self.assertEqual(calls, ["get_sound_design_parameters"])
