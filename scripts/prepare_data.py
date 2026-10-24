"""Verify and unpack the public, licensed dictionary archives."""
import gzip,hashlib,json,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def prepare(root=ROOT):
    manifest=json.loads((root/'data'/'checksums.json').read_text(encoding='utf-8'))
    for item in manifest:
        archive=root/'data'/item['archive'];target=root/item['target']
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=item['sha256']:
            raise ValueError('Dictionary checksum mismatch: '+archive.name)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest()!=item['unpacked_sha256']:
                raise FileExistsError('Refusing to overwrite a different local dictionary: '+target.name)
            continue
        temporary=target.with_suffix('.unpacking')
        try:
            with gzip.open(archive,'rb') as source,temporary.open('wb') as output:shutil.copyfileobj(source,output)
            if hashlib.sha256(temporary.read_bytes()).hexdigest()!=item['unpacked_sha256']:raise ValueError('Unpacked checksum mismatch')
            temporary.replace(target)
        finally:
            if temporary.exists():temporary.unlink()
    print('Public dictionaries verified and ready')
if __name__=='__main__':prepare()
