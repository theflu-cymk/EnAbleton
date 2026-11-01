import unittest
from enableton.artist_methods import catalog, DATA
from enableton.bass_recipes import get_recipe, RECIPES
from enableton.bass_tools import register
from test_bass import Registry


class ArtistTests(unittest.TestCase):
    def test_aliases_and_unknown_artist(self):
        self.assertEqual(catalog("Volpetron")["artists"][0]["id"], "ray-volpe")
        self.assertEqual(catalog("ray_volpe"), catalog("Ray Volpe"))
        self.assertEqual(len(catalog()["artists"]), 4)
        for artist in ["unknown", None, True]:
            with self.assertRaises(ValueError):
                catalog(artist)

    def test_native_patch_provenance_and_base_independence(self):
        self.assertTrue(set(DATA["patches"]).issubset(RECIPES))
        for key, patch in DATA["patches"].items():
            r = get_recipe(key)
            self.assertIn("not artist presets", r["provenance"])
            self.assertIn("artist_evidence_scope", r)
            self.assertNotEqual(r["chain"], get_recipe(patch["base"])["chain"])
            r["chain"][0]["parameters"].clear()
            self.assertTrue(get_recipe(patch["base"])["chain"][0]["parameters"])

    def test_workflows_resolve_sources_and_keep_evidence_separate(self):
        result = catalog()
        for profile in result["artists"]:
            self.assertEqual(len(profile["native_recipes"]), 1)
            for method in profile["methods"]:
                self.assertTrue(method["documented_findings"])
                self.assertTrue(all(k in result["sources"] for k in method["sources"]))
        vulper = catalog("vulper")["artists"][0]
        self.assertIn("No detailed first-person", vulper["scope"])
        self.assertTrue(any(m["status"] == "Limited evidence" for m in vulper["methods"]))

    def test_read_only_tool_and_copy_isolation(self):
        registry = Registry()

        def forbidden(*args):
            raise AssertionError("Catalog must not contact Live")

        register(registry, forbidden)
        result = registry.tools["artist_bass_catalog"]("Subtronics")
        self.assertIn("Read-only", result["execution"])
        result["artists"][0]["methods"].clear()
        self.assertEqual(len(catalog("Subtronics")["artists"][0]["methods"]), 2)


if __name__ == "__main__":
    unittest.main()
