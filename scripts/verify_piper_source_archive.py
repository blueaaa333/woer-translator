"""Verify the pinned Piper source archive against the checked-in lock."""
import argparse
import hashlib
import io
import json
import zipfile
from pathlib import PurePosixPath


WEIGHT_SUFFIXES = {".onnx", ".ort"}
REQUIRED_BUNDLE_FILES = {
    "voice_runtime_lock.json",
    "build_piper_runtime.ps1",
    "archive_piper_sources.ps1",
    "verify_piper_source_archive.py",
    "README-runtime-source.md",
    "source-manifest.json",
}


def _sha256(data):
    return hashlib.sha256(data).hexdigest()


def _safe_name(name):
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def verify(archive_path, lock_path):
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    expected = {item["name"]: item for item in lock["runtime"]["sources"]}
    if len(expected) != 6:
        raise ValueError(f"Expected six pinned sources, found {len(expected)}")

    with zipfile.ZipFile(archive_path) as bundle:
        names = {name for name in bundle.namelist() if not name.endswith("/")}
        unsafe = sorted(name for name in names if not _safe_name(name))
        if unsafe:
            raise ValueError(f"Unsafe archive paths: {unsafe}")
        missing = sorted(REQUIRED_BUNDLE_FILES - names)
        if missing:
            raise ValueError(f"Missing source bundle files: {missing}")
        weight_files = sorted(name for name in names if PurePosixPath(name).suffix.lower() in WEIGHT_SUFFIXES)
        if weight_files:
            raise ValueError(f"Model weights are forbidden in artifacts: {weight_files[:20]}")

        manifest = json.loads(bundle.read("source-manifest.json"))
        records = {item["name"]: item for item in manifest.get("sources", [])}
        if set(records) != set(expected):
            raise ValueError(f"Source set mismatch: expected={sorted(expected)} actual={sorted(records)}")

        checked = []
        for name, dependency in expected.items():
            record = records[name]
            if record.get("repository") != dependency["repository"] or record.get("commit") != dependency["commit"]:
                raise ValueError(f"Lock mismatch for {name}")
            if record.get("gitlinks") != []:
                raise ValueError(f"Unpinned gitlinks recorded for {name}")
            archive_name = record.get("archive", "")
            if archive_name not in names:
                raise ValueError(f"Missing source archive for {name}: {archive_name}")
            data = bundle.read(archive_name)
            if len(data) != record.get("bytes") or _sha256(data) != record.get("sha256"):
                raise ValueError(f"Source archive hash mismatch: {name}")
            with zipfile.ZipFile(io.BytesIO(data)) as source:
                source_names = {item for item in source.namelist() if not item.endswith("/")}
            if not source_names:
                raise ValueError(f"Empty source archive: {name}")
            source_weights = sorted(
                item for item in source_names if PurePosixPath(item).suffix.lower() in WEIGHT_SUFFIXES
            )
            if source_weights:
                raise ValueError(f"Source archive contains model weights ({name}): {source_weights[:20]}")

            notices = record.get("notices", [])
            if not notices or any(notice not in names for notice in notices):
                raise ValueError(f"Missing license/notice files for {name}")
            if name == "onnxruntime":
                required = {"notices/onnxruntime/LICENSE", "notices/onnxruntime/ThirdPartyNotices.txt"}
                if not required.issubset(names):
                    raise ValueError("ORT license and third-party notices are required")
            checked.append({"name": name, "commit": dependency["commit"], "archive_sha256": record["sha256"]})

    return {"verified_sources": checked, "weights_included": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--lock", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.archive, args.lock), sort_keys=True))


if __name__ == "__main__":
    main()
