from copy import deepcopy
import unittest

from enableton.remix_midi import clean_transcription


def note(pitch, start, duration, **kw):
    return dict(pitch=pitch, start_time=start, duration=duration, velocity=90, mute=False, **kw)


class MidiCleanupTests(unittest.TestCase):
    def test_duplicates_fragments_and_overlaps_preserve_original(self):
        source = [note(40, 0, 2), note(40, 0, 2), note(40, 1, 2), note(41, 4, 0.005)]
        original = deepcopy(source)
        result = clean_transcription(source, dict(snap_strength=0))
        self.assertEqual(source, original)
        self.assertEqual(result["report"]["duplicates_removed"], 1)
        self.assertEqual(result["report"]["short_removed"], 1)
        self.assertEqual([n["duration"] for n in result["notes"]], [1, 2])

    def test_lowest_voice_returns_upper_note_after_low_note_ends(self):
        source = [note(52, 0, 4), note(28, 1, 2)]
        result = clean_transcription(source, dict(monophonic_lowest=True, snap_strength=0))
        self.assertEqual(
            [(n["pitch"], n["start_time"], n["duration"]) for n in result["notes"]],
            [(52, 0, 1), (28, 1, 2), (52, 3, 1)],
        )

    def test_register_preserves_pitch_class_and_trims_octave_collisions(self):
        result = clean_transcription(
            [note(28, 0, 3), note(40, 1, 2)], dict(register=[36, 59], snap_strength=0)
        )
        self.assertEqual([n["pitch"] for n in result["notes"]], [40, 40])
        self.assertEqual(result["notes"][0]["duration"], 1)
        self.assertEqual(result["report"]["octave_adjustments"], 1)

    def test_snapping_only_nearby_onsets_and_no_key_correction(self):
        result = clean_transcription(
            [note(37, 0.02, 0.4), note(38, 1.11, 0.4)],
            dict(snap_grid=0.25, snap_tolerance=0.03, snap_strength=0.5),
        )
        self.assertAlmostEqual(result["notes"][0]["start_time"], 0.01)
        self.assertEqual(result["notes"][1]["start_time"], 1.11)
        self.assertEqual([n["pitch"] for n in result["notes"]], [37, 38])

    def test_muted_notes_survive_monophonic_cleanup_unchanged(self):
        muted = dict(note(1, 0.01, 0.001), mute=True)
        result = clean_transcription(
            [note(40, 0, 4), muted], dict(monophonic_lowest=True, register=[36, 59])
        )
        self.assertIn(muted, result["notes"])

    def test_invalid_policies_are_refused(self):
        for policy in [
            dict(monophonic_lowest=1),
            dict(register=[70, 60]),
            dict(snap_strength=float("nan")),
            dict(key_snap=True),
        ]:
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                clean_transcription([], policy)
