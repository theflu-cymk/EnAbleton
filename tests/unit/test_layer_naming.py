import unittest

from enableton import layer_naming


class RoleInferenceTests(unittest.TestCase):
    def test_known_layer_names(self):
        cases = {
            "4-2 Drums": "drums",
            "5-3 Bass": "bass",
            "6-4 Guitar": "guitar",
            "7-5 Keyboard": "keys",
            "8-6 Percussion": "percussion",
            "9-7 Strings": "strings",
            "10-8 Synth": "synth",
            "11-9 Other": "other",
            "12-10 Woodwinds": "woodwinds",
            "13-0 Lead Vocals": "lead_vox",
            "14-1 Backing Vocals": "bg_vox",
        }
        for name, role in cases.items():
            self.assertEqual(layer_naming.infer_role(name), role, name)

    def test_colours_are_unique_and_valid(self):
        values = list(layer_naming.ROLE_COLORS.values())
        self.assertEqual(len(values), len(set(values)))
        self.assertTrue(all(0 <= value <= 69 for value in values))

    def test_names_are_short_and_ordered(self):
        self.assertEqual(layer_naming.layer_name("drums", 1), "01 Drums")
        self.assertEqual(layer_naming.layer_name("lead_vox", 9), "09 Lead Vox")
        self.assertEqual(layer_naming.layer_name("bg_vox", 10), "10 BG Vox")


class PlanTests(unittest.TestCase):
    def test_plan_skips_groups_and_midi(self):
        tracks = [
            {"id": "track:0", "name": "4-2 Drums", "type": "audio", "clips": [{"id": "c0"}]},
            {"id": "track:1", "name": "5-3 Bass", "type": "audio", "clips": [{"id": "c1"}]},
            {"id": "track:2", "name": "Group", "type": "group", "is_group": True},
            {"id": "track:3", "name": "Instrument", "type": "midi"},
        ]
        rows = layer_naming.plan(tracks)
        self.assertEqual([row["name"] for row in rows], ["01 Drums", "02 Bass"])
        self.assertEqual(rows[0]["color_index"], layer_naming.ROLE_COLORS["drums"])


class LayerProcessTests(unittest.TestCase):
    def test_convention_step_renames_and_colours(self):
        from enableton import song_processes

        state = {
            "tracks": [
                {
                    "id": "track:0",
                    "name": "4-2 Drums",
                    "type": "audio",
                    "color_index": 3,
                    "clips": [{"id": "c0"}],
                }
            ]
        }
        result = song_processes.REGISTRY["apply_layer_naming"](state, {}, {})
        patch = result.changes[0]["patch"]
        self.assertEqual(patch["name"], "01 Drums")
        self.assertEqual(patch["color_index"], layer_naming.ROLE_COLORS["drums"])


if __name__ == "__main__":
    unittest.main()
