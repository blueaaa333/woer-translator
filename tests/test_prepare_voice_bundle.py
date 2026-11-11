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
            cards.append({"accent": accent, "revision": "fixed-revision", "bytes": files[-1]["bytes"],
                          "sha256": files[-1]["sha256"], "card_text": (accent + " card")})
        lock = {"schema": 1, "models": models_lock}
        lock_path = root / "voice_runtime_lock.json"
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        readme = "---\nlicense: mit\n---\nPinned fixture README"
        mit_text = "MIT text with placeholders"
        license_report = {
            "revision_requested": "fixed-revision",
            "revision_returned": "fixed-revision",
            "repo_license_metadata": "mit",
            "repo_license_text": {"text": readme, "sha256": hashlib.sha256(readme.encode()).hexdigest()},
            "standard_mit_terms": {"text": mit_text, "sha256": hashlib.sha256(mit_text.encode()).hexdigest()},
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
            self.assertFalse(result["crt"]["bundled"])
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

    def test_msvc_crt_is_rejected_from_runtime_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime, models, lock, license_report = self.inputs(root)
            crt = runtime / "speech" / "runtime" / "piper" / "VCRUNTIME140.dll"
            runtime_item = put(crt, b"runner crt fixture")
            runtime_item["path"] = "speech/runtime/piper/VCRUNTIME140.dll"
            manifest_path = runtime / "runtime-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"].append(runtime_item)
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "MSVC CRT must come from"):
                prepare(runtime, models, license_report, root / "package", lock_path=lock)

    def test_unlisted_msvc_crt_is_rejected_from_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime, models, lock, license_report = self.inputs(root)
            output = root / "package"
            prepare(runtime, models, license_report, output, lock_path=lock)
            crt = output / "speech" / "runtime" / "piper" / "MSVCP140.dll"
            crt.write_bytes(b"unlisted runner crt fixture")
            with self.assertRaisesRegex(ValueError, "MSVC CRT must not be bundled"):
                audit_embedded_voice_payload(output)


if __name__ == "__main__":
    unittest.main()

