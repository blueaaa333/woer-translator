"""Build only on the target OS. No personal data or optional speech binaries."""
import argparse,json,os,platform,shutil,subprocess,sys,plistlib,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.collect_runtime_licenses import collect

def command(*args):subprocess.run([str(x) for x in args],cwd=ROOT,check=True)

def build(skip_installer=False, skip_portable=False, voice_bundle_root=None, minimum_msvc_runtime_version=None):
    version=(ROOT/'VERSION').read_text().strip()
    if sys.platform not in ('win32','darwin'):raise RuntimeError('Build on Windows or macOS')
    target='Windows' if sys.platform=='win32' else 'macOS'
    arch='arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64'
    out=ROOT/'release-assets';out.mkdir(exist_ok=True)
    stage=ROOT/'build'/'release-resources';stage.mkdir(parents=True,exist_ok=True)
    versions=collect(stage/'runtime-licenses')
    (stage/'build-info.json').write_text(json.dumps(dict(version=version,platform=target,arch=arch,runtime=versions),indent=2),encoding='utf-8')
    voice_bundle_stage=None
    voice_license_stage=None
    if voice_bundle_root is not None:
        if sys.platform!='win32':raise RuntimeError('Preinstalled Piper resources are Windows-only')
        from scripts.prepare_voice_bundle import audit_embedded_voice_payload
        bundle_root=Path(voice_bundle_root).resolve()
        voice_report=audit_embedded_voice_payload(bundle_root)
        if not voice_report:raise RuntimeError('Incomplete locked voice bundle')
        package_manifest=json.loads((bundle_root/'licenses'/'speech'/'package-manifest.json').read_text(encoding='utf-8'))
        if package_manifest.get('crt',{}).get('bundled') is not False:
            raise RuntimeError('Voice package must not bundle Microsoft CRT DLLs')
        if not minimum_msvc_runtime_version:
            raise RuntimeError('Voice package build requires a minimum MSVC runtime version from the actual toolchain')
        voice_bundle_stage=stage/'speech'
        voice_license_stage=stage/'speech-licenses'
        if voice_bundle_stage.exists():shutil.rmtree(voice_bundle_stage)
        if voice_license_stage.exists():shutil.rmtree(voice_license_stage)
        shutil.copytree(bundle_root/'speech',voice_bundle_stage)
        shutil.copytree(bundle_root/'licenses'/'speech',voice_license_stage)
        (stage/'speech-bundle-build-report.json').write_text(
            json.dumps(voice_report,indent=2,sort_keys=True)+'\\n',encoding='utf-8')
    if sys.platform=='win32':
        if voice_bundle_stage is not None:
            dist_tree=ROOT/'dist'/'WoerTranslator'
            if dist_tree.exists():
                resolved=dist_tree.resolve()
                if resolved.parent!=(ROOT/'dist').resolve():raise RuntimeError('Refusing to remove unexpected frozen app tree')
                shutil.rmtree(dist_tree)
        command('powershell','-NoProfile','-File','build_bridge.ps1')
    from PIL import Image
    icon=ROOT/'assets'/'沃尔翻译官.ico'
    if sys.platform=='darwin':
        icon=stage/'WoerTranslator.icns';Image.open(ROOT/'assets'/'沃尔翻译官.png').convert('RGBA').resize((1024,1024)).save(icon)
    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed','--name','WoerTranslator','--icon',str(icon),'--collect-all','opencc','--exclude-module','numpy','--hidden-import','_cffi_backend']
    for name in ('words.db','extended.db','community.db','compound_entries.json','assets','licenses','LICENSE','SOURCES.md','THIRD_PARTY_NOTICES.md','VERSION'):
        path=ROOT/name
        if not path.exists():raise RuntimeError('Missing resource: '+name)
        args+=['--add-data',f'{path}{os.pathsep}.']
    ecdict_manifest=ROOT/'build'/'ecdict'/'manifest.json'
    if not ecdict_manifest.is_file():raise RuntimeError('Missing verified ECDICT build manifest')
    packaged_manifest=stage/'ecdict-manifest.json'
    shutil.copy2(ecdict_manifest,packaged_manifest)
    args+=['--add-data',f'{packaged_manifest}{os.pathsep}.']
    # Directory resources need their own destination name.
    for directory in ('assets','licenses'):
        index=args.index(f'{ROOT/directory}{os.pathsep}.');args[index]=f'{ROOT/directory}{os.pathsep}{directory}'
    args+=['--add-data',f'{stage/"runtime-licenses"}{os.pathsep}licenses/runtime','--add-data',f'{stage/"build-info.json"}{os.pathsep}.',
           '--add-data',f'{ROOT/"docs"/"MAC_FIRST_RUN.html"}{os.pathsep}docs',
           '--add-data',f'{ROOT/"scripts"/"speech-downloads.json"}{os.pathsep}scripts','--hidden-import','scripts.setup_speech',
           '--hidden-import','scripts.check_runtime']
    if voice_bundle_stage is not None:
        args+=['--add-data',f'{voice_bundle_stage}{os.pathsep}speech',
               '--add-data',f'{voice_license_stage}{os.pathsep}licenses/speech',
               '--hidden-import','scripts.prepare_voice_bundle']
    if sys.platform=='win32':args+=['--manifest',str(ROOT/'QingCi.manifest'),'--add-binary',f'{ROOT/"DesktopBridge.exe"}{os.pathsep}.']
    else:args+=['--osx-bundle-identifier','io.github.blueaaa333.woer-translator','--hidden-import','mac_platform','--hidden-import','ApplicationServices','--hidden-import','Quartz','--hidden-import','AppKit']
    args+=[str(ROOT/'app.py')];command(*args)
    if sys.platform=='win32' and voice_bundle_stage is not None:
        dist_tree=ROOT/'dist'/'WoerTranslator'
        crt_names={'vcruntime140.dll','vcruntime140_1.dll','msvcp140.dll'}
        for path in sorted(dist_tree.rglob('*')):
            if path.is_file() and path.name.lower() in crt_names:
                path.unlink()
        leftovers=[str(path.relative_to(dist_tree)) for path in dist_tree.rglob('*')
                   if path.is_file() and path.name.lower() in crt_names]
        if leftovers:
            raise RuntimeError('Frozen voice bundle still contains app-local MSVC CRT DLLs: '+', '.join(leftovers))
    if sys.platform=='darwin':
        bundle=ROOT/'dist'/'WoerTranslator.app'
        plist=bundle/'Contents'/'Info.plist'
        with plist.open('rb') as stream:info=plistlib.load(stream)
        info.update(CFBundleShortVersionString=version,CFBundleVersion=version)
        with plist.open('wb') as stream:plistlib.dump(info,stream)
        command('/usr/bin/codesign','--force','--deep','--sign','-',bundle)
    executable=ROOT/'dist'/'WoerTranslator'/'WoerTranslator.exe' if sys.platform=='win32' else ROOT/'dist'/'WoerTranslator.app'/'Contents'/'MacOS'/'WoerTranslator'
    report=stage/'smoke-report.json';command(executable,'--smoke-test','--smoke-report',report)
    assert json.loads(report.read_text(encoding='utf-8'))['dictionaries']=='ok'
    shutil.copy2(report,out/f'WoerTranslator-{version}-{target}-{arch}-checks.json')
    if sys.platform=='win32':
        menu_report=stage/'menu-layout.json'
        command(executable,'--check-menu-layout',menu_report)
        assert json.loads(menu_report.read_text(encoding='utf-8'))['resize_clip']=='ok'
    if sys.platform=='darwin':
        runtime_report=stage/'runtime-report.json'
        subprocess.run([str(executable),'--gui-self-test','--gui-report',str(runtime_report)],cwd=ROOT,check=True,timeout=40)
        runtime=json.loads(runtime_report.read_text(encoding='utf-8'))
        if 'error' in runtime:raise RuntimeError('Frozen macOS UI check failed: '+str(runtime))
        shutil.copy2(runtime_report,out/f'WoerTranslator-{version}-{target}-{arch}-runtime.json')
    if sys.platform=='win32':
        if not skip_portable:shutil.make_archive(str(out/f'WoerTranslator-{version}-Windows-x64-Portable'),'zip',ROOT/'dist','WoerTranslator')
        if not skip_installer:
            compiler=Path(os.environ.get('ProgramFiles(x86)',r'C:\Program Files (x86)'))/'Inno Setup 6'/'ISCC.exe'
            if not compiler.exists():raise RuntimeError('Install Inno Setup 6 from its official source first')
            inno_args=[f'/DAppVersion={version}']
            if voice_bundle_stage is not None:
                parts=minimum_msvc_runtime_version.split('.')
                if len(parts)!=4 or any(not part.isdigit() for part in parts):
                    raise RuntimeError('Invalid minimum MSVC runtime version: '+minimum_msvc_runtime_version)
                names=('Major','Minor','Build','Revision')
                inno_args.append('/DRequireMsvcRuntime=1')
                inno_args.extend(f'/DMsvcRuntimeMinimum{name}={part}' for name,part in zip(names,parts))
            command(compiler,*inno_args,ROOT/'packaging'/'windows.iss')
    else:
        app=ROOT/'dist'/'WoerTranslator.app'
        # A local ad-hoc signature is not a Developer ID signature or notarization.
        command('/usr/bin/codesign','--force','--deep','--sign','-',app)
        command('/usr/bin/codesign','--verify','--deep','--strict',app)
        dmg_stage=Path(tempfile.mkdtemp(prefix='dmg-',dir=ROOT/'build'))
        shutil.copytree(app,dmg_stage/'WoerTranslator.app',symlinks=True)
        command('/usr/bin/codesign','--verify','--deep','--strict',dmg_stage/'WoerTranslator.app')
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
        command(sys.executable,ROOT/'scripts'/'check_mac_update.py',out/f'WoerTranslator-{version}-macOS-{arch}.dmg')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--skip-installer',action='store_true');parser.add_argument('--skip-portable',action='store_true');parser.add_argument('--voice-bundle-root',type=Path);parser.add_argument('--minimum-msvc-runtime-version')
    args=parser.parse_args();build(args.skip_installer,args.skip_portable,args.voice_bundle_root,args.minimum_msvc_runtime_version)
