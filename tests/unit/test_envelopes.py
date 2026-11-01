import unittest
from types import SimpleNamespace
from enableton.envelope_support import EnvelopeSupportMixin, plan_steps


class FakeEnvelope:
    def __init__(self):
        self.steps = []

    def insert_step(self, t, duration, value):
        self.steps.append((t, duration, value))

    def value_at_time(self, time):
        for t, duration, value in reversed(self.steps):
            if t <= time < t + duration:
                return value
        return 0


class FakeClip:
    name = "SUB"
    loop_start = 0
    loop_end = 4
    is_session_clip = True
    is_recording = False

    def __init__(self):
        self.envelopes = {}

    def automation_envelope(self, param):
        return self.envelopes.get(id(param))

    def clear_envelope(self, param):
        del self.envelopes[id(param)]

    def create_automation_envelope(self, param):
        envelope = FakeEnvelope()
        self.envelopes[id(param)] = envelope
        return envelope


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.clip = FakeClip()
        self.param = SimpleNamespace(
            name="Drive", min=-1.0, max=1.0, is_enabled=True, is_quantized=False
        )
        self.other = SimpleNamespace(name="other")
        self.clip.envelopes[id(self.other)] = FakeEnvelope()
        track = SimpleNamespace(
            name="SUB TRACK",
            clip_slots=[SimpleNamespace(has_clip=True, clip=self.clip)],
            devices=[SimpleNamespace(parameters=[self.param])],
            mixer_device=SimpleNamespace(volume=self.param, panning=self.param, sends=[self.param]),
        )
        self.undo = []
        self.bridge = EnvelopeSupportMixin()
        self.bridge._song = SimpleNamespace(
            tracks=[track],
            begin_undo_step=lambda: self.undo.append("begin"),
            end_undo_step=lambda: self.undo.append("end"),
        )
        self.args = dict(
            track_index=0,
            clip_index=0,
            device_index=0,
            parameter_index=0,
            points=[dict(time=0, value=-1), dict(time=2, value=1)],
            resolution=0.5,
        )

    def test_write_native_values_and_readback(self):
        result = self.bridge._write_clip_envelope(self.args)
        self.assertTrue(result["verified"])
        self.assertEqual(result["steps_written"], 5)
        self.assertEqual(self.undo, ["begin", "end"])
        samples = self.bridge._get_clip_envelope(dict(self.args, times=[0.25, 1.75, 3]))
        self.assertEqual([s["value"] for s in samples["samples"]], [-1, 0.5, 1])
        self.assertIn(id(self.other), self.clip.envelopes)

    def test_existing_envelope_requires_explicit_replacement(self):
        self.bridge._write_clip_envelope(self.args)
        previous = self.clip.envelopes[id(self.param)]
        with self.assertRaisesRegex(ValueError, "already has"):
            self.bridge._write_clip_envelope(self.args)
        self.assertIs(self.clip.envelopes[id(self.param)], previous)
        self.bridge._write_clip_envelope(dict(self.args, replace=True))
        self.assertIn(id(self.other), self.clip.envelopes)

    def test_invalid_request_never_erases_existing(self):
        self.bridge._write_clip_envelope(self.args)
        previous = self.clip.envelopes[id(self.param)]
        for points in [
            [dict(time=0, value=float("nan"))],
            [dict(time=0, value=2)],
            [dict(time=1, value=0)],
            [dict(time=0, value=0), dict(time=0, value=1)],
        ]:
            with self.subTest(points=points), self.assertRaises(ValueError):
                self.bridge._write_clip_envelope(dict(self.args, points=points, replace=True))
            self.assertIs(self.clip.envelopes[id(self.param)], previous)

    def test_nested_indexes_and_stale_names(self):
        for override in [
            dict(track_index=-1),
            dict(device_index=-1),
            dict(parameter_index=True),
            dict(clip_index=99),
            dict(expected_track_name="wrong"),
            dict(expected_clip_name="wrong"),
        ]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.bridge._write_clip_envelope(dict(self.args, **override))
        self.assertEqual(self.undo, [])

    def test_quantized_requires_hold(self):
        self.param.is_quantized = True
        with self.assertRaises(ValueError):
            self.bridge._write_clip_envelope(self.args)
        self.assertTrue(
            self.bridge._write_clip_envelope(dict(self.args, interpolation="hold"))["verified"]
        )

    def test_step_budget(self):
        with self.assertRaisesRegex(ValueError, "2048 steps"):
            plan_steps(
                [dict(time=0, value=0), dict(time=4, value=1)], 0, 4, 0, 1, "linear", 1 / 960
            )

    def test_positive_durations_and_nonzero_loop_start(self):
        steps = plan_steps(
            [dict(time=4, value=0), dict(time=8, value=1)], 4, 8, 0, 1, "linear", 0.0625
        )
        self.assertTrue(all(d > 0 for _, d, _ in steps))
        self.assertEqual(steps[-1][0] + steps[-1][1], 8)

    def test_mixer_targets(self):
        for target in ["volume", "pan", "send"]:
            result = self.bridge._write_clip_envelope(
                dict(self.args, target=target, send_index=0, replace=True)
            )
            self.assertTrue(result["verified"])

    def test_recording_and_arrangement_rejected(self):
        self.clip.is_recording = True
        with self.assertRaises(ValueError):
            self.bridge._write_clip_envelope(self.args)
        self.clip.is_recording = False
        self.clip.is_session_clip = False
        with self.assertRaises(ValueError):
            self.bridge._write_clip_envelope(self.args)

    def test_failure_closes_undo_step(self):
        def fail(param):
            raise RuntimeError("Live failure")

        self.clip.create_automation_envelope = fail
        with self.assertRaisesRegex(RuntimeError, "partial"):
            self.bridge._write_clip_envelope(self.args)
        self.assertEqual(self.undo, ["begin", "end"])

    def test_read_is_nonmutating_and_bounded(self):
        self.assertFalse(self.bridge._get_clip_envelope(dict(self.args, times=[0]))["exists"])
        self.assertEqual(self.undo, [])
        for times in [[4], [float("inf")], [0] * 2049]:
            with self.assertRaises(ValueError):
                self.bridge._get_clip_envelope(dict(self.args, times=times))


if __name__ == "__main__":
    unittest.main(verbosity=2)
