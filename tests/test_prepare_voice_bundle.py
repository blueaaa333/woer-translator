import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.prepare_voice_bundle import audit_embedded_voice_payload, prepare, sha256


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return {"name": path.name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


class PrepareVoiceBundleTests(unittest.TestCase):
    def inputs(self, root):
        runtime = root / "runtime"
        models = root / "models"
        runtime_file = runtime / "speech" / "runtime" / "piper" / "piper.exe"
        runtime_item = put(runtime_file, b"test-runtime")
        runtime_item["path"] = "speech/runtime/piper/piper.exe"
        (runtime / "runtime-manifest.json").write_text(
            json.dumps({"files": [runtime_item], "profile": "fixture"}), encoding="utf-8"
        )
        (runtime / "piper-runtime-source.zip").write_bytes(b"locked source archive fixture")
        (runtime / "source-manifest.json").write_text(json.dumps({"projects": []}), encoding="utf-8")
        (runtime / "licenses" / "PIPER-LICENSE.txt").parent.mkdir(parents=True, exist_ok=True)
        (runtime / "licenses" / "PIPER-LICENSE.txt").write_text("MIT notice", encoding="utf-8")

        models_lock = []
        cards = []
        for accent, language in (("uk", "en_GB"), ("us", "en_US")):
            voice_dir = models / "speech" / "voices" / accent
            config = json.dumps({"language": {"code": language}}).encode()
            files = [
                put(voice_dir / "dictionary-voice.onnx", (accent + " weights").encode()),
                put(voice_dir / "dictionary-voice.onnx.json", config),
                put(voice_dir / "dictionary-MODEL_CARD.txt", (accent + " card").encode()),
            ]
            models_lock.append({"accent": accent, "revision": "fixed-revision", "files": files})
            cards.append({"accent": accent, "sha256": files[-1]["sha256"], "card_text": (accent + " card")})
        lock = {"schema": 1, "models": models_lock}
        lock_path = root / "voice_runtime_lock.json"
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        readme = "---\nlicense: mit\n---\nPinned fixture README"
        license_report = {
            "revision_requested": "fixed-revision",
            "revision_returned": "fixed-revision",
            "repo_license_metadata": "mit",
            "repo_license_text": {"text": readme, "sha256": hashlib.sha256(readme.encode()).hexdigest()},
            "standard_mit_terms": {"text": "MIT text with placeholders", "sha256": "fixture-mit-hash"},
            "license_files": [], "models": cards,
            "copyright_notice_finding": "No owner or year inferred.",
        }
        license_report_path = root / "license-report.json"
        license_report_path.write_text(json.dumps(license_report), encoding="utf-8")
        return runtime, models, lock_path, license_report_path

    def test_prepare_and_audit_exact_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime, models, lock, license_report = self.inputs(root)
            output = root / "package"
            result = prepare(runtime, models, license_report, output, lock_path=lock)
            self.assertEqual(result["speech_payload"]["files"], 7)
            self.assertFalse(result["crt"]["test_only"])
            self.assertEqual(audit_embedded_voice_payload(output)["files"], 7)

    def test_extra_or_modified_voice_file_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime, models, lock, license_report = self.inputs(root)
            output = root / "package"
            prepare(runtime, models, license_report, output, lock_path=lock)
            extra = output / "speech" / "voices" / "uk" / "unlocked.onnx"
            extra.write_bytes(b"unlocked")
            with self.assertRaisesRegex(ValueError, "extra=.*unlocked.onnx"):
                audit_embedded_voice_payload(output)

    def test_runner_crt_is_explicitly_test_only_and_hash_locked(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime, models, lock, license_report = self.inputs(root)
            crt = root / "runner-redist"
            names = ("VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll")
            for name in names:
                put(crt / name, (name + " fixture").encode())
            output = root / "package"
            result = prepare(runtime, models, license_report, output, crt_source=crt, lock_path=lock)
            self.assertTrue(result["crt"]["test_only"])
            self.assertEqual(len(result["crt"]["files"]), 3)
            self.assertEqual(audit_embedded_voice_payload(output)["files"], 10)
            for item in result["crt"]["files"]:
                self.assertEqual(item["sha256"], sha256(output / "speech" / "runtime" / "piper" / item["name"]))


if __name__ == "__main__":
    unittest.main()

