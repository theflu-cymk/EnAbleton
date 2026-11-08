"""Unit tests for the offline .als warp-map injector; no Live and no user media."""

import gzip
import tempfile
import unittest
from pathlib import Path

from enableton import als_warp


def build_set(tracks):
    parts = ['<?xml version="1.0" encoding="utf-8"?>', "<Ableton>", "<LiveSet>", "<Tracks>"]
    for index, (name, markers) in enumerate(tracks):
        block = "\n".join(
            '    <WarpMarker Id="%d" SecTime="%s" BeatTime="%s" />' % (i, sec, beat)
            for i, (sec, beat) in enumerate(markers)
        )
        parts.append('<AudioTrack Id="%d">' % index)
        parts.append('  <Name><EffectiveName Value="%s" /></Name>' % name)
        parts.append('  <AudioClip Id="%d" Time="0">' % index)
        parts.append('    <CurrentStart Value="0" />')
        parts.append('    <CurrentEnd Value="498.88653" />')
        parts.append('    <Loop><LoopStart Value="0" /><LoopEnd Value="498.88653" /></Loop>')
        parts.append("    <WarpMarkers>")
        parts.append(block)
        parts.append("    </WarpMarkers>")
        parts.append('    <WarpMode><Manual Value="4" /></WarpMode>')
        parts.append("  </AudioClip>")
        parts.append("</AudioTrack>")
    parts.extend(["</Tracks>", "</LiveSet>", "</Ableton>"])
    return "\n".join(parts)


class UniformMarkerTests(unittest.TestCase):
    def test_rate_and_anchor(self):
        rows = als_warp.uniform_markers(2.41, 1.6, 249.4556)
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(rows[0]["sec"], 2.41)
        self.assertAlmostEqual(rows[0]["beat"], 0.0, places=6)
        self.assertAlmostEqual(rows[-1]["sec"], 249.4556, places=6)
        self.assertAlmostEqual(rows[-1]["beat"], (249.4556 - 2.41) * 1.6, places=5)

    def test_intermediate_density(self):
        rows = als_warp.uniform_markers(0.0, 1.6, 10.0, step_seconds=2.5)
        self.assertEqual(len(rows), 5)
        self.assertAlmostEqual(rows[2]["sec"], 5.0)
        self.assertAlmostEqual(rows[2]["beat"], 8.0)

    def test_refuses_impossible_anchor(self):
        with self.assertRaises(ValueError):
            als_warp.uniform_markers(300.0, 1.6, 249.4)
        with self.assertRaises(ValueError):
            als_warp.uniform_markers(0.0, 0.0, 249.4)


class InjectTests(unittest.TestCase):
    def setUp(self):
        self.xml = build_set(
            [
                ("5-Piano", [(0.0, 0.0), (0.015625, 0.03125)]),
                ("2-Drums", [(2.24, 0.0), (60.0, 92.0), (249.4, 395.0)]),
            ]
        )

    def test_only_matching_track_changes(self):
        patched, records = als_warp.inject(self.xml, "piano", 1.6, 249.4556, 2.41)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["status"], "retimed")
        self.assertEqual(records[0]["markers_before"], 2)
        self.assertEqual(records[0]["markers_after"], 2)
        drums = [s for s in als_warp.track_spans(patched) if "Drums" in s["name"]][0]
        self.assertIn('SecTime="60.0"', drums["body"])
        piano = [s for s in als_warp.track_spans(patched) if "Piano" in s["name"]][0]
        self.assertIn('SecTime="2.41"', piano["body"])
        self.assertIn('BeatTime="395.27296"', piano["body"])

    def test_bounds_follow_the_retimed_span(self):
        patched, _ = als_warp.inject(self.xml, "piano", 1.6, 249.4556, 2.41)
        piano = [s for s in als_warp.track_spans(patched) if "Piano" in s["name"]][0]
        self.assertIn('<CurrentEnd Value="395.27296"', piano["body"])
        self.assertIn('<LoopEnd Value="395.27296"', piano["body"])
        self.assertIn('<LoopStart Value="0"', piano["body"])

    def test_clip_without_warp_block_is_skipped(self):
        xml = self.xml.replace(
            '<WarpMarkers>\n    <WarpMarker Id="0" SecTime="0.0" BeatTime="0.0" />'
            '\n    <WarpMarker Id="1" SecTime="0.015625" BeatTime="0.03125" />\n    </WarpMarkers>',
            "",
        )
        patched, records = als_warp.inject(xml, "piano", 1.6, 249.4556, 2.41)
        self.assertEqual(
            records,
            [{"track": "5-Piano", "clip_time": "0", "status": "skipped: clip has no warp block"}],
        )
        self.assertEqual(patched, xml)

    def test_in_place_write_creates_backup_and_verifies(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "set.als"
            path.write_bytes(gzip.compress(self.xml.encode("utf-8")))
            report = als_warp.inject_file(path, path, "piano", 1.6, 249.4556, 2.41, dry_run=False)
            self.assertEqual(report["verified_clips"], 1)
            self.assertTrue(Path(report["backup"]).exists())
            reread = als_warp.read_set(path)
            self.assertIn('SecTime="2.41"', reread)
            self.assertEqual(als_warp.read_set(report["backup"]), self.xml)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "set.als"
            original = gzip.compress(self.xml.encode("utf-8"))
            path.write_bytes(original)
            report = als_warp.inject_file(path, path, "piano", 1.6, 249.4556, 2.41)
            self.assertEqual(report["changed"], 1)
            self.assertTrue(report["dry_run"])
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(folder).glob("*.bak-*")), [])


if __name__ == "__main__":
    unittest.main()
