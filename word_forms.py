import re
from collections import OrderedDict
from chinese_text import simplified
from lexicon import normalize_query,valid_query,normalize_pos,clean_definition

LABELS={'0':'原形','s':'复数','3':'第三人称单数','i':'现在分词 / 动名词','p':'过去式','d':'过去分词','r':'比较级','t':'最高级'}
USAGE={'0':'','s':'名词表示多个事物时使用。','3':'用于 he / she / it 作主语的一般现在时。','i':'常与 be 连用表示正在进行，也可作动名词。','p':'表示过去发生的动作。','d':'常用于完成时（have / has / had）或被动结构。','r':'用于比较，表示“更……”。','t':'表示在比较范围内“最……”。'}
ORDER={'0':0,'s':2,'3':3,'i':4,'p':5,'d':6,'r':7,'t':8}

def tag_kind(tags,pos=''):
    tags=set(tags)
    if tags&{'archaic','obsolete','dialectal','rare','nonstandard','dated','alternative'}:return None
    if 'canonical' in tags or 'positive' in tags:return '0'
    if 'comparative' in tags:return 'r'
    if 'superlative' in tags:return 't'
    if 'past' in tags:return 'd' if 'participle' in tags else 'p'
    if 'present' in tags and 'participle' in tags:return 'i'
    if 'third-person' in tags and 'singular' in tags:return '3'
    if 'plural' in tags and pos in ('noun','name'):return 's'
    return None

def short_meaning(lexicon,word,kind):
    wants={'s':('n',),'3':('v','vt','vi'),'i':('v','vt','vi','n'),'p':('v','vt','vi'),'d':('v','vt','vi'),'r':('adj','adv'),'t':('adj','adv')}.get(kind,())
    texts=[]
    if lexicon.exam:
        row=lexicon.exam.execute('select translation from entries where word=?',(word,)).fetchone()
        if row:texts.append(row[0])
    row=lexicon.db.execute('select translation from words where word=?',(word,)).fetchone()
    if row:texts.append(row[0])
    candidates=[]
    for text in texts:
        for line in normalize_pos(simplified(clean_definition(text))).splitlines():
            if not re.search(r'[\u3400-\u9fff]',line):continue
            match=re.match(r'^(n|v|vt|vi|adj|adv)\.\s*(.*)',line)
            if match:
                content=re.sub(r'\([^)]*(?:的过去|的现在|的复数|的第三)[^)]*\)','',match[2]).strip()
                if not content:continue
                candidates.append((match[1],match[1]+'. '+content))
            elif not line.startswith('['):candidates.append(('',line))
    relevant=[value for pos,value in candidates if not wants or pos in wants]
    if not relevant:
        # The public edition uses Wiktionary and WordNet/COW instead of ECDICT.
        # Keep Chinese form explanations available with those licensed sources.
        result=lexicon.lookup(word)
        for entry in result.get('community',[]):
            if entry['edition']!='zh':continue
            pos={'noun':'n','verb':'v','adj':'adj','adv':'adv'}.get(entry['pos'],'')
            if wants and pos not in wants:continue
            for sense in entry['senses']:
                gloss=simplified('；'.join(sense['glosses']))
                if re.search(r'[\u3400-\u9fff]',gloss):relevant.append((pos+'. ' if pos else '')+gloss)
        if not relevant:
            for sense in result['senses']:
                pos={'n':'n','v':'v','a':'adj','r':'adv'}.get(sense['pos'],'')
                if sense['chinese'] and (not wants or pos in wants):relevant.append(pos+'. '+simplified(sense['chinese']))
        if not relevant:return ''
    text='；'.join(dict.fromkeys(relevant[:2] if kind=='0' else relevant[:1]))
    return text if len(text)<=58 else text[:57].rstrip(' ,，;；')+'…'

def form_rows(lexicon,result):
    bases=list(dict.fromkeys([b for b in result['bases'] if b!=result['word']]+[result['word']]))
    records=set()
    def add(base,form,kind):
        form=normalize_query(form).lower();base=normalize_query(base).lower()
        if kind in LABELS and valid_query(form):records.add((base,form,kind))
    has_details=bool(lexicon.extra.execute("select 1 from sqlite_master where type='table' and name='form_details'").fetchone())
    if has_details:
        for base in bases:
            for form,kind in lexicon.extra.execute('select form,kind from form_details where lemma=?',(base,)):add(base,form,kind)
    preferred={}
    for base,form,kind in records:preferred.setdefault((base,kind),set()).add(form)
    # Typed Wiki forms supplement the structured ECDICT fields; tags are never
    # printed verbatim and order differences do not create duplicate rows.
    for entry in result.get('community',[]):
        canonical=next((f['form'] for f in entry['forms'] if 'canonical' in f['tags']),entry['lemma'])
        positive=next((f['form'] for f in entry['forms'] if 'positive' in f['tags']),None)
        if positive:canonical=positive
        canonical=normalize_query(canonical).lower()
        if canonical not in bases:continue
        for form in entry['forms']:
            kind=tag_kind(form['tags'],entry['pos']);spelling=normalize_query(form['form']).lower()
            if not kind:continue
            key=(canonical,kind)
            if key in preferred and spelling not in preferred[key]:continue
            add(canonical,spelling,kind)
            if kind!='0':preferred.setdefault(key,set()).add(spelling)
    if not records:
        reverse={value:key for key,value in LABELS.items()};reverse['现在分词']='i'
        for form in result.get('extra_forms',[]):
            kind=reverse.get(form['label'])
            if kind:add(bases[0],form['form'],kind)
    active_bases={base for base,form,kind in records}
    contexts={}
    for base in active_bases:
        links={kind for b,form,kind in records if b==base and form==result['word']}
        if base!=result['word'] and links:
            allowed={'0'}
            if links&{'r','t'}:allowed.update(('r','t'));contexts[base]='r'
            if links&{'p','d','i','3'}:allowed.update(('p','d','i','3'));contexts[base]='3'
            if 's' in links:allowed.add('s');contexts[base]='s'
            records={record for record in records if record[0]!=base or record[2] in allowed}
    for base in active_bases:add(base,base,'0')
    records={(base,form,kind) for base,form,kind in records if kind=='0' or form!=base or not any(b!=base and f==form and k==kind for b,f,k in records)}
    groups=OrderedDict()
    def rank(record):
        base,form,kind=record
        return (bases.index(base) if base in bases else len(bases),0 if kind=='0' else (1 if form==result['word'] else ORDER[kind]),form)
    for base,form,kind in sorted(records,key=rank):
        # A past tense and past participle with the same spelling share a row;
        # noun plurals and verb third-person forms retain separate meanings.
        key=(base,form,'past' if kind in ('p','d') else kind)
        groups.setdefault(key,[]).append(kind)
    rows=[]
    for (base,form,family),kinds in groups.items():
        kinds=sorted(set(kinds),key=lambda k:ORDER[k])
        kind=kinds[0];label=' / '.join(LABELS[k] for k in kinds)
        meaning_kind=contexts.get(base,'0') if kind=='0' else ('3' if kind=='i' else kind)
        meaning=short_meaning(lexicon,form,meaning_kind)
        if not meaning:
            meaning=short_meaning(lexicon,base,meaning_kind)
            if meaning and form!=base:meaning='原词义：'+meaning
        usage='；'.join(USAGE[k].rstrip('。') for k in kinds if USAGE[k])
        if not meaning:meaning='词库暂未提供该形式的中文释义。'
        rows.append(dict(base=base,form=form,label=label,meaning=simplified(meaning),usage=usage+'。' if usage else '',current=form==result['word'],kinds=kinds))
    return rows
