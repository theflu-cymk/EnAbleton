"""Unit tests for the Replicate clients; every network call is mocked."""

import json
import os
import unittest
from unittest.mock import patch

from enableton import replicate_audio


class TokenTests(unittest.TestCase):
    def test_requires_token(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as caught:
                replicate_audio.api_token()
        self.assertIn("REPLICATE_API_TOKEN", str(caught.exception))

    def test_model_slug_needs_version(self):
        with patch.dict(os.environ, {"REPLICATE_STRUCTURE_MODEL": "owner/model"}):
            with patch.dict(os.environ, {"REPLICATE_API_TOKEN": "token"}):
                with self.assertRaises(ValueError):
                    replicate_audio.analyze_song_structure("C:/audio.wav")


class StructureTests(unittest.TestCase):
    def _report(self, output, **kwargs):
        with patch.dict(os.environ, {"REPLICATE_API_TOKEN": "token"}, clear=False):
            with patch.object(replicate_audio, "run_model", return_value=output):
                return replicate_audio.analyze_song_structure("C:/audio.wav", **kwargs)

    def test_parses_json_string_output(self):
        payload = json.dumps(
            {
                "bpm": 128.0,
                "segments": [{"start": 0.0, "end": 16.0, "label": "intro"}],
                "beats": [0.0, 0.46875],
                "downbeats": [0.0],
                "key": "F minor",
            }
        )
        report = self._report({"output": payload, "model": "m", "version": "v", "metrics": {}})
        self.assertEqual(report["bpm"], 128.0)
        self.assertEqual(report["key"], "F minor")
        self.assertEqual(report["segments"][0]["label"], "intro")
        self.assertEqual(report["downbeats"], [0.0])
        self.assertIn("verify", report["note"].lower())

    def test_can_drop_beats_and_key(self):
        payload = json.dumps({"bpm": 90.0, "segments": []})
        report = self._report(
            {"output": payload, "model": "m", "version": "v", "metrics": None},
            include_beats=False,
            include_key=False,
        )
        self.assertNotIn("beats", report)
        self.assertNotIn("key", report)

    def test_target_bpm_is_validated_before_upload(self):
        with self.assertRaises(ValueError):
            self._report({"output": "{}", "model": "m", "version": "v"}, target_bpm=5)

    def test_rejects_output_without_bpm(self):
        with self.assertRaises(RuntimeError):
            self._report({"output": json.dumps({"segments": []}), "model": "m", "version": "v"})

    def test_rejects_missing_output(self):
        with self.assertRaises(RuntimeError):
            self._report({"output": None, "model": "m", "version": "v"})


class DescribeTests(unittest.TestCase):
    def test_joins_streamed_output(self):
        with patch.dict(os.environ, {"REPLICATE_API_TOKEN": "token"}, clear=False):
            with patch.object(
                replicate_audio,
                "run_model",
                return_value={"output": ["F minor, ", "slow build"], "model": "m", "version": "v"},
            ):
                report = replicate_audio.describe_audio("C:/audio.wav", "What key?")
        self.assertEqual(report["description"], "F minor, slow build")
        self.assertIn("unverified", report["note"])

    def test_requires_prompt(self):
        with self.assertRaises(ValueError):
            replicate_audio.describe_audio("C:/audio.wav", "  ")
        with self.assertRaises(ValueError):
            replicate_audio.describe_audio("C:/audio.wav", "question", max_new_tokens=0)


class UploadTests(unittest.TestCase):
    def test_rejects_bad_file(self):
        with self.assertRaises(ValueError):
            replicate_audio.upload("C:/missing.wav", "token")
        with self.assertRaises(ValueError):
            replicate_audio._local_file("relative.wav")


if __name__ == "__main__":
    unittest.main()
