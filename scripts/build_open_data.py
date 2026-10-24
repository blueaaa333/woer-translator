"""Build release dictionaries exclusively from the sources listed in SOURCES.md."""
import argparse,collections,gzip,hashlib,json,re,sqlite3,zipfile
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]

def kind(tags,pos):
    tags=set(tags)
    if tags & {'obsolete','archaic','nonstandard','dialectal','rare','alternative','dated'}:return None
    if 'canonical' in tags or 'positive' in tags:return '0'
    if 'comparative' in tags:return 'r'
    if 'superlative' in tags:return 't'
    if 'past' in tags:return 'd' if 'participle' in tags else 'p'
    if {'present','participle'}<=tags:return 'i'
    if {'third-person','singular'}<=tags:return '3'
    if 'plural' in tags and pos in ('noun','name'):return 's'


def build(inputs,destination):
    destination.mkdir(parents=True,exist_ok=True)
    required=[inputs/'wordnet.zip',inputs/'cmn.tab',inputs/'simple-extract.jsonl.gz',inputs/'zh-extract.jsonl.gz']
    for p in required:
        if not p.is_file():raise FileNotFoundError(p.name+' missing; see SOURCES.md')
    for name in ('words.db','extended.db','community.db'):
        if (destination/name).exists():raise FileExistsError('Use an empty output directory: '+str(destination))
    empty=sqlite3.connect(destination/'words.db')
    empty.executescript('create table words(word text primary key,phonetic text,translation text,definition text,tag text);')
    empty.close()
    x=sqlite3.connect(destination/'extended.db')
    x.executescript('''create table senses(id text primary key,pos text,definition text,examples text,chinese text);
create table lemmas(word text,sense text,rank integer,primary key(word,sense));
create table forms(form text,lemma text,primary key(form,lemma));
create table form_details(lemma text,form text,kind text,primary key(lemma,form,kind));
create index ix_form_details on form_details(form);''')
    chinese=collections.defaultdict(list)
    for line in (inputs/'cmn.tab').read_text(encoding='utf-8').splitlines():
        f=line.split('\t')
        if len(f)==3 and f[1]=='cmn:lemma':chinese[f[0]].append(f[2])
    with zipfile.ZipFile(inputs/'wordnet.zip') as archive:
        license_text=archive.read('wordnet/LICENSE').decode()
        if 'WordNet 3.0 Copyright 2006' not in license_text:raise ValueError('Unexpected WordNet version')
        for part in ('noun','verb','adj','adv'):
            for line in archive.read('wordnet/data.'+part).decode().splitlines():
                if not line or not line[0].isdigit():continue
                meta,gloss=line.split('|',1);f=meta.split();pos='a' if f[2]=='s' else f[2];sid=f[0]+'-'+pos
                examples=re.findall(r'"([^"\n]+)"',gloss)
                definition=re.sub(r';?\s*"[^"\n]+"','',gloss).strip(' ;')
                x.execute('insert into senses values(?,?,?,?,?)',(sid,pos,definition,json.dumps(examples,ensure_ascii=False),'；'.join(dict.fromkeys(chinese[sid]))))
            for line in archive.read('wordnet/index.'+part).decode().splitlines():
                if not line or line[0].isspace():continue
                f=line.split();count=int(f[2])
                for rank,offset in enumerate(f[-count:]):x.execute('insert into lemmas values(?,?,?)',(f[0].replace('_',' '),offset+'-'+f[1],rank))
            for line in archive.read('wordnet/'+part+'.exc').decode().splitlines():
                f=line.split()
                for base in f[1:]:x.execute('insert or ignore into forms values(?,?)',(f[0],base))
    c=sqlite3.connect(destination/'community.db')
    c.executescript('''create table entries(word text,edition text,pos text,senses text,forms text,sounds text,url text);
create index ix_community_word on entries(word);
create table translation_hints(word text,label text,chinese text,url text,primary key(word,label,chinese));
create table metadata(key text primary key,value text);''')
    counts=collections.Counter();files=list(required)
    def add(entry,edition):
        if entry.get('lang_code')!='en' or not entry.get('word'):return
        word=entry['word'];senses=[];pos=entry.get('pos','')
        for sense in entry.get('senses',[]):
            glosses=sense.get('glosses',[])
            if not glosses:continue
            examples=[]
            for example in sense.get('examples',[]):
                if any(example.get(k) for k in ('ref','reference','source','author','title','year','url')):continue
                if 'quot' in example.get('type','').lower():continue
                if example.get('text'):examples.append(dict(text=example['text'],translation=example.get('translation','')))
            senses.append(dict(glosses=glosses,examples=examples,tags=sense.get('tags',[])))
            counts['wiktionary_senses']+=1;counts['wiktionary_examples']+=len(examples)
        if not senses:return
        forms=[dict(form=f['form'],tags=f.get('tags',[])) for f in entry.get('forms',[]) if f.get('form')]
        sounds=[dict(ipa=f['ipa'],tags=f.get('tags',[])) for f in entry.get('sounds',[]) if f.get('ipa')]
        url='https://'+edition+'.wiktionary.org/wiki/'+quote(word,safe='')
        c.execute('insert into entries values(?,?,?,?,?,?,?)',(word.lower(),edition,pos,json.dumps(senses,ensure_ascii=False),json.dumps(forms,ensure_ascii=False),json.dumps(sounds,ensure_ascii=False),url))
        for tr in entry.get('translations',[]):
            if tr.get('lang_code',tr.get('code')) in ('zh','cmn') and tr.get('word') and tr.get('sense'):
                c.execute('insert or ignore into translation_hints values(?,?,?,?)',(word.lower(),tr['sense'],tr['word'],url))
        canonical=next((f['form'] for f in forms if set(f['tags'])&{'canonical','positive'}),word).lower()
        valid=lambda s:bool(re.fullmatch(r"[a-z]+(?:[-' ][a-z]+)*",s))
        if valid(canonical):
            if word.lower()!=canonical and valid(word.lower()):x.execute('insert or ignore into forms values(?,?)',(word.lower(),canonical))
            for form in forms:
                spelling=form['form'].lower();k=kind(form['tags'],pos)
                if k and valid(spelling):
                    x.execute('insert or ignore into form_details values(?,?,?)',(canonical,spelling,k))
                    if k!='0' and spelling!=canonical:x.execute('insert or ignore into forms values(?,?)',(spelling,canonical))
        counts['wiktionary_entries']+=1
    for edition in ('simple','zh'):
        with gzip.open(inputs/(edition+'-extract.jsonl.gz'),'rb') as stream:
            for line in stream:
                if b'"en"' in line:add(json.loads(line),edition)
    common=sorted((inputs/'common_wiki').glob('*.jsonl'))
    for path in common:
        files.append(path)
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():add(json.loads(line),'en')
    counts['wordnet_senses']=x.execute('select count(*) from senses').fetchone()[0]
    counts['wordnet_headwords']=x.execute('select count(distinct word) from lemmas').fetchone()[0]
    counts['wiktionary_headwords']=c.execute('select count(distinct word) from entries').fetchone()[0]
    manifest=dict(build_date='2026-10-24',counts=dict(counts),inputs=[dict(file=p.name,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files],excluded=['ECDICT','PDF-derived exam data','private dictionary APIs','personal caches'])
    c.execute('insert into metadata values(?,?)',('release_manifest',json.dumps(manifest)))
    c.commit();x.commit();c.close();x.close()
    for path in destination.glob('*.db'):
        # Each archive preserves the license applying to its data, not the MIT code license.
        with path.open('rb') as source,(destination/(path.name+'.gz')).open('wb') as raw:
            with gzip.GzipFile(filename='',mode='wb',fileobj=raw,mtime=0) as output:
                while block:=source.read(1024*1024):output.write(block)
    (destination/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(counts,ensure_ascii=False))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--inputs',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();build(args.inputs,args.output)
