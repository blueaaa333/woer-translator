import importlib.util
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


if __name__ == "__main__":
    unittest.main()
