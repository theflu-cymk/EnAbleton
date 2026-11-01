import unittest
from enableton.mastering_recipes import catalog, plan, RECIPES
from test_bass import Registry
from enableton.bass_tools import register


class MasteringTests(unittest.TestCase):
    def test_plans_are_read_only_and_all_stages_have_sources(self):
        def forbidden(*a):
            raise AssertionError("Must not contact Live")

        r = Registry()
        register(r, forbidden)
        for profile in ["transparent", "tearout_dense", "spotify_delivery"]:
            p = r.tools["preview_mastering_plan"](profile)
            self.assertIn("Read-only", p["execution"])
            for stage in p["steps"]:
                self.assertIn(stage["id"], RECIPES)
                self.assertTrue(all(s in p["sources"] for s in stage["sources"]))
        self.assertEqual(len(r.tools["mastering_recipe_catalog"]()["recipes"]), 7)

    def test_spotify_ceiling_is_conditional(self):
        self.assertEqual(plan("spotify_delivery", -9)["ceiling_dbtp"], -2)
        self.assertEqual(plan("spotify_delivery", -14)["ceiling_dbtp"], -1)
        self.assertEqual(plan("spotify_delivery")["ceiling_dbtp"], -2)

    def test_reported_peak_does_not_certify_master(self):
        self.assertIn("exceeds", plan("spotify_delivery", -9, -1)["peak_review"])
        self.assertIn("does not certify", plan("spotify_delivery", -9, -2.1)["peak_review"])
        self.assertIn("Caller supplied", plan(measured_lufs=-8)["measurements"]["origin"])

    def test_invalid_measurements_and_names(self):
        for value in [True, float("nan"), float("inf"), "loud"]:
            with self.assertRaises(ValueError):
                plan(measured_lufs=value)
            with self.assertRaises(ValueError):
                plan(measured_true_peak_dbtp=value)
        with self.assertRaises(ValueError):
            plan("unknown")
        with self.assertRaises(ValueError):
            catalog("unknown")

    def test_results_do_not_mutate_templates(self):
        p = plan()
        p["steps"][0]["procedure"].clear()
        c = catalog()
        c["recipes"].clear()
        self.assertTrue(plan()["steps"][0]["procedure"])
        self.assertEqual(len(catalog()["recipes"]), 7)


if __name__ == "__main__":
    unittest.main()
