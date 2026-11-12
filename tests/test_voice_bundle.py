import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import sys
import importlib.util

PROPOSAL_ROOT = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = PROPOSAL_ROOT / "test-tmp"
TEST_TMP_ROOT.mkdir(exist_ok=True)
VOICE_PROFILE_ROOT = PROPOSAL_ROOT
if not (VOICE_PROFILE_ROOT / "voice_profile.py").is_file():
    VOICE_PROFILE_ROOT = PROPOSAL_ROOT.parent / "woer-public"
sys.path.insert(0, str(VOICE_PROFILE_ROOT))
spec = importlib.util.spec_from_file_location("voice_bundle_candidate", PROPOSAL_ROOT / "scripts" / "voice_bundle.py")
voice_bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(voice_bundle)
audit_bundle = voice_bundle.audit_bundle
cache_output_path = voice_bundle.cache_output_path
choose_runtime_dir = voice_bundle.choose_runtime_dir
choose_voice_folder = voice_bundle.choose_voice_folder


def write_voice(folder, code, model_name="dictionary-voice"):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{model_name}.onnx").write_bytes(b"onnx-fixture")
    (folder / f"{model_name}.onnx.json").write_text(
        json.dumps({"language": {"code": code}, "espeak": {"voice": "en"}}),
        encoding="utf-8",
    )


class VoiceBundleTests(unittest.TestCase):
    def test_complete_user_model_pair_wins_for_that_accent(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            user = root / "user"
            resources = root / "resources"
            write_voice(user / "voices" / "uk", "en_GB")
            write_voice(resources / "speech" / "voices" / "uk", "en_GB")
            self.assertEqual(choose_voice_folder(user, resources, 1), user / "voices" / "uk")

    def test_missing_or_invalid_user_config_falls_back_to_bundled_pair(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            user = root / "user"
            resources = root / "resources"
            partial = user / "voices" / "us"
            partial.mkdir(parents=True)
            (partial / "dictionary-voice.onnx").write_bytes(b"partial")
            write_voice(resources / "speech" / "voices" / "us", "en_US")
            self.assertEqual(choose_voice_folder(user, resources, 2), resources / "speech" / "voices" / "us")

    def test_legacy_complete_user_voice_remains_a_valid_override(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            user = root / "user"
            resources = root / "resources"
            write_voice(user / "voices" / "uk", "en_GB", "voice")
            write_voice(resources / "speech" / "voices" / "uk", "en_GB")
            self.assertEqual(choose_voice_folder(user, resources, 1), user / "voices" / "uk")

    def test_runtime_resolution_does_not_depend_on_voice_folder(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            user = root / "user"
            resources = root / "resources"
            (user / "voices" / "uk").mkdir(parents=True)
            runtime = resources / "speech" / "runtime" / "piper"
            runtime.mkdir(parents=True)
            (runtime / "piper.exe").write_bytes(b"runtime")
            self.assertEqual(choose_runtime_dir(user, resources), runtime)

    def test_temp_audio_path_is_under_user_cache_not_installed_runtime(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            cache = Path(temp) / "QingCi" / "speech-cache"
            path = cache_output_path(cache, "water|uk")
            self.assertTrue(path.parent.is_dir())
            self.assertEqual(path.parent, cache)
            self.assertNotIn("runtime", path.parts)
            path.write_bytes(b"temporary wave")
            self.assertTrue(path.is_file())

    def test_bundle_audit_allows_only_pinned_assets_and_rejects_private_files(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP_ROOT) as temp:
            root = Path(temp)
            voice = root / "speech" / "voices" / "uk"
            voice.mkdir(parents=True)
            files = []
            for name, payload in (
                ("dictionary-voice.onnx", b"model"),
                ("dictionary-voice.onnx.json", b'{"language":{"code":"en_GB"}}'),
                ("dictionary-MODEL_CARD.txt", b"card"),
            ):
                path = voice / name
                path.write_bytes(payload)
                files.append(
                    {
                        "name": name,
                        "bytes": len(payload),
                        "sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
            lock = {"models": [{"accent": "uk", "files": files}]}
            runtime_file = root / "speech" / "runtime" / "piper" / "piper.exe"
            runtime_file.parent.mkdir(parents=True)
            runtime_file.write_bytes(b"runtime")
            runtime = {
                "files": [
                    {
                        "path": "speech/runtime/piper/piper.exe",
                        "bytes": runtime_file.stat().st_size,
                        "sha256": hashlib.sha256(runtime_file.read_bytes()).hexdigest(),
                    }
                ]
            }
            self.assertEqual(audit_bundle(root, lock, runtime)["files"], 4)
            (root / "private.pdf").write_bytes(b"private")
            with self.assertRaisesRegex(ValueError, "Bundle tree mismatch"):
                audit_bundle(root, lock, runtime)


if __name__ == "__main__":
    unittest.main()
