import sqlite3,json,re
from pathlib import Path
from chinese_text import simplified

def normalize_query(text):
 text=text.replace('\u00ad','').translate(str.maketrans({c:'-' for c in '\u2010\u2011\u2012\u2013\u2014\u2212\ufe63\uff0d'}))
 text=text.translate(str.maketrans({'’':"'",'‘':"'",'ʼ':"'"}))
 text=re.sub(r'\s*-\s*','-',text)
 text=re.sub(r'\s+',' ',text).strip().strip(',;:!?“”"()[]')
 return text.strip('.') if '.' not in text.rstrip('.') else text

def valid_query(text):
 return len(text)<=80 and bool(re.fullmatch(r"[A-Za-z]+(?:[-'. ][A-Za-z]+)*\.?",text)) and len(text.split())<=6

def clean_definition(text):
 return text.replace('\\n','\n').replace('\\r','').replace('\ue7ab','啰').replace('\ue7b3','狂').strip()

class Lexicon:
 def __init__(self,base):
  self.db=sqlite3.connect(Path(base)/'words.db')
  self.extra=sqlite3.connect(Path(base)/'extended.db')
  self.community=sqlite3.connect(Path(base)/'community.db') if (Path(base)/'community.db').exists() else None
  self.exam=sqlite3.connect(Path(base)/'exam_core.db') if (Path(base)/'exam_core.db').exists() else None
  p=Path(base)/'compound_entries.json';self.compounds=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
  p=Path(base)/'examples.json';self.curated=json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
 def lookup(self,word):
  word=normalize_query(word).lower();bases=[word]
  # Look up whole expressions first. Never replace a compound's meaning by
  # blindly joining the translations of its individual parts.
  variants=[word.replace('-',' '),word.replace(' ','-')]
  if '.' in word or len(word)<=4:variants.extend([word.rstrip('.')+'.',word.rstrip('.')])
  for variant in variants:
   if variant!=word and self.has_word(variant):bases.append(variant)
  bases.extend(r[0] for r in self.extra.execute('select lemma from forms where form=?',(word,)))
  if self.exam:bases.extend(r[0] for r in self.exam.execute('select lemma from forms where form=?',(word,)))
  # Keep inflected entries and all mapped base entries, rather than silently replacing them.
  bases=list(dict.fromkeys(bases));entries=[];senses=[];seen=set();custom=[];community=[];translation_hints=[];exam=[];compounds=[];extra_forms=[]
  for base in bases:
   if base in self.compounds:
    compounds.append(dict(self.compounds[base],word=base));custom.extend(self.compounds[base].get('examples',[]))
   exam_row=self.exam.execute('select phonetic,translation,definition,tag,exchange,page from entries where word=?',(base,)).fetchone() if self.exam else None
   if exam_row:
    exam.append(dict(word=base,tag=exam_row[3],page=exam_row[5]))
    entries.append(dict(word=base,phonetic=exam_row[0],translation=exam_row[1],definition=exam_row[2],tag=exam_row[3],source='考纲核心词库'))
    for segment in exam_row[4].split('/'):
     key,sep,value=segment.partition(':');label={'s':'复数','p':'过去式','d':'过去分词','i':'现在分词','3':'第三人称单数','r':'比较级','t':'最高级','0':'原形'}.get(key)
     if sep and label:extra_forms.append(dict(label=label,form=value))
   r=self.db.execute('select phonetic,translation,definition,tag from words where word=?',(base,)).fetchone()
   if r and (not exam_row or (clean_definition(r[1] or ''),clean_definition(r[2] or ''))!=(exam_row[1],exam_row[2])):entries.append(dict(word=base,phonetic=r[0],translation=r[1],definition=r[2],tag=r[3]))
   for row in self.extra.execute('''select s.id,s.pos,s.definition,s.examples,s.chinese from lemmas l join senses s on s.id=l.sense where l.word=? order by case s.pos when 'n' then 0 when 'v' then 1 when 'a' then 2 else 3 end,l.rank''',(base,)):
    if row[0] in seen:continue
    seen.add(row[0]);senses.append(dict(id=row[0],pos=row[1],definition=row[2],examples=json.loads(row[3]),chinese=row[4],lemma=base))
   custom.extend(self.curated.get(base,[]))
   if self.community:
    translation_hints.extend(dict(label=r[0],chinese=r[1],url=r[2]) for r in self.community.execute('select label,chinese,url from translation_hints where word=?',(base,)))
    for row in self.community.execute("select edition,pos,senses,forms,sounds,url from entries where word=? order by case edition when 'zh' then 0 else 1 end",(base,)):
     community.append(dict(edition=row[0],pos=row[1],senses=json.loads(row[2]),forms=json.loads(row[3]),sounds=json.loads(row[4]),url=row[5],lemma=base))
  parts=[]
  if not (entries or senses or community or compounds) and '-' in word and 2<=len(word.split('-'))<=4:
   parts=[dict(word=p,result=self.lookup(p)) for p in word.split('-')]
  return dict(word=word,bases=bases,entries=entries,senses=senses,curated=custom,community=community,translation_hints=translation_hints,exam=exam,compounds=compounds,extra_forms=extra_forms,compound_parts=parts)
 def has_word(self,word):
  if word in self.compounds:return True
  if self.db.execute('select 1 from words where word=?',(word,)).fetchone():return True
  if self.exam and self.exam.execute('select 1 from entries where word=?',(word,)).fetchone():return True
  if self.community and self.community.execute('select 1 from entries where word=? limit 1',(word,)).fetchone():return True
  return bool(self.extra.execute('select 1 from lemmas where word=? limit 1',(word,)).fetchone())

POS={'n':'n. 名词','v':'v. 动词','a':'adj. 形容词','r':'adv. 副词'}

def normalize_pos(text):
 text=text.replace('\\n','\n')
 mapping={'a':'adj','s':'adj','r':'adv'}
 def replace(m):return mapping.get(m[1],m[1])+'. '
 return re.sub(r'(?m)^\s*(n|v|a|s|r|vt|vi|adj|adv|prep|pron|conj|interj|num|det|aux)(?:\.\s*|\s+)',replace,text)
def word_form_note(result):
 bases=[base for base in result['bases'] if base!=result['word'] and re.fullmatch(r"[a-z]+(?:'[a-z]+)?",base)]
 if not bases:return ''
 base=bases[0]
 labels=list(dict.fromkeys(f['label'] for f in result.get('extra_forms',[]) if f['form'].lower()==result['word']))
 return base+' 的'+(' / '.join(labels) if labels else '词形变化')

def definition_sections(result):
 # Meaning and provenance are separate UI roles. Chinese definitions always
 # precede source names, English morphology notes, and extended dictionaries.
 primary=[];details=[];sources=[];seen=set()
 def add(kind,text):
  text=simplified(clean_definition(text))
  key=re.sub(r'\s+','',text)
  if text and key not in seen:primary.append(dict(kind=kind,text=text));seen.add(key)
 note=word_form_note(result)
 if result.get('machine_translation'):
  add('meaning',result['machine_translation']);primary.append(dict(kind='note',text='机器翻译 · 需结合上下文核对'));sources.append('LibreTranslate（自托管）')
 for entry in result.get('compounds',[]):
  add('meaning',normalize_pos(entry['translation']))
  if entry.get('note'):primary.append(dict(kind='note',text=entry['note']))
  details.append(dict(kind='english',text=entry['definition']));sources.append('自编短语与复合词补充')
 for entry in result['entries']:
  if entry['translation']:
   if entry['word']!=result['word']:add('label','原形 '+entry['word'])
   add('meaning',normalize_pos(entry['translation']))
  if entry['definition']:details.append(dict(kind='english',text=('【'+entry['word']+'】\n' if entry['word']!=result['word'] else '')+normalize_pos(entry['definition'])))
  sources.append(entry.get('source','ECDICT'))
 # Chinese Wiktionary meanings remain visible; only their provenance is small.
 for entry in result.get('community',[]):
  if entry['edition']=='zh':
   for sense in entry['senses']:
    gloss='；'.join(sense['glosses'])
    if entry['pos']=='unknown':gloss=re.sub(r'^'+re.escape(entry['lemma'])+r'\s*\n','',gloss)
    if re.search(r'[\u3400-\u9fff]',gloss):add('meaning',WIKI_POS.get(entry['pos'],'')+' '+gloss)
 for hint in result.get('translation_hints',[]):add('meaning',hint['chinese'])
 if not primary:
  for sense in result['senses']:
   if sense['chinese']:add('meaning',POS.get(sense['pos'],sense['pos'])+' '+sense['chinese'])
 if note:primary.append(dict(kind='note',text=note))
 if result.get('exam'):
  tags={'zk':'中考','gk':'高考','cet4':'四级','cet6':'六级','ky':'考研','ielts':'雅思','toefl':'托福','gre':'GRE'}
  labels=list(dict.fromkeys(tags.get(t,t) for entry in result['exam'] for t in entry['tag'].split()))
  primary.append(dict(kind='note',text='考试标签  '+' / '.join(labels)))
 if result.get('translation_hints'):
  grouped={}
  for hint in result['translation_hints']:grouped.setdefault(hint['label'],[]).append(hint['chinese'])
  details.append(dict(kind='source',text='多义对照 · 维基词典'))
  details.append(dict(kind='english',text='\n\n'.join(label+'\n'+'；'.join(dict.fromkeys(words)) for label,words in grouped.items())))
 if result.get('community'):
  sources.append('维基词典')
  for entry in result['community']:
   source={'zh':'中文','simple':'简单英语','en':'英语'}.get(entry['edition'],entry['edition'])
   details.append(dict(kind='source',text='维基词典 · '+source+' / '+WIKI_POS.get(entry['pos'],entry['pos'])))
   details.append(dict(kind='english',text='\n'.join(str(i)+'. '+'；'.join(sense['glosses']) for i,sense in enumerate(entry['senses'],1))))
 if result['senses']:
  sources.append('WordNet / COW')
  details.append(dict(kind='source',text='详细分义 · WordNet / COW'))
  for i,sense in enumerate(result['senses'],1):details.append(dict(kind='english',text=str(i)+'. '+POS.get(sense['pos'],sense['pos'])+' '+(sense['chinese']+'\n' if sense['chinese'] else '')+sense['definition']))
 if not primary and result.get('compound_parts'):
  add('note','构词辅助 · 整词暂未收录\n以下为组成部分的释义，整词含义需结合上下文判断。')
  for part in result['compound_parts']:
   entry=next((e for e in part['result']['entries'] if e['translation']),None)
   add('label',part['word']);add('meaning',normalize_pos(entry['translation']) if entry else '暂未收录')
 if not any(section['kind']=='meaning' for section in primary):
  if details:
   primary.insert(0,dict(kind='note',text='中文释义暂缺，以下为已有英文释义。'))
   # English-only entries still show their definition without requiring a click.
   primary.extend(section for section in details if section['kind']=='english');details=[section for section in details if section['kind']!='english']
  elif not primary:primary.append(dict(kind='note',text='本地词库暂未收录此词或短语。可在设置中启用本地短语翻译，或补充上下文后再查询。'))
 return dict(primary=[dict(s,text=simplified(s['text'])) for s in primary],details=[dict(s,text=simplified(s['text'])) for s in details],sources=list(dict.fromkeys(simplified(source) for source in sources)))

def definition_text(result):
 sections=definition_sections(result)
 blocks=[s['text'] for s in sections['primary']]
 blocks.extend(s['text'] for s in sections['details'])
 if sections['sources']:blocks.append('来源：'+' · '.join(sections['sources']))
 return simplified('\n\n'.join(blocks))

def examples_text(result):
 blocks=[]
 if result.get('community'):
  blocks.append(community_text(result,examples=True))
 if result['curated']:
  blocks.append('常用义 · 双语示例（自编）')
  for i,item in enumerate(result['curated'],1):blocks.append(f"{i}. {item[0]}\n{item[1]}\n{item[2]}")
 available=[s for s in result['senses'] if s['examples']]
 if available:blocks.append('WordNet / COW · 分义例句\n各例句对应其上方词义。')
 for i,s in enumerate(available,1):
  block=f"{i}. {POS.get(s['pos'],s['pos'])} · "+(s['chinese'] or s['lemma'])+'\n'+s['definition']
  if s['examples']:
   for ex in s['examples']:
    # Synset examples may use a synonym; make that explicit instead of mislabelling.
    is_target=re.search(r'\b'+re.escape(s['lemma'])+r'(?:s|es|ed|ing)?\b',ex,re.I)
    block+='\n'+('例句：' if is_target else '同义词组例句：')+ex
  blocks.append(block)
 if not blocks:blocks.append('本地例句库暂未收录该词的分义例句。')
 return simplified('\n\n'.join(blocks))

WIKI_POS={'noun':'n.','verb':'v.','adj':'adj.','adv':'adv.','prep':'prep.','name':'专名','pron':'pron.','conj':'conj.','intj':'interj.','phrase':'短语','num':'num.','det':'det.'}
def community_text(result,examples=False):
 blocks=[]
 for entry in result.get('community',[]):
  # Only show senses that have usage examples on the examples page; full senses remain on Definitions.
  senses=[s for s in entry['senses'] if s.get('examples')] if examples else entry['senses']
  if not senses:continue
  source={'zh':'维基词典 · 中文','simple':'维基词典 · 简单英语','en':'维基词典 · 英语'}.get(entry['edition'],'维基词典')
  blocks.append(source+' / '+WIKI_POS.get(entry['pos'],entry['pos']))
  for i,sense in enumerate(senses,1):
   block=str(i)+'. '+'；'.join(sense['glosses'])
   if examples:
    for ex in sense.get('examples',[]):
     block+='\n'+ex['text']
     if ex.get('translation'):block+='\n'+ex['translation']
   blocks.append(block)
 return '\n\n'.join(blocks)
