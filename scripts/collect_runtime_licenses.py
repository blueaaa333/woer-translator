"""Collect notices for the exact interpreter and dependencies used to freeze."""
import importlib.metadata as metadata
import hashlib,io,json,platform,sys,tarfile,urllib.request
from pathlib import Path

def collect(destination):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    candidates=[Path(sys.base_prefix)/'LICENSE.txt',Path(sys.base_prefix)/'LICENSE']
    source=next((p for p in candidates if p.is_file()),None)
    if source:text=source.read_text(encoding='utf-8',errors='replace')
    else:
        url=f'https://raw.githubusercontent.com/python/cpython/v{platform.python_version()}/LICENSE'
        with urllib.request.urlopen(url,timeout=60) as response:text=response.read().decode()
    (destination/'Python-LICENSE.txt').write_text(text,encoding='utf-8')
    versions={'Python':platform.python_version()}
    names=['opencc-python-reimplemented','certifi','pyinstaller']
    if sys.platform=='darwin':names += sorted(d.metadata['Name'] for d in metadata.distributions() if d.metadata['Name'].lower().startswith('pyobjc-'))
    for name in names:
        distribution=metadata.distribution(name);versions[name]=distribution.version
        files=[p for p in distribution.files or [] if any(part.lower().startswith(('license','copying','copyright')) for part in p.parts)]
        if not files or name=='pyobjc-core':
            # Some PyObjC wheels omit License.txt although the official sdist
            # includes it. Fetch matching source notices without installing code.
            with urllib.request.urlopen(f'https://pypi.org/pypi/{name}/{distribution.version}/json',timeout=60) as response:release=json.load(response)
            source=next(item for item in release['urls'] if item['packagetype']=='sdist')
            with urllib.request.urlopen(source['url'],timeout=60) as response:archive=response.read()
            if hashlib.sha256(archive).hexdigest()!=source['digests']['sha256']:raise RuntimeError('Source archive hash mismatch')
            count=0
            with tarfile.open(fileobj=io.BytesIO(archive),mode='r:gz') as members:
                for member in members:
                    filename=Path(member.name).name
                    if member.isfile() and filename.lower().startswith(('license','copying','copyright')):
                        (destination/f'{name}-source-{count}-{filename}').write_bytes(members.extractfile(member).read());count+=1
            if not count:raise RuntimeError('Missing source license: '+name)
        for index,relative in enumerate(files):
            path=Path(distribution.locate_file(relative))
            if path.is_file():(destination/f'{name}-{index}-{path.name}').write_bytes(path.read_bytes())
    # Tcl and Tk are embedded by PyInstaller's tkinter hook.
    import tkinter
    interpreter=tkinter.Tcl();patch=interpreter.call('info','patchlevel')
    tag='core-'+str(patch).replace('.','-')
    for component in ('tcl','tk'):
        url=f'https://raw.githubusercontent.com/tcltk/{component}/{tag}/license.terms'
        with urllib.request.urlopen(url,timeout=60) as response:notice=response.read()
        (destination/f'{component}-license.terms').write_bytes(notice)
    versions['Tcl']=str(patch)
    return versions
