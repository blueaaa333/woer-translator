import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pronunciation import SpeechEngine


def install_voice_fixture(root, accent):
    """Create a selector-valid model/config pair; this test does not infer."""
    name = "uk" if accent == 1 else "us"
    language = "en_GB" if accent == 1 else "en_US"
    folder = Path(root) / "speech" / "voices" / name
    folder.mkdir(parents=True)
    model = folder / "dictionary-voice.onnx"
    model.write_bytes(b"fixture-only-not-used-for-inference".ljust(1_000_001, b"x"))
    (folder / "dictionary-voice.onnx.json").write_text(
        json.dumps({"language": {"code": language}, "dataset": "latency-fixture"}),
        encoding="utf-8",
    )


class LatencyTests(unittest.TestCase):
    def test_local_cache_skips_network(self):
        with tempfile.TemporaryDirectory() as d:
            engine = SpeechEngine(d, d)
            try:
                with (
                    patch.object(engine.recordings, "cached", return_value=None),
                    patch.object(engine, "cached_synthesis", return_value=Path("hit.wav")),
                    patch.object(engine.recordings, "get", side_effect=AssertionError("network")),
                ):
                    self.assertEqual(engine.render("water", 1), Path("hit.wav"))
            finally:
                engine.close()

    def test_slow_recording_is_bounded_and_not_queued(self):
        with tempfile.TemporaryDirectory() as d:
            install_voice_fixture(d, 1)
            install_voice_fixture(d, 2)
            engine = SpeechEngine(d, d)
            release = threading.Event()
            started = threading.Event()

            def slow(*args):
                started.set()
                release.wait(2)

            try:
                with patch("pronunciation.Recordings.get", side_effect=slow) as get:
                    started_at = time.monotonic()
                    self.assertIsNone(engine.quick_recording("water", 1))
                    self.assertLess(time.monotonic() - started_at, 0.6)
                    self.assertTrue(started.is_set())
                    self.assertIsNone(engine.quick_recording("hello", 2))
                    self.assertEqual(get.call_count, 1)
                    release.set()
            finally:
                release.set()
                engine.close()


if __name__ == "__main__":
    unittest.main()

