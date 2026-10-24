"""Explicitly fetch optional speech dependencies directly from their upstreams.

No runtime binary or voice weights are redistributed by this source repository.
Read docs/SPEECH.md and the upstream terms before choosing to run this command.
"""
import argparse,hashlib,json,shutil,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def install(root):
    manifest=json.loads((ROOT/'scripts'/'speech-downloads.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        target=(root/item['path']).resolve()
        if not target.is_relative_to(root):raise ValueError('Invalid destination')
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']:continue
        if target.exists():raise FileExistsError('Different local dependency already exists: '+str(target))
        target.parent.mkdir(parents=True,exist_ok=True);temporary=target.with_suffix(target.suffix+'.part')
        try:
            print('Downloading '+item['path'],flush=True)
            request=urllib.request.Request(item['url'],headers={'User-Agent':'WoerTranslator/0.1'})
            with urllib.request.urlopen(request,timeout=120) as source,temporary.open('wb') as output:shutil.copyfileobj(source,output)
            if hashlib.sha256(temporary.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Upstream SHA256 mismatch')
            temporary.replace(target)
        finally:
            if temporary.exists():temporary.unlink()
    destination=root/'speech'/'runtime';destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(root/'speech'/'piper_windows_amd64.zip') as archive:
        for item in archive.infolist():
            resolved=(destination/item.filename).resolve()
            if not resolved.is_relative_to(destination.resolve()):raise ValueError('Unsafe upstream archive path')
        archive.extractall(destination)
    print('UK and US offline speech dependencies ready. Their upstream licenses still apply.')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target',type=Path,default=ROOT)
    args=parser.parse_args();install(args.target.resolve())
