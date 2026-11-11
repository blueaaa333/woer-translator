import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.verify_piper_source_archive import verify


def make_zip(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return output.getvalue()


def digest(data):
    return hashlib.sha256(data).hexdigest()


class SourceArchiveTests(unittest.TestCase):
    def make_fixture(self, nested_weight=False):
        names = ["piper", "piper-phonemize", "espeak-ng", "onnxruntime", "fmt", "spdlog"]
        sources = []
        records = []
        outer_files = {
            name: b"fixture\n"
            for name in (
                "voice_runtime_lock.json",
                "build_piper_runtime.ps1",
                "archive_piper_sources.ps1",
                "verify_piper_source_archive.py",
                "README-runtime-source.md",
            )
        }

        def archive_record(path, repository, commit, prefix, children=(), links=(), files=None):
            data = make_zip(files or {"src/readme.txt": b"pinned source\n"})
            archive_name = f"sources/{prefix}.zip"
            outer_files[archive_name] = data
            notice = f"notices/{prefix}/LICENSE"
            outer_files[notice] = b"MIT\n"
            return {
                "path": path,
                "repository": repository,
                "commit": commit,
                "gitlinks": list(links),
                "archive": archive_name,
                "bytes": len(data),
                "sha256": digest(data),
                "notices": [notice],
                "submodules": list(children),
            }

        benchmark_pin = {
            "path": "third_party/benchmark",
            "repository": "https://github.com/google/benchmark.git",
            "commit": "b" * 40,
        }
        pybind_pin = {
            "path": "third_party/pybind11",
            "repository": "https://github.com/pybind/pybind11.git",
            "commit": "c" * 40,
        }
        onnx_pin = {
            "path": "cmake/external/onnx",
            "repository": "https://github.com/onnx/onnx.git",
            "commit": "a" * 40,
            "submodules": [benchmark_pin, pybind_pin],
        }
        benchmark_record = archive_record(
            benchmark_pin["path"], benchmark_pin["repository"], benchmark_pin["commit"],
            "onnxruntime__benchmark",
        )
        pybind_files = {"src/readme.txt": b"pinned source\n"}
        if nested_weight:
            pybind_files["assets/example.onnx"] = b"forbidden\n"
        pybind_record = archive_record(
            pybind_pin["path"], pybind_pin["repository"], pybind_pin["commit"],
            "onnxruntime__pybind11", files=pybind_files,
        )
        onnx_record = archive_record(
            onnx_pin["path"], onnx_pin["repository"], onnx_pin["commit"],
            "onnxruntime__onnx",
            children=[benchmark_record, pybind_record],
            links=[
                {"path": benchmark_pin["path"], "repository": benchmark_pin["repository"], "commit": benchmark_pin["commit"]},
                {"path": pybind_pin["path"], "repository": pybind_pin["repository"], "commit": pybind_pin["commit"]},
            ],
        )

        for index, name in enumerate(names):
            commit = f"{index + 1:040x}"
            pin = {
                "name": name,
                "repository": f"https://example.invalid/{name}.git",
                "commit": commit,
                "submodules": [onnx_pin] if name == "onnxruntime" else [],
            }
            sources.append(pin)
            children = [onnx_record] if name == "onnxruntime" else []
            links = [
                {"path": onnx_pin["path"], "repository": onnx_pin["repository"], "commit": onnx_pin["commit"]}
            ] if name == "onnxruntime" else []
            record = archive_record(name, pin["repository"], commit, name, children=children, links=links)
            record["name"] = name
            if name == "onnxruntime":
                for leaf in ("LICENSE", "ThirdPartyNotices.txt"):
                    path = f"notices/onnxruntime/{leaf}"
                    outer_files[path] = b"ORT notice\n"
                    record["notices"].append(path)
            records.append(record)

        manifest = {"schema": 1, "sources": records}
        outer_files["source-manifest.json"] = json.dumps(manifest).encode("utf-8")
        lock = {"runtime": {"sources": sources}}

        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        bundle_path = root / "bundle.zip"
        lock_path = root / "lock.json"
        with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as bundle:
            for path, data in outer_files.items():
                bundle.writestr(path, data)
        lock_path.write_text(json.dumps(lock), encoding="utf-8")
        return temporary, bundle_path, lock_path

    def test_verifies_recursive_pins_archives_and_notices(self):
        temporary, archive_path, lock_path = self.make_fixture()
        with temporary:
            report = verify(archive_path, lock_path)
        ort = next(item for item in report["verified_sources"] if item["path"] == "onnxruntime")
        self.assertEqual(len(ort["submodules"]), 1)
        self.assertEqual(len(ort["submodules"][0]["submodules"]), 2)
        self.assertFalse(report["weights_included"])

    def test_rejects_model_weights_in_deep_source_archive(self):
        temporary, archive_path, lock_path = self.make_fixture(nested_weight=True)
        with temporary, self.assertRaisesRegex(ValueError, "model weights"):
            verify(archive_path, lock_path)


if __name__ == "__main__":
    unittest.main()
