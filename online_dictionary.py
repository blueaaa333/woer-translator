"""Wiktionary API client. Text remains CC BY-SA 4.0, separately from app code."""
import hashlib,html,json,re,ssl,time,urllib.request,urllib.parse,urllib.error
from html.parser import HTMLParser
from pathlib import Path
from chinese_text import simplified
from lexicon import normalize_query,valid_query
AGENT='WoerTranslator/0.3.10 (https://github.com/blueaaa333/woer-translator)'
LICENSE='https://creativecommons.org/licenses/by-sa/4.0/'
class DictionaryUnavailable(Exception):pass

class Plain(HTMLParser):
 def __init__(self):super().__init__();self.parts=[];self.skip=0
 def handle_starttag(self,tag,attrs):
  if tag in ('script','style'):self.skip+=1
 def handle_endtag(self,tag):
  if tag in ('script','style'):self.skip=max(0,self.skip-1)
 def handle_data(self,value):
  if not self.skip:self.parts.append(value)
def plain(value):
 p=Plain();p.feed(value);return re.sub(r'\s+',' ',''.join(p.parts)).strip()

class Definitions(HTMLParser):
 def __init__(self):
  super().__init__();self.heading=None;self.heading_text=[];self.language='';self.pos='';self.stack=[];self.capture=None;self.items=[]
 def handle_starttag(self,tag,attrs):
  if tag in ('h2','h3','h4','h5'):self.heading=tag;self.heading_text=[]
  if tag in ('ol','ul','dl'):self.stack.append(tag)
  if tag=='li' and self.stack==['ol'] and self.pos:
   self.capture=[]
 def handle_endtag(self,tag):
  if tag==self.heading:
   text=simplified(''.join(self.heading_text)).strip()
   if tag=='h2':self.language=text;self.pos=''
   else:self.pos=text if re.match(r'^(名词|动词|形容词|副词|介词|代词|数词|冠词|连词|叹词|词组|短语|成语|习语|释义|分词|词形)',text) else ''
   self.heading=None
  if tag=='li' and self.capture is not None and self.stack==['ol']:
   text=simplified(re.sub(r'\s+',' ',''.join(self.capture)).strip())
   if text:self.items.append(dict(language=self.language,pos=self.pos,text=text,english=False))
   self.capture=None
  if tag in ('ol','ul','dl') and self.stack and self.stack[-1]==tag:self.stack.pop()
 def handle_data(self,value):
  if self.heading:self.heading_text.append(value)
  if self.capture is not None and self.stack==['ol']:self.capture.append(value)

def request(url):
 import certifi
 context=ssl.create_default_context();context.load_verify_locations(certifi.where())
 req=urllib.request.Request(url,headers={'User-Agent':AGENT,'Accept':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=8,context=context) as response:
   if urllib.parse.urlsplit(response.geturl()).hostname not in ('zh.wiktionary.org','en.wiktionary.org'):raise ValueError('Unexpected redirect')
   data=response.read(768*1024+1)
   if len(data)>768*1024:raise ValueError('Response too large')
  return json.loads(data)
 except urllib.error.HTTPError as error:
  if error.code==404:return {}
  raise DictionaryUnavailable('在线词典暂时不可用，本地释义仍可使用') from error
 except Exception as error:
  raise DictionaryUnavailable('无法连接维基词典，请检查网络；本地释义仍可使用') from error

def page_source(edition,title,revision=None):
 host='https://'+edition+'.wiktionary.org'
 url=host+'/wiki/'+urllib.parse.quote(title.replace(' ','_'),safe='')
 return dict(url=url,history=host+'/w/index.php?'+urllib.parse.urlencode(dict(title=title,action='history')),
             revision_url=host+'/w/index.php?oldid='+str(revision) if revision else url,
             licence='CC BY-SA 4.0',licence_url=LICENSE,edition=edition,
             changes='提取释义、去除 HTML 标记、中文转换为简体；词典文本沿用 CC BY-SA 4.0。')

def fetch(word):
 word=normalize_query(word)
 if not valid_query(word):raise ValueError('Invalid dictionary query')
 entries=[];sources=[];failures=[]
 params=dict(action='parse',page=word,prop='text|revid',format='json',formatversion=2,redirects=1)
 try:
  data=request('https://zh.wiktionary.org/w/api.php?'+urllib.parse.urlencode(params))
  if data.get('error',{}).get('code') not in (None,'missingtitle'):raise DictionaryUnavailable('中文维基词典暂时未返回词条')
  page=data.get('parse',{});parser=Definitions();parser.feed(page.get('text',''))
  entries=parser.items[:40]
  if entries:sources.append(page_source('zh',page.get('title',word),page.get('revid')))
 except DictionaryUnavailable as error:failures.append(str(error))
 # English fallback covers Latin and other borrowed terms absent from Chinese edition.
 if not entries:
  try:
   data=request('https://en.wiktionary.org/api/rest_v1/page/definition/'+urllib.parse.quote(word,safe=''))
   groups=data.get('en') or [group for values in data.values() if isinstance(values,list) for group in values]
   for group in groups:
    if not isinstance(group,dict):continue
    for item in group.get('definitions',[]):
     text=plain(item.get('definition',''))
     if text:entries.append(dict(language=group.get('language',''),pos=group.get('partOfSpeech',''),text=text,english=True))
     if len(entries)>=40:break
    if len(entries)>=40:break
   if entries:sources.append(page_source('en',word))
  except DictionaryUnavailable as error:failures.append(str(error))
 if not entries and failures:raise DictionaryUnavailable(failures[-1])
 return dict(word=word,entries=entries,sources=sources,fetched=time.time())

class OnlineDictionary:
 def __init__(self,folder):self.folder=Path(folder)
 def get(self,word):
  word=normalize_query(word).lower();path=self.folder/(hashlib.sha256(word.encode()).hexdigest()+'.json')
  try:
   data=json.loads(path.read_text(encoding='utf-8'));age=time.time()-data['fetched']
   if data.get('word')==word and 0<=age<(86400 if data.get('entries') else 900):return data
  except (OSError,ValueError,KeyError,TypeError):pass
  data=fetch(word)
  try:
   self.folder.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.part');temporary.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8');temporary.replace(path)
  except OSError:pass
  return data

def attribution(data,folder):
 folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
 links=[]
 for source in data.get('sources',[]):
  links.append('<p>维基词典贡献者 · <a href="'+html.escape(source['url'],quote=True)+'">原词条</a> · <a href="'+html.escape(source['history'],quote=True)+'">作者与编辑历史</a> · <a href="'+html.escape(source['revision_url'],quote=True)+'">查询版本</a> · <a href="'+LICENSE+'">CC BY-SA 4.0</a><br>'+html.escape(source['changes'])+'</p>')
 path=folder/'ATTRIBUTION.html';path.write_text('<!doctype html><meta charset="utf-8"><title>在线词典来源与许可</title><h2>维基词典来源与许可</h2>'+''.join(links),encoding='utf-8');return path
