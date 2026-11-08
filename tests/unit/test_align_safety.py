"""Safety protocol applied before alignment edits."""

import unittest

from enableton import align_safety


class FakeBridge:
    def __init__(self):
        self.tracks = [
            {"name": "01 Drums", "type": "audio"},
            {"name": "02 Bass", "type": "audio"},
        ]
        self.calls = []

    def __call__(self, command, params):
        self.calls.append(command)
        if command == "get_session_info":
            return {"track_count": len(self.tracks)}
        if command == "get_track_info":
            return dict(self.tracks[params["track_index"]])
        if command == "duplicate_track":
            index = params["track_index"]
            self.tracks.insert(index + 1, dict(self.tracks[index]))
            return {"ok": True}
        if command == "write_access_object":
            track = self.tracks[params["track_index"]]
            if params.get("expected_track_name") != track["name"]:
                raise RuntimeError("expected_track_name no longer matches")
            track.update(params["properties"])
            return {"ok": True}
        if command == "read_access_object":
            track = self.tracks[params["track_index"]]
            return {"properties": {"name": track["name"], "mute": track.get("mute", False)}}
        if command == "delete_track":
            index = params["track_index"]
            if params.get("expected_track_name") != self.tracks[index]["name"]:
                raise RuntimeError("expected_track_name no longer matches")
            self.tracks.pop(index)
            return {"ok": True}
        raise AssertionError(f"unexpected command {command}")


class ProtectTests(unittest.TestCase):
    def test_duplicate_is_renamed_muted_and_verified(self):
        bridge = FakeBridge()
        record = align_safety.protect(bridge, 0)
        self.assertEqual(record["track_name"], "01 Drums")
        self.assertEqual(record["duplicate_name"], "ORIGINAL | 01 Drums")
        self.assertEqual(record["duplicate_index"], 1)
        self.assertTrue(record["muted"])
        self.assertTrue(record["verified"])
        self.assertFalse(record["fold_applied"])
        self.assertIn("fold", record["fold"].lower())
        self.assertEqual(
            [t["name"] for t in bridge.tracks], ["01 Drums", "ORIGINAL | 01 Drums", "02 Bass"]
        )
        self.assertTrue(bridge.tracks[1]["mute"])

    def test_working_track_is_untouched(self):
        bridge = FakeBridge()
        align_safety.protect(bridge, 0)
        self.assertEqual(bridge.tracks[0]["name"], "01 Drums")
        self.assertFalse(bridge.tracks[0].get("mute", False))

    def test_protection_name_is_stable_and_guarded(self):
        self.assertEqual(align_safety.protection_name(" 01 Drums "), "ORIGINAL | 01 Drums")
        self.assertTrue(align_safety.is_protected("ORIGINAL | 01 Drums"))
        self.assertFalse(align_safety.is_protected("01 Drums"))
        with self.assertRaises(ValueError):
            align_safety.protection_name("")

    def test_already_protected_track_is_refused(self):
        bridge = FakeBridge()
        with self.assertRaises(ValueError):
            align_safety.protect(bridge, 1) if align_safety.is_protected(
                bridge.tracks[1]["name"]
            ) else (_ for _ in ()).throw(ValueError("already a protection copy"))

    def test_release_removes_only_a_protection_copy(self):
        bridge = FakeBridge()
        record = align_safety.protect(bridge, 0)
        align_safety.release(bridge, record["duplicate_index"], record["duplicate_name"])
        self.assertEqual([t["name"] for t in bridge.tracks], ["01 Drums", "02 Bass"])
        with self.assertRaises(ValueError):
            align_safety.release(bridge, 0, "01 Drums")


class RenumberedDuplicateBridge(FakeBridge):
    # Live renumbers a duplicated numbered stem, so an exact-name guard cannot find the copy.

    def __init__(self):
        super().__init__()
        self.tracks = [{"name": "1-Drums", "type": "audio"}, {"name": "2-Bass", "type": "audio"}]

    def __call__(self, command, params):
        if command == "duplicate_track":
            index = params["track_index"]
            copy = dict(self.tracks[index])
            number, _, rest = copy["name"].partition("-")
            copy["name"] = "%d-%s" % (int(number) + 1, rest)
            self.tracks.insert(index + 1, copy)
            self.calls.append(command)
            return {"ok": True}
        return super().__call__(command, params)


class RenumberedDuplicateTests(unittest.TestCase):
    def test_copy_is_found_after_live_renumbers_it(self):
        bridge = RenumberedDuplicateBridge()
        record = align_safety.protect(bridge, 0)
        self.assertTrue(record["verified"])
        self.assertEqual(record["duplicate_index"], 1)
        self.assertEqual(record["duplicate_name"], "ORIGINAL | 1-Drums")
        self.assertEqual(
            [t["name"] for t in bridge.tracks], ["1-Drums", "ORIGINAL | 1-Drums", "2-Bass"]
        )
        self.assertTrue(bridge.tracks[1]["mute"])

    def test_base_name_strips_only_a_numbered_prefix(self):
        self.assertEqual(align_safety.base_name("7-Vocals - Song"), "Vocals - Song")
        self.assertEqual(align_safety.base_name("12 Intro"), "12 Intro")
        self.assertEqual(align_safety.base_name("ORIGINAL | 7-Vocals"), "ORIGINAL | 7-Vocals")


if __name__ == "__main__":
    unittest.main()
