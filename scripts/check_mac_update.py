"""Install the actual DMG into an isolated CI folder, then run the replaced app."""
import hashlib
import json
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import updater


def run(artifact):
    root = Path(__file__).resolve().parents[1]
    test_root = root/'build'/('update-e2e-'+str(time.time_ns()))
    test_root.mkdir(parents=True)
    target = test_root/'WoerTranslator.app'
    shutil.copytree(root/'dist'/'WoerTranslator.app', target, symlinks=True)
    info_path = target/'Contents'/'Info.plist'
    with info_path.open('rb') as stream:info = plistlib.load(stream)
    info['CFBundleShortVersionString'] = '0.2.2'
    with info_path.open('wb') as stream:plistlib.dump(info, stream)
    (target/'Contents'/'Resources'/'old-only.txt').write_text('previous version marker')
    subprocess.run(['/usr/bin/codesign', '--force', '--deep', '--sign', '-', str(target)], check=True)
    artifact = Path(artifact).resolve()
    version = (root/'VERSION').read_text().strip()
    with artifact.open('rb') as stream:digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    release = updater.Release(version, artifact.name, 'unused-in-local-test', digest, artifact.stat().st_size, '')
    old_process = subprocess.Popen(['/bin/sleep', '120'])
    try:
        folder = updater.prepare_mac(release, artifact, test_root/'state', target, test_root, old_process.pid)
        assert (target/'Contents'/'Resources'/'old-only.txt').is_file(), 'replaced before old process exited'
        old_process.terminate();old_process.wait(timeout=5)
        deadline = time.monotonic()+45
        while time.monotonic() < deadline:
            if (folder/'gui.json').exists():
                gui = json.loads((folder/'gui.json').read_text())
                assert 'error' not in gui, gui
                result = json.loads((folder/'result.json').read_text())
                assert result['installed'] and result['version'] == version
                assert not (target/'Contents'/'Resources'/'old-only.txt').exists()
                assert (Path(result['backup'])/'Contents'/'Resources'/'old-only.txt').is_file()
                updater.validate_bundle(target, version)
                report = dict(platform=sys.platform, update='ok', actual_dmg=True, staged_replace='ok',
                              backup_preserved=True, restarted_gui=gui)
                (root/'release-assets'/(artifact.stem+'-update-test.json')).write_text(json.dumps(report, indent=2))
                print(json.dumps(report));return
            time.sleep(.25)
        raise RuntimeError('Replaced Mac app did not finish its startup check')
    finally:
        if old_process.poll() is None:old_process.terminate();old_process.wait(timeout=5)


if __name__ == '__main__':
    run(sys.argv[1])
