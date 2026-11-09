"""Verify and unpack the public, licensed dictionary archives."""
import gzip,hashlib,json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.build_ecdict import SOURCE_SHA256,UPSTREAM_COMMIT,sha256_file

def ecdict_bundle(root,bundle_dir=None):
    folder=Path(bundle_dir) if bundle_dir else root/'build'/'ecdict'
    database=folder/'words.db';archive=folder/'words.db.gz';path=folder/'manifest.json'
    if not path.is_file():raise FileNotFoundError('Run scripts/build_ecdict.py before preparing public dictionaries')
    data=json.loads(path.read_text(encoding='utf-8'))
    if data.get('source_commit')!=UPSTREAM_COMMIT or data.get('source_sha256')!=SOURCE_SHA256:
        raise ValueError('ECDICT source pin mismatch in build manifest')
    if not database.is_file() or sha256_file(database)!=data.get('database_sha256'):
        raise ValueError('ECDICT database checksum mismatch')
    if not archive.is_file() or sha256_file(archive)!=data.get('archive_sha256'):
        raise ValueError('ECDICT archive checksum mismatch')
    return data,database,archive

def install_ecdict(root,item,data,archive):
    seed=root/'data'/item['archive']
    if hashlib.sha256(seed.read_bytes()).hexdigest()!=item['sha256']:
        raise ValueError('Dictionary checksum mismatch: '+seed.name)
    target=root/item['target'];expected=data['database_sha256']
    if target.exists():
        current=hashlib.sha256(target.read_bytes()).hexdigest()
        if current==expected:return
        if current!=item['unpacked_sha256']:
            raise FileExistsError('Refusing to overwrite a different local dictionary: '+target.name)
    temporary=target.with_suffix('.unpacking')
    if temporary.exists():raise FileExistsError('Refusing to overwrite temporary dictionary: '+temporary.name)
    try:
        with gzip.open(archive,'rb') as source,temporary.open('xb') as output:shutil.copyfileobj(source,output)
        if hashlib.sha256(temporary.read_bytes()).hexdigest()!=expected:raise ValueError('ECDICT unpacked checksum mismatch')
        temporary.replace(target)
    finally:
        if temporary.exists():temporary.unlink()

def prepare(root=ROOT,bundle_dir=None):
    root=Path(root)
    manifest=json.loads((root/'data'/'checksums.json').read_text(encoding='utf-8'))
    ecdict,_,ecdict_archive=ecdict_bundle(root,bundle_dir)
    for item in manifest:
        archive=root/'data'/item['archive'];target=root/item['target']
        if item['target']=='words.db':
            install_ecdict(root,item,ecdict,ecdict_archive)
            continue
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
