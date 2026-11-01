import unittest
from enableton.bass_patterns import phrase, inspect_sub_notes
from enableton.tutorial_layering import gun_blueprint
from test_bass import Registry
from enableton.bass_tools import register


class TutorialTests(unittest.TestCase):
    def test_triplets_stay_on_grid_and_monophonic(self):
        for role in ["call", "response", "sub"]:
            notes = phrase("tearout_triplet", 8, 29, role, 42)["notes"]
            self.assertTrue(
                all(abs(n["start_time"] * 3 - round(n["start_time"] * 3)) < 1e-8 for n in notes)
            )
            self.assertFalse(inspect_sub_notes(notes)["overlaps"])

    def test_call_response_are_complementary(self):
        call = phrase("tearout_triplet", role="call")["notes"]
        response = phrase("tearout_triplet", role="response")["notes"]
        self.assertFalse(inspect_sub_notes(call + response)["overlaps"])

    def test_four_layers_are_synchronized(self):
        layers = gun_blueprint()["original_example_material"]["layers"]
        self.assertEqual([l["role"] for l in layers], ["sub", "transient", "body", "noise"])
        expected = [n["start_time"] for n in layers[0]["notes"]]
        for layer in layers:
            self.assertEqual([n["start_time"] for n in layer["notes"]], expected)
        self.assertLess(layers[1]["notes"][0]["duration"], layers[0]["notes"][0]["duration"])

    def test_blueprint_is_nonmutating_and_provenance_explicit(self):
        registry = Registry()

        def send(*args):
            raise AssertionError("Must not touch Live")

        register(registry, send)
        result = registry.tools["tearout_gun_blueprint"]()
        self.assertIn("not a transcription", result["original_example_material"]["note"])
        self.assertIn("auto-generated", result["source"]["evidence"])
        self.assertIn("Read-only", result["execution"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
