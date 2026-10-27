"""Release checks, not a legal warranty. Refuse missing notices/private resources."""
import hashlib,json,re,sqlite3,sys
from pathlib import Path
REQUIRED=('IAccessible2-BSD.txt','WordNet-LICENSE.txt','COW-LICENSE.txt','CC-BY-SA-4.0.html','Wiktionary-NOTICE.md','Lucide-LICENSE.txt','OpenCC-LICENSE.txt','OpenCC-NOTICE.txt')
NATIVE=('Python-LICENSE.txt','CPython-incorporated-software.rst','OpenSSL-LICENSE.txt','zlib-LICENSE.txt','Expat-LICENSE.txt','libmpdec-NOTICE.txt','libffi-LICENSE.txt','bzip2-LICENSE.txt','XZ-liblzma-COPYING.txt','tcl-license.terms','tk-license.terms')

def audit(base):
    base=Path(base);licenses=base/'licenses';runtime=licenses/'runtime'
    missing=[str(Path('licenses')/name) for name in REQUIRED if not (licenses/name).is_file()]
    missing += [str(Path('licenses/runtime')/name) for name in NATIVE if not (runtime/name).is_file()]
    if missing:raise RuntimeError('Missing distribution notices: '+', '.join(missing))
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
            if path.suffix.lower() in ('.pdf','.onnx','.wav','.mp3','.ogg','.oga','.ttf','.otf','.woff','.woff2') or name in ('exam_core.db','preferences.json','生词本.txt','piper.exe'):
                forbidden.append(str(path.relative_to(root)))
    if forbidden:raise RuntimeError('Unreviewed/private distribution files: '+', '.join(forbidden))
    connection=sqlite3.connect((base/'words.db').resolve().as_uri()+'?mode=ro',uri=True)
    try:
        if connection.execute('select count(*) from words').fetchone()[0]!=0:raise RuntimeError('Private dictionary entries in public compatibility database')
    finally:connection.close()
    return dict(check='distribution_notices_and_exclusions',files=count,required_notices=len(REQUIRED)+len(NATIVE),native_notice_hashes='matched',private_compatibility_entries=0,
                legal_scope='Automated packaging evidence only; not a non-infringement warranty')
