"""Collect notices for native libraries used by the selected CPython runtime."""
import hashlib,json,platform,re,ssl,sys,urllib.request,urllib.error,zlib
import xml.parsers.expat
from pathlib import Path

def read(url):
    request=urllib.request.Request(url,headers={'User-Agent':'WoerTranslator-LicenseCollector/0.3.11 (https://github.com/blueaaa333/woer-translator)'})
    with urllib.request.urlopen(request,timeout=45) as response:
        data=response.read(1024*1024+1)
    if len(data)>1024*1024:raise RuntimeError('Unexpectedly large notice')
    return data

def collect(destination,python_version=None,openssl_version=None,zlib_version=None,target=None):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    py=python_version or platform.python_version();target=target or sys.platform
    openssl=openssl_version or '.'.join(map(str,ssl.OPENSSL_VERSION_INFO[:3]))
    zversion=zlib_version or zlib.ZLIB_RUNTIME_VERSION
    if not openssl.startswith('3.'):raise RuntimeError('Review OpenSSL licence for this major version before publishing')
    prefix=f'https://raw.githubusercontent.com/python/cpython/v{py}/'
    props=read(prefix+'PCbuild/python.props').decode()
    bzip=re.search(r'bzip2-([0-9.]+)',props)
    ffi=re.search(r'libffi-([0-9.]+)',props)
    xz=re.search(r'xz-([0-9.]+)',props)
    if not all((bzip,ffi,xz)):raise RuntimeError('Cannot identify CPython native dependency references')
    xversion=xz[1]
    xurl=f'https://raw.githubusercontent.com/python/cpython-source-deps/xz-{xversion}/COPYING'
    if target=='darwin':
        recipe=read(prefix+'Mac/BuildScript/build-installer.py').decode()
        match=re.search(r'xz-([0-9.]+)\.tar',recipe)
        if not match:raise RuntimeError('Cannot identify macOS liblzma reference')
        xversion=match[1];xurl=f'https://raw.githubusercontent.com/tukaani-project/xz/v{xversion}/COPYING'
    records=[]
    def save(name,url,marker,header=False):
        data=read(url)
        if header:
            # Preserve the complete original copyright/licence comment, not code.
            match=re.search(rb'/\*.*?\*/',data,re.S)
            if not match:raise RuntimeError('Missing source copyright block')
            data=match[0]+b'\n'
        if marker.lower() not in data.decode('utf-8',errors='replace').lower():raise RuntimeError('Unexpected licence text: '+name)
        (destination/name).write_bytes(data)
        records.append(dict(file=name,url=url,sha256=hashlib.sha256(data).hexdigest(),changes='Unmodified notice; source header extracted only' if header else 'Unmodified upstream notice'))
    save('CPython-incorporated-software.rst',prefix+'Doc/license.rst','OpenSSL')
    save('OpenSSL-LICENSE.txt',f'https://raw.githubusercontent.com/openssl/openssl/openssl-{openssl}/LICENSE.txt','Apache License')
    try:
        save('zlib-LICENSE.txt',f'https://raw.githubusercontent.com/madler/zlib/v{zversion}/LICENSE','origin of this software')
    except urllib.error.HTTPError as error:
        if error.code!=404:raise
        save('zlib-LICENSE.txt',f'https://raw.githubusercontent.com/madler/zlib/v{zversion}/zlib.h','origin of this software',header=True)
    save('Expat-LICENSE.txt',prefix+'Modules/expat/COPYING','Permission is hereby granted')
    save('libmpdec-NOTICE.txt',prefix+'Modules/_decimal/libmpdec/mpdecimal.c','Stefan Krah',header=True)
    save('libffi-LICENSE.txt',f'https://raw.githubusercontent.com/libffi/libffi/v{ffi[1]}/LICENSE','Permission is hereby granted')
    save('bzip2-LICENSE.txt',f'https://raw.githubusercontent.com/python/cpython-source-deps/bzip2-{bzip[1]}/LICENSE','Julian R Seward')
    save('XZ-liblzma-COPYING.txt',xurl,'liblzma is in the public domain')
    evidence=dict(python=py,target=target,openssl=openssl,zlib=zversion,
                  expat=xml.parsers.expat.EXPAT_VERSION,libffi_source_reference=ffi[1],
                  bzip2_source_reference=bzip[1],xz_source_reference=xversion,
                  note='Source references are CPython build declarations, not a claim that every system library is bundled.',notices=records)
    (destination/'native-components.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    return evidence
