import unittest

from enableton import song_processes


def state(clip_list):
    return {
        "tracks": [
            {
                "id": "track:0",
                "name": "4-2 Drums",
                "type": "audio",
                "role": "drums",
                "clips": clip_list,
            }
        ],
        "session": {"tempo": 100},
    }


def clip(markers, warping=True):
    return {
        "id": "track:0:arrangement:0",
        "name": "2 Drums",
        "type": "audio",
        "warping": warping,
        "warp_markers": [{"beat_time": index} for index in range(markers)],
    }


class UnwrapDefaultTests(unittest.TestCase):
    def test_requires_a_reference(self):
        result = song_processes.REGISTRY["unwrap_layers"](state([clip(5)]), {}, {})
        self.assertEqual(result.changes, [])
        self.assertTrue(any("reference" in notice for notice in result.notices))

    def test_warped_layer_requires_a_render(self):
        result = song_processes.REGISTRY["unwrap_layers"](
            state([clip(5)]), {"reference": "track:0"}, {}
        )
        self.assertEqual(result.changes, [])
        self.assertTrue(any("Render required" in notice for notice in result.notices))

    def test_layer_without_markers_is_unwrapped_directly(self):
        result = song_processes.REGISTRY["unwrap_layers"](
            state([clip(2)]), {"reference": "track:0"}, {}
        )
        self.assertEqual(result.changes[0]["patch"], {"warping": False})

    def test_set_default_warp_delegates_to_render_first(self):
        result = song_processes.REGISTRY["set_default_warp"](
            state([clip(5)]), {"enabled": False, "reference": "track:0"}, {}
        )
        self.assertEqual(result.changes, [])
        self.assertTrue(any("Render required" in notice for notice in result.notices))

    def test_toggle_escape_hatch_still_toggles(self):
        result = song_processes.REGISTRY["set_default_warp"](
            state([clip(5)]), {"enabled": False, "method": "toggle"}, {}
        )
        self.assertEqual(result.changes[0]["patch"]["warping"], False)


if __name__ == "__main__":
    unittest.main()
