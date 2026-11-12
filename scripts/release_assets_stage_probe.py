"""Exercise v0.3.23 release staging with runner-only installer placeholders.

The Windows package evidence and corresponding source archive are taken from a
completed Windows CI artifact. The three installer files staged here are
explicit test placeholders; this script never publishes or uploads them.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import release_assets  # noqa: E402

WINDOWS_RUN_ID = 43156159232
WINDOWS_ARTIFACT_ID = 13915839072
WINDOWS_INSTALLER_BYTES = 233327472
WINDOWS_INSTALLER_SHA256 = "8bc772bcacbcf7cac30acbbe183bc96853253741cac747f1e18ac789d6b031a0"
SOURCE_ARCHIVE_BYTES = 110678332
SOURCE_ARCHIVE_SHA256 = "83ebe3e5d2895af4b06a5f3e426dcb849c85c8f963baa71119961db0df8e100f"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_files(root):
    for path in Path(root).rglob("*.json"):
        try:
            yield path, json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue


def source_archive_records(value):
    if isinstance(value, dict):
        if (value.get("file") == "piper-runtime-source.zip"
                and isinstance(value.get("bytes"), int)
                and isinstance(value.get("sha256"), str)):
            yield value
        for child in value.values():
            yield from source_archive_records(child)
    elif isinstance(value, list):
        for child in value:
            yield from source_archive_records(child)


def run(version, artifact_root, output_root, run_id, artifact_id):
    if run_id != WINDOWS_RUN_ID or artifact_id != WINDOWS_ARTIFACT_ID:
        raise RuntimeError("This probe is bound to the reviewed Windows run and artifact IDs")
    tag = "v" + version
    expected_windows_name = f"WoerTranslator-{version}-Windows-x64-Setup.exe"
    source_name = release_assets.source_archive(tag)
    reports = list(json_files(artifact_root))
    package_reports = [
        (path, data) for path, data in reports
        if isinstance(data, dict)
        and data.get("candidate_installer", {}).get("path", "").replace("\\", "/").endswith(expected_windows_name)
        and data.get("passed") is True
        and data.get("first_install", {}).get("passed") is True
        and data.get("upgrade", {}).get("passed") is True
    ]
    if len(package_reports) != 1:
        raise RuntimeError(f"Expected one passing Windows package report; found {len(package_reports)}")
    package_report_path, package_report = package_reports[0]
    real_windows = package_report["candidate_installer"]
    if (real_windows.get("bytes", 0) <= 0
            or not isinstance(real_windows.get("sha256"), str)
            or len(real_windows["sha256"]) != 64):
        raise RuntimeError("Windows package report has no valid size or SHA-256")
    if (real_windows["bytes"] != WINDOWS_INSTALLER_BYTES
            or real_windows["sha256"] != WINDOWS_INSTALLER_SHA256):
        raise RuntimeError("Windows package report differs from the reviewed candidate evidence")

    source_reports = []
    for path, data in reports:
        source_reports.extend((path, info) for info in source_archive_records(data))
    unique_source_reports = {}
    for path, info in source_reports:
        key = (info["bytes"], info["sha256"])
        unique_source_reports.setdefault(key, (path, info))
    if len(unique_source_reports) == 1:
        source_report_path, source_info = next(iter(unique_source_reports.values()))
        source_evidence = "downloaded build JSON report"
    elif not unique_source_reports:
        # The Windows job printed this same-build summary, but its artifact
        # allowlist intentionally uploaded only review JSON plus the source ZIP.
        source_report_path = "Windows probe run 43156159232 console summary"
        source_info = {
            "file": "piper-runtime-source.zip",
            "bytes": SOURCE_ARCHIVE_BYTES,
            "sha256": SOURCE_ARCHIVE_SHA256,
        }
        source_evidence = "same-build Windows probe console summary"
    else:
        raise RuntimeError(f"Expected one consistent source-archive report; found {len(unique_source_reports)}")
    archives = list(Path(artifact_root).rglob("piper-runtime-source.zip"))
    if len(archives) != 1:
        raise RuntimeError(f"Expected one corresponding-source ZIP; found {len(archives)}")
    archive = archives[0]
    archive_sha = sha256(archive)
    if archive.stat().st_size != source_info["bytes"] or archive_sha != source_info["sha256"]:
        raise RuntimeError("Downloaded source ZIP differs from the same-build report")
    if archive.stat().st_size != SOURCE_ARCHIVE_BYTES or archive_sha != SOURCE_ARCHIVE_SHA256:
        raise RuntimeError("Downloaded ZIP differs from the source archive locked to this artifact ID")

    if Path(output_root).exists():
        raise RuntimeError("Refusing to mix an existing staging-probe directory")
    root = Path(output_root)
    assets = root / "release-assets"
    public = root / "public-release"
    assets.mkdir(parents=True)
    staged_source = assets / source_name
    shutil.copyfile(archive, staged_source)
    report_name = release_assets.source_report(tag)
    report_info = dict(source_info)
    report_info.update(file="piper-runtime-source.zip", release_asset=source_name)
    (assets / report_name).write_text(json.dumps({
        "version": version,
        "runtime_source_archive": report_info,
        "probe_evidence": {"run_id": run_id, "source_report": str(source_report_path),
                           "artifact_id": artifact_id, "source_evidence": source_evidence,
                           "stage_input_is_runner_only_fixture": True},
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    placeholder_names = release_assets.installers(tag)
    for name in placeholder_names:
        (assets / name).write_text(
            f"TEST PLACEHOLDER ONLY; not an installer and must not be published.\n{name}\n",
            encoding="utf-8",
        )
    release_assets.stage(version, assets, public, ROOT / "docs" / "RELEASE_NOTES.md")

    expected_names = set(release_assets.payload_names(tag)) | {"SHA256SUMS.txt"}
    actual_names = {path.name for path in public.iterdir() if path.is_file()}
    if actual_names != expected_names:
        raise RuntimeError(f"Unexpected staged payload set: {sorted(actual_names)}")
    checksums = {}
    for line in (public / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        checksums[name] = digest
    if set(checksums) != set(release_assets.payload_names(tag)):
        raise RuntimeError("SHA256SUMS does not enumerate exactly the four release payloads")
    if checksums[source_name] != archive_sha:
        raise RuntimeError("Staged source checksum differs from the downloaded CI archive")
    notes = (root / "release-notes.md").read_text(encoding="utf-8")
    source_url = f"https://github.com/{release_assets.REPO}/releases/download/{tag}/{source_name}"
    if source_url not in notes:
        raise RuntimeError("Staged release notes do not link the version-matched source ZIP")

    feed_path = ROOT / "scripts" / "publish_update_feed.py"
    feed_tree = ast.parse(feed_path.read_text(encoding="utf-8"), filename=str(feed_path))
    feed_text = feed_path.read_text(encoding="utf-8")
    if "piper-runtime-source" in feed_text:
        raise RuntimeError("Update-feed publisher unexpectedly includes the source archive")
    feed_names = release_assets.installers(tag)
    if len(feed_names) != 3 or source_name in feed_names:
        raise RuntimeError("Update-feed payload set must remain the three installers")
    if not any(isinstance(node, ast.FunctionDef) and node.name == "main" for node in feed_tree.body):
        raise RuntimeError("Could not verify the existing update-feed publisher")
    if release_assets.payload_names("v0.3.22") != release_assets.installers("v0.3.22"):
        raise RuntimeError("Legacy v0.3.22 three-installer layout is not preserved")

    report = {
        "passed": True,
        "purpose": "runner-only staging-format fixture; no publishing performed",
        "windows_evidence_run_id": run_id,
        "windows_report_file": package_report_path.name,
        "real_windows_installer": real_windows,
        "first_install_passed": package_report["first_install"]["passed"],
        "upgrade_passed": package_report["upgrade"]["passed"],
        "source_report_file": source_report_path.name if isinstance(source_report_path, Path) else None,
        "source_report_evidence": source_evidence,
        "source_archive": {"name": source_name, "bytes": archive.stat().st_size, "sha256": archive_sha},
        "staged_payload_names": sorted(expected_names),
        "placeholder_installer_names": sorted(placeholder_names),
        "installer_placeholders_are_not_real_packages": True,
        "checksum_payload_count": len(checksums),
        "source_link_present": True,
        "update_feed_installer_count": len(feed_names),
        "legacy_v0_3_22_layout_preserved": True,
    }
    root.mkdir(parents=True, exist_ok=True)
    (root / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default="0.3.23")
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", type=int, default=WINDOWS_RUN_ID)
    parser.add_argument("--artifact-id", type=int, default=WINDOWS_ARTIFACT_ID)
    args = parser.parse_args()
    run(args.version, args.artifact_root, args.output_root, args.run_id, args.artifact_id)
