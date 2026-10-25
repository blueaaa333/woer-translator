import hashlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import updater


def fixture(data=b'installer', version='9.9.9'):
    name = updater.asset_name(version)
    return updater.Release(version, name, f'https://github.com/{updater.REPO}/releases/download/v{version}/{name}',
                           hashlib.sha256(data).hexdigest(), len(data), 'Fixes')


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status, self.headers = status, headers or {}


class UpdaterTests(unittest.TestCase):
    def metadata(self, release):
        return dict(tag_name='v'+release.version, body=release.notes, assets=[dict(name=release.name,
                    browser_download_url=release.url, digest='sha256:'+release.sha256, size=release.size)])

    def test_versions_platform_and_no_downgrade(self):
        self.assertGreater(updater.version_tuple('1.10.0'), updater.version_tuple('1.9.9'))
        self.assertTrue(updater.asset_name('1.0.0', 'darwin', 'arm64').endswith('arm64.dmg'))
        self.assertTrue(updater.asset_name('1.0.0', 'darwin', 'x86_64').endswith('x64.dmg'))
        release = fixture()
        self.assertIsNone(updater.parse_release(self.metadata(release), '9.9.9'))
        self.assertIsNone(updater.parse_release(self.metadata(release), '10.0.0'))
        self.assertEqual(updater.parse_release(self.metadata(release), '0.2.2'), release)

    def test_rejects_foreign_downloads_bad_hash_and_prereleases(self):
        for change in ('url', 'hash', 'size', 'tag', 'draft', 'prerelease'):
            metadata = self.metadata(fixture())
            asset = metadata['assets'][0]
            if change == 'url': asset['browser_download_url'] = 'https://elsewhere.test/installer'
            elif change == 'hash': asset['digest'] = None
            elif change == 'size': asset['size'] = 10**12
            elif change == 'tag': metadata['tag_name'] = 'v../../1.0.0'
            else: metadata[change] = True
            with self.subTest(change=change), self.assertRaises(updater.UpdateError):
                updater.parse_release(metadata, '0.2.2')

    def test_resumes_partial_download_then_verifies_hash(self):
        data = b'a real installer'
        release = fixture(data)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)/release.version
            folder.mkdir()
            (folder/(release.name+'.part')).write_bytes(data[:3])
            def request(req, timeout):
                self.assertEqual(req.get_header('Range'), 'bytes=3-')
                return Response(data[3:], 206, {'Content-Range':f'bytes 3-{len(data)-1}/{len(data)}'})
            path = updater.download(release, temporary, request=request)
            self.assertEqual(path.read_bytes(), data)
            self.assertFalse(path.with_name(path.name+'.part').exists())

    def test_bad_checksum_is_never_saved_as_installer(self):
        release = fixture(b'correct')
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(updater.UpdateError, '校验失败'):
                updater.download(release, temporary, request=lambda *a, **k:Response(b'incorre'))
            self.assertFalse((Path(temporary)/release.version/release.name).exists())

    def test_complete_part_does_not_request_an_invalid_range(self):
        data = b'complete'
        release = fixture(data)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)/release.version
            folder.mkdir()
            (folder/(release.name+'.part')).write_bytes(data)
            path = updater.download(release, temporary, request=lambda *a, **k:self.fail('network not needed'))
            self.assertTrue(updater.verified(path, release))

    def test_download_cancellation_preserves_partial_file(self):
        release = fixture()
        stop = threading.Event(); stop.set()
        with tempfile.TemporaryDirectory() as temporary, self.assertRaisesRegex(updater.UpdateError, '暂停'):
            updater.download(release, temporary, cancelled=stop)

    def test_bundle_replace_rolls_back_if_second_rename_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target, stage, backup = root/'WoerTranslator.app', root/'stage.app', root/'backup.app'
            target.mkdir();stage.mkdir()
            (target/'old').write_text('user installed app')
            original = Path.rename
            def rename(path, to):
                if path == stage:raise OSError('simulated replace failure')
                return original(path, to)
            with patch.object(Path, 'rename', rename), self.assertRaises(OSError):
                updater.replace_bundle(stage, target, backup)
            self.assertTrue((target/'old').is_file())
            self.assertFalse(backup.exists())

    def test_target_must_be_the_installed_app_and_not_a_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root/'WoerTranslator.app';target.mkdir()
            self.assertEqual(updater.validate_target(target, root), target)
            with self.assertRaises(updater.UpdateError):updater.validate_target(target)
            with self.assertRaises(updater.UpdateError):updater.validate_target(root/'Other.app', root)

    def test_windows_installer_does_not_launch_bad_download(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)/'bad.exe';path.write_bytes(b'bad')
            with patch('updater.subprocess.Popen') as launch, self.assertRaises(updater.UpdateError):
                updater.install_windows(fixture(), path)
            launch.assert_not_called()

    def test_rejects_https_downgrade_redirect(self):
        import urllib.request
        with self.assertRaises(updater.UpdateError):
            updater.HTTPSRedirect().redirect_request(urllib.request.Request('https://github.com'), None,
                                                    302, '', {}, 'http://example.test/app')


if __name__ == '__main__':
    unittest.main()
