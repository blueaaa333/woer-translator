"""Explicitly fetch optional speech dependencies directly from their upstreams.

No runtime binary or voice weights are redistributed by this source repository.
Read docs/SPEECH.md and the upstream terms before choosing to run this command.
"""
import argparse,hashlib,json,shutil,urllib.request,urllib.parse,zipfile,zlib
from pathlib import Path
import sys
ROOT=Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
CHUNK_BYTES=4*1024*1024

def fetch_asset(item, destination):
    size=item.get('bytes',0)
    if urllib.parse.urlsplit(item['url']).hostname=='huggingface.co' and size>CHUNK_BYTES:
        # Verified ranges also handle intermediaries serving partial large HF
        # responses. Keep only one small chunk in memory, not an entire model.
        with destination.open('wb') as output:
            for start in range(0,size,CHUNK_BYTES):
                end=min(start+CHUNK_BYTES,size)-1
                for attempt in range(3):
                    separator='&' if '?' in item['url'] else '?'
                    url=item['url']+separator+f'download=true&woer_segment={start}&attempt={attempt}'
                    request=urllib.request.Request(url,headers={'User-Agent':'WoerTranslator/0.3.6',
                        'Range':f'bytes={start}-{end}','Cache-Control':'no-cache'})
                    try:
                        with urllib.request.urlopen(request,timeout=25) as source:
                            data=source.read(end-start+2)
                            if len(data)!=end-start+1 or not source.headers.get('Content-Range','').startswith(f'bytes {start}-'):
                                raise ValueError('Invalid partial model response')
                        output.write(data);break
                    except Exception:
                        if attempt==2:raise
    else:
        request=urllib.request.Request(item['url'],headers={'User-Agent':'WoerTranslator/0.3.6'})
        with urllib.request.urlopen(request,timeout=120) as source,destination.open('wb') as output:shutil.copyfileobj(source,output)

def install(root):
    root=Path(root).resolve()
    manifest=json.loads((ROOT/'scripts'/'speech-downloads.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        target=(root/item['path']).resolve()
        if not target.is_relative_to(root):raise ValueError('Invalid destination')
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==item['sha256']:continue
        managed_voice=item['path'].startswith('speech/voices/') and target.name.startswith('dictionary-')
        if target.exists() and not managed_voice:raise FileExistsError('Different local dependency already exists: '+str(target))
        target.parent.mkdir(parents=True,exist_ok=True);temporary=target.with_suffix(target.suffix+'.part')
        try:
            print('Downloading '+item['path'],flush=True)
            fetch_asset(item,temporary)
            if hashlib.sha256(temporary.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Upstream SHA256 mismatch')
            temporary.replace(target)
        finally:
            if temporary.exists():temporary.unlink()
    destination=root/'speech'/'runtime';destination.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(root/'speech'/'piper_windows_amd64.zip') as archive:
        for item in archive.infolist():
            resolved=(destination/item.filename).resolve()
            if not resolved.is_relative_to(destination.resolve()):raise ValueError('Unsafe upstream archive path')
        # Skip identical runtime files, including an already-running piper.exe.
        # Stage replacements so a failed write cannot truncate the working copy.
        for item in archive.infolist():
            target=destination/item.filename
            if item.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            if target.is_file() and target.stat().st_size==item.file_size and zlib.crc32(target.read_bytes())&0xffffffff==item.CRC:continue
            target.parent.mkdir(parents=True,exist_ok=True);temporary=target.with_suffix(target.suffix+'.part')
            try:
                with archive.open(item) as source,temporary.open('wb') as output:shutil.copyfileobj(source,output)
                temporary.replace(target)
            finally:temporary.unlink(missing_ok=True)
    print('UK and US offline speech dependencies ready. Their upstream licenses still apply.')
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--target',type=Path,default=ROOT)
    args=parser.parse_args();install(args.target.resolve())
