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
    return not path.is_absolute() and ".." not in path.parts and "\\" not in name


def _unique_by_path(items, label):
    result = {}
    for item in items:
        path = item.get("path")
        if not path or path in result:
            raise ValueError(f"Duplicate or missing path in {label}: {path!r}")
        result[path] = item
    return result


def _verify_source_node(bundle, names, record, pin, label, require_ort_notices=False):
    if record.get("repository") != pin["repository"] or record.get("commit") != pin["commit"]:
        raise ValueError(f"Lock mismatch for {label}")

    expected_children = _unique_by_path(pin.get("submodules", []), f"lock submodules {label}")
    recorded_gitlinks = _unique_by_path(record.get("gitlinks", []), f"manifest gitlinks {label}")
    recorded_children = _unique_by_path(record.get("submodules", []), f"manifest submodules {label}")
    expected_gitlinks = {
        path: {"repository": child["repository"], "commit": child["commit"]}
        for path, child in expected_children.items()
    }
    actual_gitlinks = {
        path: {"repository": link.get("repository"), "commit": link.get("commit")}
        for path, link in recorded_gitlinks.items()
    }
    if actual_gitlinks != expected_gitlinks:
        raise ValueError(f"Gitlink pin mismatch for {label}")
    if set(recorded_children) != set(expected_children):
        raise ValueError(f"Nested source set mismatch for {label}")

    archive_name = record.get("archive", "")
    if archive_name not in names:
        raise ValueError(f"Missing source archive for {label}: {archive_name}")
    data = bundle.read(archive_name)
    if len(data) != record.get("bytes") or _sha256(data) != record.get("sha256"):
        raise ValueError(f"Source archive hash mismatch: {label}")
    with zipfile.ZipFile(io.BytesIO(data)) as source:
        source_names = {item for item in source.namelist() if not item.endswith("/")}
        unsafe_source_names = sorted(item for item in source_names if not _safe_name(item))
    if unsafe_source_names:
        raise ValueError(f"Unsafe paths in source archive ({label}): {unsafe_source_names[:20]}")
    if not source_names:
        raise ValueError(f"Empty source archive: {label}")
    source_weights = sorted(
        item for item in source_names if PurePosixPath(item).suffix.lower() in WEIGHT_SUFFIXES
    )
    if source_weights:
        raise ValueError(f"Source archive contains model weights ({label}): {source_weights[:20]}")

    notices = record.get("notices", [])
    if not notices or any(notice not in names for notice in notices):
        raise ValueError(f"Missing license/notice files for {label}")
    if require_ort_notices:
        required = {"notices/onnxruntime/LICENSE", "notices/onnxruntime/ThirdPartyNotices.txt"}
        if not required.issubset(names):
            raise ValueError("ORT license and third-party notices are required")

    checked_children = []
    for path, child_pin in expected_children.items():
        child_record = recorded_children[path]
        child_summary = _verify_source_node(
            bundle,
            names,
            child_record,
            child_pin,
            f"{label}/{path}",
        )
        checked_children.append(child_summary)

    return {
        "path": label,
        "commit": pin["commit"],
        "archive_sha256": record["sha256"],
        "submodules": checked_children,
    }


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

        manifest = json.loads(bundle.read("source-manifest.json").decode("utf-8-sig"))
        manifest_sources = manifest.get("sources", [])
        records = {item["name"]: item for item in manifest_sources}
        if len(records) != len(manifest_sources):
            raise ValueError("Duplicate source names in source manifest")
        if set(records) != set(expected):
            raise ValueError(f"Source set mismatch: expected={sorted(expected)} actual={sorted(records)}")

        checked = []
        for name, dependency in expected.items():
            record = records[name]
            checked.append(_verify_source_node(
                bundle,
                names,
                record,
                dependency,
                name,
                require_ort_notices=(name == "onnxruntime"),
            ))

    return {"verified_sources": checked, "weights_included": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True)
    parser.add_argument("--lock", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.archive, args.lock), sort_keys=True))


if __name__ == "__main__":
    main()
