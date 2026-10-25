"""Publish a small CDN-friendly feed after installers and Packages succeed."""
import base64
import json
import subprocess
import sys

REPO = 'blueaaa333/woer-translator'


def main(version):
    release = json.loads(subprocess.check_output(['gh', 'api', f'repos/{REPO}/releases/tags/v{version}']))
    names = {f'WoerTranslator-{version}-Windows-x64-Setup.exe',
             f'WoerTranslator-{version}-macOS-arm64.dmg', f'WoerTranslator-{version}-macOS-x64.dmg'}
    feed = {key:release[key] for key in ('tag_name', 'draft', 'prerelease', 'body')}
    feed['assets'] = [{key:a[key] for key in ('name', 'browser_download_url', 'digest', 'size')}
                      for a in release['assets'] if a['name'] in names]
    assert {a['name'] for a in feed['assets']} == names
    assert all(a['digest'].startswith('sha256:') for a in feed['assets'])
    payload = dict(message=f'Publish update feed for v{version} [skip ci]',
                   content=base64.b64encode(json.dumps(feed, ensure_ascii=False, indent=2).encode()).decode(), branch='main')
    response = subprocess.run(['gh', 'api', f'repos/{REPO}/contents/updates/latest.json'], capture_output=True)
    if response.returncode == 0:
        payload['sha'] = json.loads(response.stdout)['sha']
    elif b'404' not in response.stderr:
        raise RuntimeError('Cannot read current update feed')
    subprocess.run(['gh', 'api', '--method', 'PUT', f'repos/{REPO}/contents/updates/latest.json', '--input', '-'],
                   input=json.dumps(payload).encode(), check=True, stdout=subprocess.DEVNULL)
    print('Published update feed for v'+version)


if __name__ == '__main__':
    main(sys.argv[1])
