"""Assemble and audit the Windows-only voice payload used by the probe package."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

CRT_NAMES = ("VCRUNTIME140.dll", "VCRUNTIME140_1.dll", "MSVCP140.dll")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _copy_text(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def verify_speech_tree(root: Path, lock: dict, runtime_manifest: dict) -> dict:
    """Check the exact speech/ payload by locked path, byte count, and SHA-256."""
    root = Path(root)
    expected: dict[str, tuple[int, str]] = {}
    revisions = {model["revision"] for model in lock["models"]}
    if len(revisions) != 1:
        raise ValueError("Voice models do not share one pinned revision")
    for model in lock["models"]:
        for item in model["files"]:
            rel = Path("speech") / "voices" / model["accent"] / item["name"]
            expected[rel.as_posix()] = (item["bytes"], item["sha256"])
    for item in runtime_manifest["files"]:
        rel = Path(item["path"])
        if rel.is_absolute() or ".." in rel.parts or rel.as_posix() in expected:
            raise ValueError(f"Invalid or duplicate runtime path: {item['path']}")
        expected[rel.as_posix()] = (item["bytes"], item["sha256"])

    speech = root / "speech"
    actual = {
        (Path("speech") / path.relative_to(speech)).as_posix(): path
        for path in speech.rglob("*")
        if path.is_file()
    }
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing or extra:
        raise ValueError(f"Speech payload tree mismatch; missing={missing}; extra={extra}")
    for rel, (size, expected_hash) in expected.items():
        path = actual[rel]
        if path.stat().st_size != size:
            raise ValueError(f"Byte count mismatch: {rel}")
        if sha256(path) != expected_hash:
            raise ValueError(f"SHA-256 mismatch: {rel}")
    return {"files": len(expected), "paths": sorted(expected)}


def _copy_license_evidence(report_path: Path, destination: Path) -> dict:
    report_bytes = Path(report_path).read_bytes()
    review = json.loads(report_bytes.decode("utf-8"))
    if review.get("repo_license_metadata", "").lower() != "mit":
        raise ValueError("Pinned piper-voices root README does not declare MIT")
    if review.get("revision_requested") != review.get("revision_returned"):
        raise ValueError("Pinned model-license revision did not resolve exactly")
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "model-license-review.json").write_bytes(report_bytes)
    readme = review.get("repo_license_text")
    mit = review.get("standard_mit_terms")
    if not readme or not mit or not mit.get("text"):
        raise ValueError("Pinned README or standard MIT text is missing")
    (destination / "piper-voices-README.md").write_bytes(readme["text"].encode("utf-8"))
    (destination / "MIT-LICENSE-TEMPLATE.txt").write_bytes(mit["text"].encode("utf-8"))
    files_dir = destination / "repository-license-files"
    for item in review.get("license_files", []):
        if item.get("status") != "read" or not item.get("text"):
            raise ValueError("A listed model repository license file could not be read")
        name = Path(item["path"]).name
        if name in ("", ".", ".."):
            raise ValueError("Invalid model repository license filename")
        files_dir.mkdir(parents=True, exist_ok=True)
        (files_dir / name).write_bytes(item["text"].encode("utf-8"))
    cards = review.get("models", [])
    if len(cards) != 2 or any(not item.get("card_text") for item in cards):
        raise ValueError("Both pinned model-card texts are required")
    cards_dir = destination / "model-cards"
    cards_dir.mkdir(parents=True, exist_ok=True)
    for item in cards:
        (cards_dir / f"{item['accent']}-MODEL_CARD.txt").write_bytes(item["card_text"].encode("utf-8"))
    return {
        "review_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "readme_sha256": readme["sha256"],
        "mit_text_sha256": mit["sha256"],
        "model_cards": {item["accent"]: item["sha256"] for item in cards},
        "revision": review["revision_requested"],
        "license": review["repo_license_metadata"],
        "copyright_notice_finding": review.get("copyright_notice_finding"),
    }


def prepare(runtime_root: Path, model_root: Path, license_report: Path,
            output_root: Path, crt_source: Path | None = None,
            crt_eula: Path | None = None, lock_path: Path | None = None) -> dict:
    runtime_root = Path(runtime_root).resolve()
    model_root = Path(model_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root.exists() and any(output_root.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty voice stage: {output_root}")
    output_root.mkdir(parents=True, exist_ok=True)
    speech = output_root / "speech"
    shutil.copytree(runtime_root / "speech" / "runtime", speech / "runtime", dirs_exist_ok=True)
    shutil.copytree(model_root / "speech" / "voices", speech / "voices", dirs_exist_ok=True)

    license_root = output_root / "licenses" / "speech"
    license_root.mkdir(parents=True, exist_ok=True)
    lock_path = Path(lock_path) if lock_path else Path(__file__).with_name("voice_runtime_lock.json")
    runtime_manifest_path = runtime_root / "runtime-manifest.json"
    source_archive = runtime_root / "piper-runtime-source.zip"
    source_manifest = runtime_root / "source-manifest.json"
    for source in (lock_path, runtime_manifest_path, source_archive, source_manifest):
        if not source.is_file():
            raise FileNotFoundError(f"Missing pinned runtime/source evidence: {source}")
    shutil.copy2(lock_path, license_root / "voice_runtime_lock.json")
    runtime_manifest = json.loads(runtime_manifest_path.read_text(encoding="utf-8-sig"))
    crt_records = []
    if crt_source is not None:
        crt_source = Path(crt_source)
        runtime_dir = speech / "runtime" / "piper"
        for name in CRT_NAMES:
            source = crt_source / name
            if not source.is_file():
                raise FileNotFoundError(f"Runner CRT probe source lacks required DLL: {source}")
            target = runtime_dir / name
            shutil.copy2(source, target)
            record = {"name": name, "path": f"speech/runtime/piper/{name}",
                      "bytes": target.stat().st_size, "sha256": sha256(target),
                      "source": str(source)}
            crt_records.append(record)
            runtime_manifest["files"].append({
                "path": record["path"], "bytes": record["bytes"], "sha256": record["sha256"]
            })
        if crt_eula is not None:
            crt_dir = license_root / "msvc-crt-test-only"
            crt_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(crt_eula, crt_dir / "Microsoft-VC-Runtime-EULA.docx")
    (license_root / "runtime-manifest.json").write_text(
        json.dumps(runtime_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    shutil.copy2(source_archive, license_root / source_archive.name)
    shutil.copy2(source_manifest, license_root / source_manifest.name)
    notices = runtime_root / "licenses"
    if notices.is_dir():
        shutil.copytree(notices, license_root / "runtime-notices", dirs_exist_ok=True)
    license_summary = _copy_license_evidence(Path(license_report), license_root / "model-license")
    package_summary = verify_speech_tree(output_root, json.loads(lock_path.read_text(encoding="utf-8")), runtime_manifest)
    summary = {
        "schema": 1,
        "model_revision": license_summary["revision"],
        "model_license": license_summary["license"],
        "model_license_evidence": license_summary,
        "speech_payload": package_summary,
        "runtime_source_archive": {
            "file": source_archive.name, "bytes": source_archive.stat().st_size,
            "sha256": sha256(license_root / source_archive.name),
        },
        "source_manifest_sha256": sha256(license_root / source_manifest.name),
        "crt": {"test_only": bool(crt_records), "files": crt_records,
                "redistribution_rights": "not established by this package probe"},
    }
    (license_root / "package-manifest.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def audit_embedded_voice_payload(base: Path) -> dict | None:
    base = Path(base)
    speech = base / "speech"
    license_root = base / "licenses" / "speech"
    lock_path = license_root / "voice_runtime_lock.json"
    runtime_path = license_root / "runtime-manifest.json"
    if not speech.exists() and not lock_path.exists() and not runtime_path.exists():
        return None
    if not speech.is_dir() or not lock_path.is_file() or not runtime_path.is_file():
        raise RuntimeError("Incomplete preinstalled speech resources or manifests")
    package_manifest_path = license_root / "package-manifest.json"
    source_archive = license_root / "piper-runtime-source.zip"
    source_manifest = license_root / "source-manifest.json"
    model_review = license_root / "model-license/model-license-review.json"
    required = (package_manifest_path, source_archive, source_manifest, model_review,
                license_root / "model-license/piper-voices-README.md",
                license_root / "model-license/MIT-LICENSE-TEMPLATE.txt")
    missing = [str(path.relative_to(base)) for path in required if not path.is_file()]
    if missing:
        raise RuntimeError("Missing speech source/license evidence: " + ", ".join(missing))
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    runtime_manifest = json.loads(runtime_path.read_text(encoding="utf-8"))
    package = json.loads(package_manifest_path.read_text(encoding="utf-8"))
    if package.get("model_revision") != lock["models"][0]["revision"]:
        raise RuntimeError("Voice package manifest revision mismatch")
    if sha256(source_archive) != package["runtime_source_archive"]["sha256"]:
        raise RuntimeError("Piper corresponding-source archive hash mismatch")
    if sha256(source_manifest) != package["source_manifest_sha256"]:
        raise RuntimeError("Piper source-manifest hash mismatch")
    review = json.loads(model_review.read_text(encoding="utf-8"))
    if review.get("revision_requested") != package["model_revision"] or review.get("repo_license_metadata", "").lower() != "mit":
        raise RuntimeError("Pinned model-license evidence does not match the voice payload")
    if hashlib.sha256(model_review.read_bytes()).hexdigest() != package["model_license_evidence"]["review_sha256"]:
        raise RuntimeError("Model-license evidence hash mismatch")
    model_license = license_root / "model-license"
    if sha256(model_license / "piper-voices-README.md") != package["model_license_evidence"]["readme_sha256"]:
        raise RuntimeError("Pinned model repository README hash mismatch")
    if sha256(model_license / "MIT-LICENSE-TEMPLATE.txt") != package["model_license_evidence"]["mit_text_sha256"]:
        raise RuntimeError("MIT terms text hash mismatch")
    result = verify_speech_tree(base, lock, runtime_manifest)
    if result["files"] != package["speech_payload"]["files"]:
        raise RuntimeError("Speech payload file count differs from package manifest")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--license-report", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--crt-source", type=Path)
    parser.add_argument("--crt-eula", type=Path)
    parser.add_argument("--lock", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    summary = prepare(args.runtime_root, args.model_root, args.license_report,
                      args.output_root, args.crt_source, args.crt_eula, args.lock)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"passed": True, "summary": summary}, sort_keys=True))


if __name__ == "__main__":
    main()

