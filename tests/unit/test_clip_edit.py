"""Split marker mechanics for the bridge clip-edit mixin.

Live slides the end marker along with the start marker, so a split has to write
both edges of the clip window or the right half keeps the whole length.
"""

import unittest

from enableton.clip_edit import ClipEditMixin


class FakeSong:
    def __init__(self):
        self.undo_steps = 0

    def begin_undo_step(self):
        self.undo_steps += 1

    def end_undo_step(self):
        pass


class FakeClip:
    def __init__(self, start_time, length, start_marker=0.0, name="clip"):
        self.start_time = float(start_time)
        self._start_marker = float(start_marker)
        self._end_marker = float(start_marker) + float(length)
        self.name = name
        self.is_audio_clip = True
        self.warping = True

    @property
    def start_marker(self):
        return self._start_marker

    @start_marker.setter
    def start_marker(self, value):
        delta = float(value) - self._start_marker
        self._start_marker = float(value)
        self._end_marker += delta

    @property
    def end_marker(self):
        return self._end_marker

    @end_marker.setter
    def end_marker(self, value):
        self._end_marker = float(value)

    @property
    def length(self):
        return self._end_marker - self._start_marker

    @property
    def end_time(self):
        return self.start_time + self.length


class WarpedRefusingClip(FakeClip):
    """Live ignores start_marker writes on warped audio."""

    @property
    def start_marker(self):
        return self._start_marker

    @start_marker.setter
    def start_marker(self, value):
        return None


class FakeTrack:
    def __init__(self, clips):
        self.clips = list(clips)

    @property
    def arrangement_clips(self):
        return tuple(self.clips)

    def duplicate_clip_to_arrangement(self, clip, destination):
        clone = type(clip)(destination, clip.length, start_marker=clip.start_marker, name=clip.name)
        clone._end_marker = clip.end_marker
        self.clips.append(clone)
        self.clips.sort(key=lambda item: item.start_time)
        return clone

    def delete_clip(self, clip):
        self.clips.remove(clip)


class FakeLive(ClipEditMixin):
    def __init__(self, track):
        self._song = FakeSong()
        self._track = track

    def _access_track(self, args):
        return self._track


def split(clip, at):
    track = FakeTrack([clip])
    live = FakeLive(track)
    result = live._split_arrangement_clip(
        {"track_index": 0, "expected_start_time": clip.start_time, "split_at": at}
    )
    return sorted(track.clips, key=lambda item: item.start_time), result


class SplitTests(unittest.TestCase):
    def test_split_trims_both_halves(self):
        (left, right), result = split(FakeClip(0.0, 452.836), 100.0)
        self.assertEqual(left.start_time, 0.0)
        self.assertAlmostEqual(left.end_time, 100.0, places=6)
        self.assertAlmostEqual(right.start_time, 100.0, places=6)
        self.assertAlmostEqual(right.end_time, 452.836, places=6)
        self.assertAlmostEqual(right.length, 352.836, places=6)
        self.assertAlmostEqual(result["right"]["end"], 452.836, places=6)

    def test_split_keeps_existing_marker_window(self):
        (left, right), _ = split(FakeClip(0.0, 452.836, start_marker=50.0), 100.0)
        self.assertAlmostEqual(left.end_marker, 150.0, places=6)
        self.assertAlmostEqual(right.start_marker, 150.0, places=6)
        self.assertAlmostEqual(right.end_marker, 502.836, places=6)
        self.assertAlmostEqual(right.length, 352.836, places=6)

    def test_split_refuses_unwarped_audio(self):
        clip = FakeClip(0.0, 100.0)
        clip.warping = False
        with self.assertRaises(ValueError):
            split(clip, 50.0)

    def test_split_cancels_when_live_ignores_start_marker(self):
        clip = WarpedRefusingClip(0.0, 452.836)
        track = FakeTrack([clip])
        live = FakeLive(track)
        with self.assertRaises(RuntimeError) as caught:
            live._split_arrangement_clip(
                {"track_index": 0, "expected_start_time": 0.0, "split_at": 100.0}
            )
        self.assertIn("no change kept", str(caught.exception))
        self.assertEqual(len(track.clips), 1)
        self.assertAlmostEqual(track.clips[0].end_marker, 452.836, places=6)


if __name__ == "__main__":
    unittest.main()
