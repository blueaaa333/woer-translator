"""Release checks, not a legal warranty. Refuse missing notices/private resources."""
import hashlib,json,re,sqlite3,sys
from pathlib import Path
REQUIRED=('IAccessible2-BSD.txt','WordNet-LICENSE.txt','COW-LICENSE.txt','CC-BY-SA-4.0.html','Wiktionary-NOTICE.md','Lucide-LICENSE.txt','OpenCC-LICENSE.txt','OpenCC-NOTICE.txt')
NATIVE=('Python-LICENSE.txt','CPython-incorporated-software.rst','OpenSSL-LICENSE.txt','zlib-LICENSE.txt','Expat-LICENSE.txt','libmpdec-NOTICE.txt','libffi-LICENSE.txt','bzip2-LICENSE.txt','XZ-liblzma-COPYING.txt','tcl-license.terms','tk-license.terms')
ECDICT_COMMIT='39cfb9672c0906b63569e0453c2e6abfb9ab182a'
ECDICT_SOURCE_SHA256='d1ecbdf9ee2b920afb6f430ca6b6bb9f559588cf0dff86e04bd255f9390843cc'
MSVC_CRT_NAMES=frozenset({'vcruntime140.dll','vcruntime140_1.dll','msvcp140.dll'})

def audit(base):
    base=Path(base);licenses=base/'licenses';runtime=licenses/'runtime'
    missing=[str(Path('licenses')/name) for name in REQUIRED if not (licenses/name).is_file()]
    missing += [str(Path('licenses/runtime')/name) for name in NATIVE if not (runtime/name).is_file()]
    if missing:raise RuntimeError('Missing distribution notices: '+', '.join(missing))
    from scripts.prepare_voice_bundle import audit_embedded_voice_payload
    voice_report=audit_embedded_voice_payload(base)
    allowed_voice_paths=set()
    if voice_report:
        allowed_voice_paths={(base/relative).resolve() for relative in voice_report['paths']}
    evidence=json.loads((runtime/'native-components.json').read_text(encoding='utf-8'))
    for item in evidence['notices']:
        name=item['file']
        if Path(name).name!=name:raise RuntimeError('Invalid notice path')
        if hashlib.sha256((runtime/name).read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Notice changed after collection: '+name)
    roots=[base]
    if base.parent.name=='Contents' and (base.parent/'Resources').is_dir():roots.append(base.parent/'Resources')
    forbidden=[];seen=set();count=0
    for root in roots:
        for path in root.rglob('*'):
            if not path.is_file():continue
            resolved=path.resolve()
            if resolved in seen:continue
            seen.add(resolved);count+=1
            name=path.name.lower()
            restricted=path.suffix.lower() in ('.pdf','.onnx','.wav','.mp3','.ogg','.oga','.ttf','.otf','.woff','.woff2') or name in ('exam_core.db','preferences.json','生词本.txt','piper.exe')
            if name in MSVC_CRT_NAMES:
                forbidden.append(str(path.relative_to(root)))
            elif restricted and resolved not in allowed_voice_paths:
                forbidden.append(str(path.relative_to(root)))
    if forbidden:raise RuntimeError('Unreviewed/private distribution files: '+', '.join(forbidden))
    manifest_path=base/'ecdict-manifest.json'
    if not manifest_path.is_file():raise RuntimeError('Missing pinned ECDICT build manifest')
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    if manifest.get('source_commit')!=ECDICT_COMMIT or manifest.get('source_sha256')!=ECDICT_SOURCE_SHA256:
        raise RuntimeError('ECDICT source pin mismatch')
    database=base/'words.db'
    if hashlib.sha256(database.read_bytes()).hexdigest()!=manifest.get('database_sha256'):
        raise RuntimeError('ECDICT database hash mismatch')
    connection=sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)
    try:
        row_count=connection.execute('select count(*) from words').fetchone()[0]
        if row_count!=manifest.get('headwords'):raise RuntimeError('ECDICT database row count mismatch')
    finally:connection.close()
    return dict(check='distribution_notices_and_exclusions',files=count,required_notices=len(REQUIRED)+len(NATIVE),native_notice_hashes='matched',
                ecdict_source_commit=ECDICT_COMMIT,ecdict_headwords=row_count,ecdict_database_hash='matched',
                legal_scope='Automated packaging evidence only; not a non-infringement warranty',
                voice_payload_files=(voice_report['files'] if voice_report else 0),
                voice_payload_paths=(voice_report['paths'] if voice_report else []))
