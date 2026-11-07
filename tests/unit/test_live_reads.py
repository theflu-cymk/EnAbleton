from copy import deepcopy
import unittest

from enableton.live_reads import read_many
from enableton.song_lint import collect_live
from test_song_lint import FakeLive


class CountConnection:
    def __init__(self, live):
        self.live = live
        self.calls = []

    def send_command(self, kind, params):
        self.calls.append((kind, deepcopy(params)))
        return self.live.send_command(kind, params)


class ManyTracks(FakeLive):
    def send_command(self, kind, params):
        i = params.get("track_index", 0)
        if kind == "get_session_info":
            result = super().send_command(kind, params)
            result["track_count"] = 24
            return result
        if kind == "get_track_info":
            result = super().send_command(kind, dict(params, track_index=0))
            result.update(index=i, name=f"MIDI {i}")
            return result
        if kind == "get_group_info":
            return {"is_foldable": False, "group_track": None}
        if kind == "get_arrangement_clips":
            return super().send_command(kind, dict(params, track_index=0))
        return super().send_command(kind, params)


class ReadBatchTests(unittest.TestCase):
    def test_24_track_scan_uses_six_transport_calls(self):
        connection = CountConnection(ManyTracks())
        state = collect_live(connection)
        self.assertEqual(state["capture_errors"], [])
        self.assertEqual(len(state["tracks"]), 24)
        self.assertEqual(len(connection.calls), 6)
        self.assertEqual(state["capture_metrics"]["roundTrips"], 6)

    def test_scoped_reads_never_visit_other_tracks(self):
        connection = CountConnection(ManyTracks())
        state = collect_live(connection, track_indices=[7])
        self.assertEqual([t["index"] for t in state["tracks"]], [7])
        self.assertFalse(state["capture_scope"]["full_set"])
        self.assertTrue(all(p.get("track_index", 7) == 7 for _, p in connection.calls))

    def test_rejects_invalid_scopes(self):
        for scope in [[True], [24], [-1], [0, 0]]:
            with self.assertRaises(ValueError):
                collect_live(ManyTracks(), track_indices=scope)

    def test_command_failure_isolated_without_losing_good_reads(self):
        def call(kind, params):
            if kind == "batch":
                return {
                    "results": [
                        {"result": call(c["type"], c["params"])} for c in params["commands"]
                    ]
                }
            if params["track_index"] == 2:
                raise RuntimeError("Unavailable")
            return params["track_index"]

        rows = read_many(
            call, [{"type": "get_track_info", "params": {"track_index": i}} for i in range(8)]
        )
        self.assertEqual([value for value, error in rows if error is None], [0, 1, 3, 4, 5, 6, 7])
        self.assertIsNotNone(rows[2][1])

    def test_timeout_does_not_fan_out_into_individual_retries(self):
        calls = []

        def call(kind, params):
            calls.append(kind)
            raise TimeoutError("No reply")

        rows = read_many(call, [{"type": "get_track_info", "params": {}}] * 48)
        self.assertEqual(calls, ["batch"])
        self.assertTrue(all(error is not None for _, error in rows))

    def test_partial_response_surfaces_incomplete_capture(self):
        rows = read_many(lambda *_: {"results": []}, [{"type": "get_track_info", "params": {}}] * 2)
        self.assertTrue(all(value is None and error is not None for value, error in rows))

    def test_cannot_use_read_helper_for_writes(self):
        with self.assertRaises(ValueError):
            read_many(
                lambda *_: self.fail("Must not dispatch"), [{"type": "delete_track", "params": {}}]
            )

    def test_batches_are_bounded(self):
        sizes = []

        def call(kind, params):
            sizes.append(len(params["commands"]))
            return {"results": [{"result": 1}] * len(params["commands"])}

        self.assertEqual(
            len(read_many(call, [{"type": "get_track_info", "params": {}}] * 100)), 100
        )
        self.assertEqual(sizes, [48, 48, 4])
