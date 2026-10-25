"""Official-release updates. Networking and installation never run in the Tk thread."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import urllib.error
import urllib.parse
import uuid
import ssl
import certifi

REPO = 'blueaaa333/woer-translator'
BUNDLE_ID = 'io.github.blueaaa333.woer-translator'
LATEST = f'https://raw.githubusercontent.com/{REPO}/main/updates/latest.json'
API_LATEST = f'https://api.github.com/repos/{REPO}/releases/latest'
MAX_INSTALLER = 400 * 1024 * 1024


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value), encoding='utf-8')
    temporary.replace(path)


class UpdateError(RuntimeError):
    pass


def version_tuple(text):
    if not re.fullmatch(r'(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)', text):
        raise UpdateError('更新版本号无效')
    return tuple(map(int, text.split('.')))


def asset_name(version, system=None, machine=None):
    version_tuple(version)
    system = system or sys.platform
    machine = (machine or platform.machine()).lower()
    if system == 'win32' and machine in ('amd64', 'x86_64', 'x64'):
        return f'WoerTranslator-{version}-Windows-x64-Setup.exe'
    if system == 'darwin' and machine in ('arm64', 'aarch64', 'x86_64', 'amd64', 'x64'):
        arch = 'arm64' if machine in ('arm64', 'aarch64') else 'x64'
        return f'WoerTranslator-{version}-macOS-{arch}.dmg'
    raise UpdateError('此平台暂不支持软件内更新，请查看发行页面')


@dataclass(frozen=True)
class Release:
    version: str
    name: str
    url: str
    sha256: str
    size: int
    notes: str

    @property
    def page(self):
        return f'https://github.com/{REPO}/releases/tag/v{self.version}'


def parse_release(data, current, system=None, machine=None):
    version_tuple(current)
    tag = data.get('tag_name', '')
    if data.get('draft') or data.get('prerelease') or not tag.startswith('v'):
        raise UpdateError('没有可用的正式更新')
    version = tag[1:]
    if version_tuple(version) <= version_tuple(current):
        return None
    name = asset_name(version, system, machine)
    assets = [a for a in data.get('assets', []) if a.get('name') == name]
    if len(assets) != 1:
        raise UpdateError('新版本的对应安装包尚未准备完成，请稍后重试')
    asset = assets[0]
    url = f'https://github.com/{REPO}/releases/download/{tag}/{name}'
    digest = asset.get('digest') or ''
    size = asset.get('size')
    if asset.get('browser_download_url') != url or not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise UpdateError('更新来源或校验信息不完整，已停止更新')
    if type(size) is not int or not 0 < size <= MAX_INSTALLER:
        raise UpdateError('安装包大小无效')
    return Release(version, name, url, digest[7:], size, str(data.get('body') or '')[:4000])


class HTTPSRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != 'https':
            raise UpdateError('更新连接必须使用 HTTPS')
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def open_url(request, timeout=15):
    context = ssl.create_default_context()
    context.load_verify_locations(certifi.where())
    return urllib.request.build_opener(HTTPSRedirect(), urllib.request.HTTPSHandler(context=context)).open(request, timeout=timeout)


def check(current, system=None, machine=None, request=open_url):
    headers = {'Accept': 'application/json', 'User-Agent': 'WoerTranslator-Updater/' + current}
    try:
        response = request(urllib.request.Request(LATEST, headers=headers), timeout=12)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        response = request(urllib.request.Request(API_LATEST, headers=headers), timeout=12)
    with response:
        data = response.read(1024 * 1024 + 1)
    if len(data) > 1024 * 1024:
        raise UpdateError('更新信息过大')
    return parse_release(json.loads(data), current, system, machine)


def verified(path, release):
    if not path.is_file() or path.stat().st_size != release.size:
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() == release.sha256


def download(release, cache, progress=lambda done, total: None, request=open_url, cancelled=None):
    # Revalidate the immutable descriptor before using it for a filesystem path.
    if release.name != asset_name(release.version):
        raise UpdateError('安装包与当前平台不匹配')
    expected_url = f'https://github.com/{REPO}/releases/download/v{release.version}/{release.name}'
    if release.url != expected_url or not re.fullmatch(r'[a-f0-9]{64}', release.sha256):
        raise UpdateError('更新来源或校验信息无效')
    if type(release.size) is not int or not 0 < release.size <= MAX_INSTALLER:
        raise UpdateError('安装包大小无效')
    folder = Path(cache) / release.version
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / release.name
    part = folder / (release.name + '.part')
    if verified(target, release):
        return target
    for attempt in range(3):
        if cancelled and cancelled.is_set():
            raise UpdateError('已暂停下载，下次可以继续')
        start = part.stat().st_size if part.exists() else 0
        if start == release.size and verified(part, release):
            part.replace(target)
            return target
        if start > release.size:
            part.unlink()
            start = 0
        try:
            headers = {'User-Agent': 'WoerTranslator-Updater'}
            if start:
                headers['Range'] = f'bytes={start}-'
            with request(urllib.request.Request(release.url, headers=headers), timeout=15) as response:
                partial = response.status == 206
                if partial and not response.headers.get('Content-Range', '').startswith(f'bytes {start}-'):
                    raise UpdateError('续传响应不匹配')
                if not partial:
                    start = 0
                with part.open('ab' if partial else 'wb') as output:
                    done = start
                    while True:
                        if cancelled and cancelled.is_set():
                            raise UpdateError('已暂停下载，下次可以继续')
                        block = response.read(256 * 1024)
                        if not block:
                            break
                        done += len(block)
                        if done > release.size:
                            raise UpdateError('下载大小与发行记录不符')
                        output.write(block)
                        progress(done, release.size)
            if not verified(part, release):
                if part.stat().st_size == release.size:
                    part.unlink()
                    raise UpdateError('安装包 SHA-256 校验失败，已删除无效下载')
                raise OSError('Incomplete download')
            part.replace(target)
            return target
        except UpdateError:
            raise
        except (OSError, urllib.error.URLError):
            if attempt == 2:
                raise UpdateError('网络中断，下载进度已保留，请点“继续下载”重试') from None
            time.sleep(.5 * (attempt + 1))


def bundle_path(executable=None):
    path = Path(executable or sys.executable).resolve()
    app = path.parents[2]
    if app.name != 'WoerTranslator.app' or path.relative_to(app).parts != ('Contents', 'MacOS', 'WoerTranslator'):
        raise UpdateError('请先将 App 拖入 Applications，再从“应用程序”中打开并更新')
    return app


def validate_bundle(app, expected_version=None):
    with (app / 'Contents/Info.plist').open('rb') as stream:
        info = plistlib.load(stream)
    if info.get('CFBundleIdentifier') != BUNDLE_ID or info.get('CFBundleExecutable') != 'WoerTranslator':
        raise UpdateError('安装包中的应用标识不匹配')
    if expected_version and info.get('CFBundleShortVersionString') != expected_version:
        raise UpdateError('安装包中的应用版本不匹配')
    subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(app)],
                   check=True, timeout=45, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def validate_target(target, test_root=None):
    target = Path(target).absolute()
    allowed = {Path('/Applications'), Path.home() / 'Applications'}
    if test_root is not None:
        allowed = {Path(test_root).resolve()}
    if target.name != 'WoerTranslator.app' or target.is_symlink() or target.parent.resolve() not in allowed:
        raise UpdateError('请先将 App 安装到“应用程序”，再使用软件内更新')
    if not target.is_dir() or not os.access(target.parent, os.W_OK):
        raise UpdateError('当前账户无法更新此安装位置，请由管理员安装新版本')
    return target


def replace_bundle(stage, target, backup):
    if stage.parent != target.parent or backup.parent != target.parent or backup.exists():
        raise UpdateError('更新暂存路径无效')
    target.rename(backup)
    try:
        stage.rename(target)
    except Exception:
        backup.rename(target)
        raise


def prepare_mac(release, artifact, cache, target=None, test_root=None, parent_pid=None):
    if not verified(artifact, release):
        raise UpdateError('安装包校验未通过')
    target = validate_target(target or bundle_path(), test_root)
    validate_bundle(target)
    folder = Path(cache) / ('install-' + uuid.uuid4().hex)
    folder.mkdir(parents=True)
    mount = folder / 'mount'
    mount.mkdir()
    plan = folder / 'plan.json'
    ready = folder / 'ready.json'
    subprocess.run(['/usr/bin/hdiutil', 'attach', '-readonly', '-nobrowse', '-noautoopen',
                    '-mountpoint', str(mount), str(artifact)], check=True, timeout=60,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    source = mount / 'WoerTranslator.app'
    try:
        validate_bundle(source, release.version)
        values = dict(target=str(target), mount=str(mount), version=release.version,
                      parent_pid=parent_pid or os.getpid(), ready=str(ready))
        if test_root:
            values['test_root'] = str(Path(test_root).resolve())
        write_json(plan, values)
        flags = ['--apply-mac-update', str(plan)]
        if test_root:
            flags.append('--update-self-test')
        process = subprocess.Popen([str(source / 'Contents/MacOS/WoerTranslator'), *flags],
                                   env=dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT='1'),
                                   stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, start_new_session=True)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if ready.exists():
                result = json.loads(ready.read_text(encoding='utf-8'))
                if result.get('error'):
                    raise UpdateError(result['error'])
                return folder
            if process.poll() is not None:
                raise UpdateError('安装助手未能启动，当前版本仍保留')
            time.sleep(.1)
        process.terminate()
        raise UpdateError('安装准备超时，当前版本仍保留')
    except Exception:
        subprocess.run(['/usr/bin/hdiutil', 'detach', str(mount)], timeout=15,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raise


def apply_mac(plan_path):
    plan_path = Path(plan_path).resolve()
    values = json.loads(plan_path.read_text(encoding='utf-8'))
    ready = plan_path.parent / 'ready.json'
    test_root = values.get('test_root') if '--update-self-test' in sys.argv else None
    target = validate_target(values['target'], test_root)
    mount = plan_path.parent / 'mount'
    source = bundle_path()
    if source.parent != mount or values['mount'] != str(mount):
        raise UpdateError('更新来源路径不匹配')
    version_tuple(values['version'])
    stage = target.parent / ('.WoerTranslator-update-' + uuid.uuid4().hex + '.app')
    backup = target.parent / ('.WoerTranslator-previous-' + uuid.uuid4().hex + '.app')
    try:
        validate_bundle(source, values['version'])
        subprocess.run(['/usr/bin/ditto', '--rsrc', '--extattr', str(source), str(stage)], check=True, timeout=90)
        validate_bundle(stage, values['version'])
        write_json(ready, dict(ready=True))
        deadline = time.monotonic() + 45
        while True:
            try:
                os.kill(int(values['parent_pid']), 0)
            except ProcessLookupError:
                break
            if time.monotonic() > deadline:
                raise UpdateError('旧版尚未退出，已取消替换')
            time.sleep(.1)
        replace_bundle(stage, target, backup)
        result = dict(installed=True, version=values['version'], target=str(target), backup=str(backup))
        write_json(plan_path.parent / 'result.json', result)
        command = ['/usr/bin/open', '-n', str(target)]
        if test_root:
            command += ['--args', '--gui-self-test', '--gui-report', str(plan_path.parent / 'gui.json')]
        subprocess.run(command, check=True, timeout=15)
    except Exception as exc:
        write_json(ready, dict(error=str(exc)))
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        # The helper runs from this disk image; detach after this process exits.
        subprocess.Popen(['/bin/sh', '-c', 'sleep 2; /usr/bin/hdiutil detach "$1" >/dev/null 2>&1',
                          'woer-update-cleanup', str(mount)], start_new_session=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cleanup_previous(cache, current):
    if sys.platform != 'darwin' or not getattr(sys, 'frozen', False):
        return
    target = bundle_path()
    for path in Path(cache).glob('install-*/result.json'):
        values = json.loads(path.read_text(encoding='utf-8'))
        backup = Path(values['backup'])
        if (values.get('version') == current and values.get('target') == str(target)
                and backup.parent == target.parent and re.fullmatch(r'\.WoerTranslator-previous-[a-f0-9]{32}\.app', backup.name)
                and not backup.is_symlink() and backup.is_dir()):
            shutil.rmtree(backup)


def install_windows(release, artifact):
    if not verified(artifact, release):
        raise UpdateError('安装包校验未通过')
    # Explicit user action, standard installer, no force-closing other apps or reboot.
    return subprocess.Popen([str(artifact), '/SILENT', '/SP-', '/NORESTART',
                             '/NOFORCECLOSEAPPLICATIONS', '/WOERUPDATE=1'])
