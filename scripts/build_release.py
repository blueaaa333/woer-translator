"""Build only on the target OS. No personal data or optional speech binaries."""
import argparse,json,os,platform,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.collect_runtime_licenses import collect

def command(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)

def build(skip_installer=False):
    version=(ROOT/'VERSION').read_text().strip()
    if sys.platform not in ('win32','darwin'):raise RuntimeError('Build on Windows or macOS')
    target='Windows' if sys.platform=='win32' else 'macOS'
    arch='arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64'
    out=ROOT/'release-assets';out.mkdir(exist_ok=True)
    stage=ROOT/'build'/'release-resources';stage.mkdir(parents=True,exist_ok=True)
    versions=collect(stage/'runtime-licenses')
    (stage/'build-info.json').write_text(json.dumps(dict(version=version,platform=target,arch=arch,runtime=versions),indent=2),encoding='utf-8')
    if sys.platform=='win32':command('powershell','-NoProfile','-File','build_bridge.ps1')
    from PIL import Image
    icon=ROOT/'assets'/'沃尔翻译官.ico'
    if sys.platform=='darwin':
        icon=stage/'WoerTranslator.icns';Image.open(ROOT/'assets'/'沃尔翻译官.png').convert('RGBA').resize((1024,1024)).save(icon)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--name','WoerTranslator','--icon',str(icon),'--collect-all','opencc']
    for name in ('words.db','extended.db','community.db','compound_entries.json','assets','licenses','LICENSE','SOURCES.md','THIRD_PARTY_NOTICES.md','VERSION'):
        path=ROOT/name
        if not path.exists():raise RuntimeError('Missing resource: '+name)
        args+=['--add-data',f'{path}{os.pathsep}.']
    # Directory resources need their own destination name.
    for directory in ('assets','licenses'):
        index=args.index(f'{ROOT/directory}{os.pathsep}.');args[index]=f'{ROOT/directory}{os.pathsep}{directory}'
    args+=['--add-data',f'{stage/"runtime-licenses"}{os.pathsep}licenses/runtime','--add-data',f'{stage/"build-info.json"}{os.pathsep}.',
           '--add-data',f'{ROOT/"docs"/"MAC_FIRST_RUN.html"}{os.pathsep}docs',
           '--add-data',f'{ROOT/"scripts"/"speech-downloads.json"}{os.pathsep}scripts','--hidden-import','scripts.setup_speech',
           '--hidden-import','scripts.check_runtime']
    if sys.platform=='win32':args+=['--manifest',str(ROOT/'QingCi.manifest'),'--add-binary',f'{ROOT/"DesktopBridge.exe"}{os.pathsep}.']
    else:args+=['--osx-bundle-identifier','io.github.blueaaa333.woer-translator','--hidden-import','mac_platform','--hidden-import','ApplicationServices','--hidden-import','Quartz','--hidden-import','AppKit']
    args+=[str(ROOT/'app.py')];command(*args)
    executable=ROOT/'dist'/'WoerTranslator'/'WoerTranslator.exe' if sys.platform=='win32' else ROOT/'dist'/'WoerTranslator.app'/'Contents'/'MacOS'/'WoerTranslator'
    report=stage/'smoke-report.json';command(executable,'--smoke-test','--smoke-report',report)
    assert json.loads(report.read_text(encoding='utf-8'))['dictionaries']=='ok'
    shutil.copy2(report,out/f'WoerTranslator-{version}-{target}-{arch}-checks.json')
    if sys.platform=='darwin':
        runtime_report=stage/'runtime-report.json'
        subprocess.run([str(executable),'--gui-self-test','--gui-report',str(runtime_report)],cwd=ROOT,check=True,timeout=40)
        runtime=json.loads(runtime_report.read_text(encoding='utf-8'))
        if 'error' in runtime:raise RuntimeError('Frozen macOS UI check failed: '+str(runtime))
        shutil.copy2(runtime_report,out/f'WoerTranslator-{version}-{target}-{arch}-runtime.json')
    if sys.platform=='win32':
        shutil.make_archive(str(out/f'WoerTranslator-{version}-Windows-x64-Portable'),'zip',ROOT/'dist','WoerTranslator')
        if not skip_installer:
            compiler=Path(os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Inno Setup 6'/'ISCC.exe'
            if not compiler.exists():raise RuntimeError('Install Inno Setup 6 from its official source first')
            command(compiler,f'/DAppVersion={version}',ROOT/'packaging'/'windows.iss')
    else:
        app=ROOT/'dist'/'WoerTranslator.app'
        # A local ad-hoc signature is not a Developer ID signature or notarization.
        command('/usr/bin/codesign','--force','--deep','--sign','-',app)
        command('/usr/bin/codesign','--verify','--deep','--strict',app)
        dmg_stage=ROOT/'build'/'dmg';dmg_stage.mkdir(exist_ok=True)
        shutil.copytree(app,dmg_stage/'WoerTranslator.app',dirs_exist_ok=True)
        shutil.copy2(ROOT/'docs'/'MAC_FIRST_RUN.html',dmg_stage/'Mac首次运行指南.html')
        shutil.copy2(ROOT/'docs'/'mac-first-run-poster.png',dmg_stage/'Mac首次运行海报.png')
        # GitHub normalizes release asset filenames; keep them ASCII so the
        # published names match SHA256SUMS. In-DMG labels remain Chinese.
        shutil.copy2(ROOT/'docs'/'MAC_FIRST_RUN.html',out/f'WoerTranslator-{version}-Mac.html')
        shutil.copy2(ROOT/'docs'/'mac-first-run-poster.png',out/f'WoerTranslator-{version}-Mac.png')
        link=dmg_stage/'Applications'
        if not link.exists():link.symlink_to('/Applications')
        command('/usr/bin/hdiutil','create','-volname','Woer Translator','-srcfolder',dmg_stage,'-ov','-format','UDZO',out/f'WoerTranslator-{version}-macOS-{arch}.dmg')
        command('/usr/bin/productbuild','--component',app,'/Applications','--identifier','io.github.blueaaa333.woer-translator','--version',version,out/f'WoerTranslator-{version}-macOS-{arch}.pkg')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--skip-installer',action='store_true')
    build(parser.parse_args().skip_installer)
