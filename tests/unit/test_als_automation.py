"""Unit tests for offline clip-envelope injection; synthetic .als fixtures only."""

import gzip
import tempfile
import unittest
from pathlib import Path

from enableton import als_automation

CONTROLLERS = (
    '<MidiControllers><ControllerTargets.22 Id="9000" />'
    '<ControllerTargets.23 Id="9001" /></MidiControllers>'
)

EMPTY_ENVELOPES = "<Envelopes><Envelopes /></Envelopes>"

FILLED_ENVELOPES = (
    '<Envelopes><Envelopes><ClipEnvelope Id="7"><EnvelopeTarget>'
    '<PointeeId Value="9000" /></EnvelopeTarget><Automation><Events>'
    '<FloatEvent Id="0" Time="-63072000" Value="5" /></Events>'
    "</Automation></ClipEnvelope></Envelopes></Envelopes>"
)

POINTS = [{"time": 0.0, "value": 0.0}, {"time": 4.0, "value": 1.0}]


def midi_track(name, envelope, controller=True, clip_time="8"):
    return "\n".join(
        [
            '<MidiTrack Id="1">',
            '  <Name><EffectiveName Value="%s" /></Name>' % name,
            "  " + (CONTROLLERS if controller else ""),
            '  <MidiClip Id="3" Time="%s">' % clip_time,
            "  " + envelope,
            '    <CurrentStart Value="8" /><CurrentEnd Value="40" />',
            "  </MidiClip>",
            "</MidiTrack>",
        ]
    )


def build_set(controller=True, existing_envelope=False, extra_midi=False):
    envelope = FILLED_ENVELOPES if existing_envelope else EMPTY_ENVELOPES
    tracks = [midi_track("Structure", envelope, controller)]
    if extra_midi:
        tracks.append(midi_track("Structure 2", EMPTY_ENVELOPES, controller))
    tracks.append(
        "\n".join(
            [
                '<AudioTrack Id="2">',
                '  <Name><EffectiveName Value="Bass" /></Name>',
                '  <AudioClip Id="4" Time="0"><WarpMarkers /></AudioClip>',
                "</AudioTrack>",
            ]
        )
    )
    return "\n".join(
        ['<?xml version="1.0" encoding="utf-8"?>', "<Ableton><LiveSet><Tracks>", *tracks]
        + ["</Tracks></LiveSet></Ableton>"]
    )


class InjectionTests(unittest.TestCase):
    def test_writes_events_with_initial_marker(self):
        patched, report = als_automation.inject(build_set(), "structure", 8, 22, POINTS)
        self.assertEqual(report["pointee_id"], "9000")
        self.assertFalse(report["replaced"])
        self.assertIn('<PointeeId Value="9000"', patched)
        self.assertEqual(patched.count("<FloatEvent"), 3)
        self.assertIn('Time="-63072000"', patched)
        self.assertIn('Value="127"', patched)
        self.assertNotIn(EMPTY_ENVELOPES, patched)

    def test_audio_track_is_untouched(self):
        original = build_set()
        patched, _ = als_automation.inject(original, "structure", 8, 22, POINTS)
        self.assertIn(original[original.index("<AudioTrack") :], patched)

    def test_missing_controller_target_raises(self):
        with self.assertRaises(ValueError) as caught:
            als_automation.inject(build_set(controller=False), "structure", 8, 22, POINTS)
        self.assertIn("ControllerTargets.22", str(caught.exception))

    def test_unknown_and_ambiguous_track_raise(self):
        with self.assertRaises(ValueError):
            als_automation.inject(build_set(), "missing", 8, 22, POINTS)
        with self.assertRaises(ValueError) as caught:
            als_automation.inject(build_set(extra_midi=True), "structure", 8, 22, POINTS)
        self.assertIn("several MIDI tracks", str(caught.exception))

    def test_exact_clip_time_match(self):
        with self.assertRaises(ValueError) as caught:
            als_automation.inject(build_set(), "structure", 8.5, 22, POINTS)
        self.assertIn("8.5", str(caught.exception))

    def test_existing_envelope_requires_replace(self):
        xml = build_set(existing_envelope=True)
        with self.assertRaises(ValueError):
            als_automation.inject(xml, "structure", 8, 22, POINTS)
        patched, report = als_automation.inject(xml, "structure", 8, 22, POINTS, replace=True)
        self.assertTrue(report["replaced"])
        self.assertEqual(patched.count('<PointeeId Value="9000"'), 1)

    def test_point_validation(self):
        with self.assertRaises(ValueError):
            als_automation.inject(build_set(), "structure", 8, 22, [{"time": 0, "value": 2}])
        with self.assertRaises(ValueError):
            als_automation.inject(
                build_set(),
                "structure",
                8,
                22,
                [{"time": 1, "value": 0.5}, {"time": 1, "value": 0.5}],
            )
        with self.assertRaises(ValueError):
            als_automation.inject(build_set(), "structure", 8, 22, [])


class FileTests(unittest.TestCase):
    def _write(self, folder, **kwargs):
        path = Path(folder) / "set.als"
        path.write_bytes(gzip.compress(build_set(**kwargs).encode("utf-8")))
        return path

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self._write(folder)
            original = path.read_bytes()
            report = als_automation.inject_file(path, "structure", 8, 22, POINTS)
            self.assertTrue(report["dry_run"])
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(folder).glob("*.bak-*")), [])

    def test_in_place_write_backs_up_and_verifies(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self._write(folder)
            original = path.read_bytes()
            report = als_automation.inject_file(path, "structure", 8, 22, POINTS, dry_run=False)
            self.assertEqual(report["envelopes_for_target"], 1)
            self.assertTrue(Path(report["backup"]).exists())
            self.assertEqual(Path(report["backup"]).read_bytes(), original)
            self.assertIn('PointeeId Value="9000"', als_automation.read_set(path))

    def test_copy_writes_without_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = self._write(folder)
            output = Path(folder) / "out.als"
            report = als_automation.inject_file(
                path, "structure", 8, 23, POINTS, str(output), dry_run=False
            )
            self.assertIsNone(report["backup"])
            self.assertTrue(output.exists())
            self.assertIn('PointeeId Value="9001"', als_automation.read_set(output))


if __name__ == "__main__":
    unittest.main()
