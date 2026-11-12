import importlib.util
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("release_assets", Path(__file__).resolve().parents[1] / "scripts/release_assets.py")
release_assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_assets)


class ReleaseAssetTests(unittest.TestCase):
    def release(self):
        return {"tag_name": "v0.2.1", "assets": [
            {"name": name, "digest": "sha256:" + "a" * 64}
            for name in release_assets.installers("v0.2.1") + [
                "SHA256SUMS.txt", "WoerTranslator-0.2.1-Windows-x64-Portable.zip",
                "blueaaa333-woer-translator-0.2.1.tgz"]]}

    def test_removes_only_known_auxiliary_files(self):
        removed = release_assets.plan(self.release(), "v0.2.1")
        self.assertEqual(len(removed), 2)
        self.assertTrue(all(a["name"].endswith((".zip", ".tgz")) for a in removed))

    def test_refuses_missing_installer_unknown_asset_and_changed_tag(self):
        for change in ("missing", "unknown", "tag", "digest", "immutable"):
            data = self.release()
            if change == "missing": data["assets"].pop(0)
            elif change == "unknown": data["assets"].append({"name": "important-user-file.txt"})
            elif change == "tag": data["tag_name"] = "v0.2.0"
            elif change == "digest": data["assets"][0]["digest"] = None
            else: data["immutable"] = True
            with self.subTest(change=change), self.assertRaises(ValueError):
                release_assets.plan(data, "v0.2.1")

    def test_checksums_keep_launcher_contract(self):
        text = release_assets.checksums(self.release(), "v0.2.1")
        self.assertEqual(len(text.splitlines()), 3)
        self.assertEqual({line[66:] for line in text.splitlines()}, set(release_assets.installers("v0.2.1")))

    def test_download_links_preserve_signing_notes_and_are_idempotent(self):
        body = "功能说明\n\n### 下载选择\n\nPortable.zip / checks.json\n\n### 签名与许可\n\n尚未签名和公证。\n"
        notes = release_assets.release_notes(body, "v0.2.1")
        self.assertEqual(notes, release_assets.release_notes(notes, "v0.2.1"))
        self.assertEqual(notes.count("/releases/download/v0.2.1/WoerTranslator-"), 3)
        self.assertNotIn("Portable.zip", notes)
        self.assertIn("尚未签名和公证。", notes)
        self.assertLess(notes.index("下载 Windows 安装包"), notes.index("功能说明"))

    def test_future_staging_excludes_build_reports_and_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "release-assets"
            source.mkdir()
            for name in release_assets.installers("v0.2.1") + ["checks.json", "launcher.tgz"]:
                (source / name).write_bytes(name.encode())
            notes = root / "notes.md"
            notes.write_text("Release details", encoding="utf-8")
            target = root / "public-release"
            release_assets.stage("0.2.1", source, target, notes)
            self.assertEqual({p.name for p in target.iterdir()}, set(release_assets.installers("v0.2.1")) | {"SHA256SUMS.txt"})
            self.assertIn("下载 Mac Intel 版", (root / "release-notes.md").read_text(encoding="utf-8"))
            with self.assertRaises(ValueError):
                release_assets.stage("0.2.1", source, target, notes)

    def voice_release(self):
        tag = "v0.3.23"
        names = release_assets.payload_names(tag) + ["SHA256SUMS.txt"]
        return {"tag_name": tag, "assets": [
            {"name": name, "digest": "sha256:" + "b" * 64, "size": 1}
            for name in names]}

    def write_voice_source(self, source, version="0.3.23", payload=b"pinned source"):
        archive = source / release_assets.source_archive("v" + version)
        archive.write_bytes(payload)
        report = {
            "version": version,
            "runtime_source_archive": {
                "file": "piper-runtime-source.zip",
                "release_asset": release_assets.source_archive("v" + version),
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            },
        }
        (source / release_assets.source_report("v" + version)).write_text(
            json.dumps(report), encoding="utf-8")
        return archive

    def test_v02323_requires_source_and_checksums_cover_four_payloads(self):
        data = self.voice_release()
        self.assertEqual(len(release_assets.plan(data, "v0.3.23")), 0)
        self.assertEqual(len(release_assets.checksums(data, "v0.3.23").splitlines()), 4)
        missing = dict(data, assets=[a for a in data["assets"]
                                     if a["name"] != release_assets.source_archive("v0.3.23")])
        with self.assertRaises(ValueError):
            release_assets.plan(missing, "v0.3.23")
        unknown = dict(data, assets=data["assets"] + [{"name": "extra.zip", "digest": "sha256:" + "c" * 64}])
        with self.assertRaises(ValueError):
            release_assets.plan(unknown, "v0.3.23")

    def test_legacy_four_asset_release_remains_valid(self):
        data = {"tag_name": "v0.3.22", "assets": [
            {"name": name, "digest": "sha256:" + "d" * 64}
            for name in release_assets.installers("v0.3.22") + ["SHA256SUMS.txt"]]}
        self.assertEqual(release_assets.plan(data, "v0.3.22"), [])
        self.assertEqual(len(release_assets.checksums(data, "v0.3.22").splitlines()), 3)

    def test_v02323_stage_publishes_source_and_fails_closed_on_bad_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "release-assets"
            source.mkdir()
            for name in release_assets.installers("v0.3.23"):
                (source / name).write_bytes(name.encode())
            archive = self.write_voice_source(source)
            notes = root / "notes.md"
            notes.write_text("Windows bundled speech", encoding="utf-8")
            target = root / "public-release"
            release_assets.stage("0.3.23", source, target, notes)
            self.assertEqual({p.name for p in target.iterdir()},
                             set(release_assets.payload_names("v0.3.23")) | {"SHA256SUMS.txt"})
            self.assertEqual(len((target / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()), 4)
            notes_text = (root / "release-notes.md").read_text(encoding="utf-8")
            self.assertIn(release_assets.source_archive("v0.3.23"), notes_text)

            bad = root / "bad-assets"
            bad.mkdir()
            for name in release_assets.installers("v0.3.23"):
                (bad / name).write_bytes(name.encode())
            bad_archive = self.write_voice_source(bad, payload=b"different")
            report_path = bad / release_assets.source_report("v0.3.23")
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["runtime_source_archive"]["sha256"] = "0" * 64
            report_path.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaises(ValueError):
                release_assets.stage("0.3.23", bad, root / "bad-public", notes)
            self.assertFalse((root / "bad-public").exists())


if __name__ == "__main__":
    unittest.main()

