"""Fake-Live tests for direct Arrangement audio import."""

import os
import tempfile
import unittest

from enableton.clip_edit import ClipEditMixin


class Clip:
    def __init__(self, start, end, name="Audio"):
        self.start_time = start
        self.end_time = end
        self.name = name
        self.is_audio_clip = True


class Track:
    def __init__(self, audio=True, creator=True):
        self.name = "Audio"
        self.has_audio_input = audio
        self.has_midi_input = not audio
        self._clips = []
        self.deleted = []
        self.length = 4.0
        if creator:
            self.create_audio_clip = self._create

    @property
    def arrangement_clips(self):
        # Live returns a new wrapper on every read. Identity must not be the match.
        return [Clip(clip.start_time, clip.end_time, clip.name) for clip in self._clips]

    def _create(self, path, position):
        self._clips.append(Clip(position, position + self.length, "Imported"))
        self.last_path = path

    def delete_clip(self, clip):
        for index, stored in enumerate(self._clips):
            if stored is clip or (
                abs(float(stored.start_time) - float(clip.start_time)) < 1e-3
                and abs(float(stored.end_time) - float(clip.end_time)) < 1e-3
            ):
                self.deleted.append(self._clips.pop(index))
                return
        raise AssertionError("delete_clip missed the underlying clip")


class Song:
    def __init__(self):
        self.steps = []

    def begin_undo_step(self):
        self.steps.append("begin")

    def end_undo_step(self):
        self.steps.append("end")


class Host(ClipEditMixin):
    def __init__(self, track):
        self.track = track
        self._song = Song()

    def _access_track(self, args):
        if args.get("expected_track_name") != self.track.name:
            raise ValueError("expected_track_name no longer matches")
        return self.track


class ArrangementAudioTests(unittest.TestCase):
    def setUp(self):
        handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        handle.write(b"RIFF")
        handle.close()
        self.path = handle.name
        self.track = Track()
        self.host = Host(self.track)

    def tearDown(self):
        os.remove(self.path)

    def args(self, **extra):
        payload = {
            "path": self.path,
            "position": 0,
            "expected_track_name": "Audio",
            "track_index": 0,
        }
        payload.update(extra)
        return payload

    def test_requires_an_absolute_existing_file_and_an_audio_track(self):
        with self.assertRaisesRegex(ValueError, "expected_track_name"):
            self.host._create_arrangement_audio_clip({"path": self.path, "position": 0})
        with self.assertRaisesRegex(ValueError, "absolute"):
            self.host._create_arrangement_audio_clip(self.args(path="kick.wav"))
        with self.assertRaisesRegex(ValueError, "does not exist"):
            self.host._create_arrangement_audio_clip(
                self.args(path=os.path.join(tempfile.gettempdir(), "missing-enableton.wav"))
            )
        self.track.has_midi_input = True
        with self.assertRaisesRegex(ValueError, "not an audio track"):
            self.host._create_arrangement_audio_clip(self.args())

    def test_refuses_a_live_build_without_the_creator(self):
        host = Host(Track(creator=False))
        with self.assertRaisesRegex(RuntimeError, "Track.create_audio_clip"):
            host._create_arrangement_audio_clip(self.args())

    def test_refuses_a_position_inside_an_existing_clip(self):
        self.track._clips.append(Clip(0, 8, "Kept"))
        with self.assertRaisesRegex(ValueError, "inside an existing"):
            self.host._create_arrangement_audio_clip(self.args(position=4))
        self.assertEqual(self.host._song.steps, [])
        self.assertEqual(len(self.track._clips), 1)

    def test_imports_at_a_free_beat(self):
        self.track._clips.append(Clip(0, 4, "Kept"))
        report = self.host._create_arrangement_audio_clip(self.args(position=16))
        self.assertTrue(report["imported"])
        self.assertEqual(report["start_time"], 16)
        self.assertEqual(report["length"], 4)
        self.assertFalse(report["playback_started"])
        self.assertEqual(self.host._song.steps, ["begin", "end"])
        self.assertEqual([clip.name for clip in self.track._clips], ["Kept", "Imported"])
        first = self.track.arrangement_clips[-1]
        second = self.track.arrangement_clips[-1]
        self.assertIsNot(first, second)

    def test_removes_an_import_that_overlaps_a_later_clip(self):
        self.track._clips.append(Clip(10, 14, "Later"))
        self.track.length = 8
        with self.assertRaisesRegex(ValueError, "overlapped"):
            self.host._create_arrangement_audio_clip(self.args(position=8))
        self.assertEqual([clip.name for clip in self.track._clips], ["Later"])
        self.assertEqual(self.host._song.steps, ["begin", "end"])

    def test_removes_an_import_that_misses_the_requested_beat(self):
        def place_late(path, position):
            self.track._clips.append(Clip(position + 1, position + 5, "Late"))
            self.track.last_path = path

        self.track.create_audio_clip = place_late
        with self.assertRaisesRegex(RuntimeError, "not found at the requested beat"):
            self.host._create_arrangement_audio_clip(self.args(position=16))
        self.assertEqual(self.track._clips, [])
        self.assertEqual(self.host._song.steps, ["begin", "end"])
