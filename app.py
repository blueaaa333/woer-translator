import sys
if __name__=='__main__' and '--apply-mac-update' in sys.argv:
 from updater import apply_mac
 apply_mac(sys.argv[sys.argv.index('--apply-mac-update')+1])
 raise SystemExit
if __name__=='__main__' and '--mac-bridge' in sys.argv:
 from mac_native import run
 run()
 raise SystemExit

import tkinter as tk
from tkinter import ttk
import ctypes as C,sqlite3,sys,os,re,threading,time,queue,urllib.request,urllib.parse,hashlib,json,subprocess,atexit,base64,traceback
from pathlib import Path
from lexicon import Lexicon,definition_text,definition_sections,word_form_note,examples_text,normalize_pos,normalize_query,valid_query
from chinese_text import simplified
from pronunciation import SpeechEngine,phonetic_labels,SpeechUnavailable
from word_forms import form_rows
from preferences import PreferenceStore

from app_paths import resource_root,user_data_dir
IS_WINDOWS=sys.platform=='win32'
if IS_WINDOWS:
 import winsound
else:
 import mac_platform as mac
 winsound=mac.sound
BASE=resource_root();DATA=user_data_dir();DATA.mkdir(parents=True,exist_ok=True)
UI_FONT='Microsoft YaHei UI' if IS_WINDOWS else 'PingFang SC'
LATIN_FONT='Segoe UI' if IS_WINDOWS else 'Helvetica Neue'
def write_error(kind,exc,value,tb):
 try:
  with (DATA/'application-errors.log').open('a',encoding='utf-8') as f:
   f.write('\n'+time.strftime('%Y-%m-%d %H:%M:%S')+' '+kind+'\n');traceback.print_exception(exc,value,tb,file=f)
 except OSError:pass
if IS_WINDOWS:
 u=C.windll.user32
 # Set awareness BEFORE Tk creates a window: never let Windows bitmap-stretch text.
 try:u.SetProcessDpiAwarenessContext(C.c_void_p(-4))
 except (AttributeError,OSError):
  try:C.windll.shcore.SetProcessDpiAwareness(2)
  except (AttributeError,OSError):u.SetProcessDPIAware()
 u.GetClipboardData.restype=C.c_void_p
 k=C.windll.kernel32;k.GlobalLock.argtypes=[C.c_void_p];k.GlobalLock.restype=C.c_void_p;k.GlobalUnlock.argtypes=[C.c_void_p]
else:u=k=None
def clipboard_sequence():return u.GetClipboardSequenceNumber() if IS_WINDOWS else mac.clipboard_sequence()

events=queue.Queue()
def clipboard():
 if not IS_WINDOWS:return mac.clipboard_text()
 if not u.OpenClipboard(None): return ''
 try:
  h=u.GetClipboardData(13)
  if not h:return ''
  k.GlobalSize.argtypes=[C.c_void_p];k.GlobalSize.restype=C.c_size_t
  if k.GlobalSize(h)>512:return ''
  p=k.GlobalLock(h)
  if not p:return ''
  try:return C.wstring_at(p)
  finally:k.GlobalUnlock(h)
 finally:u.CloseClipboard()
def hotkeys():
 if not IS_WINDOWS:return
 # Register in this thread because Windows delivers hotkey messages to its queue.
 if not u.RegisterHotKey(None,1,0x4000|0x2|0x4,0x44):events.put(('status','快捷键被占用：请使用复制弹窗或手动输入'))
 from ctypes import wintypes
 msg=wintypes.MSG()
 while u.GetMessageW(C.byref(msg),None,0,0)>0:
  if msg.message==0x312:
   for _ in range(100):
    if not any(u.GetAsyncKeyState(v)&0x8000 for v in (0x11,0x12,0x44)):break
    time.sleep(.01)
   old=u.GetClipboardSequenceNumber()
   u.keybd_event(0x11,0,0,0);u.keybd_event(0x43,0,0,0);u.keybd_event(0x43,0,2,0);u.keybd_event(0x11,0,2,0)
   for _ in range(20):
    time.sleep(.035)
    if u.GetClipboardSequenceNumber()!=old:
     events.put(('lookup',clipboard()));break
   else:events.put(('show','未能复制选区，请选中单词后重试，或复制后查词'))
bridge_stop=threading.Event()
selection_enabled=threading.Event()
managed=set();managed_lock=threading.Lock()
def start_bridge(args,**kwargs):
 proc=subprocess.Popen([str(BASE/'DesktopBridge.exe')]+args,creationflags=0x08000000,**kwargs)
 with managed_lock:managed.add(proc)
 return proc
def stop_children():
 bridge_stop.set()
 if not IS_WINDOWS:mac.stop_monitor()
 with managed_lock:procs=list(managed)
 for proc in procs:
  if proc.poll() is None:
   try:proc.terminate()
   except OSError:pass
def forget(proc):
 with managed_lock:managed.discard(proc)
atexit.register(stop_children)
def record_stage(stage,**fields):
 try:
  entry=dict(time=time.time(),process=os.getpid(),stage=stage,**fields)
  path=DATA/'selection-timing.jsonl'
  if path.exists() and path.stat().st_size>64000:
   lines=path.read_text(encoding='utf-8').splitlines()[-150:];path.write_text('\n'.join(lines)+'\n',encoding='utf-8')
  with path.open('a',encoding='utf-8') as f:f.write(json.dumps(entry,ensure_ascii=False)+'\n')
 except OSError:pass
def source_process(pid):
 k.OpenProcess.restype=C.c_void_p;k.OpenProcess.argtypes=[C.c_ulong,C.c_int,C.c_ulong]
 k.CloseHandle.argtypes=[C.c_void_p]
 handle=k.OpenProcess(0x1000,False,int(pid))
 if not handle:return ''
 try:
  buf=C.create_unicode_buffer(2048);length=C.c_ulong(2048)
  k.QueryFullProcessImageNameW.argtypes=[C.c_void_p,C.c_ulong,C.c_wchar_p,C.POINTER(C.c_ulong)]
  return Path(buf.value).stem.lower() if k.QueryFullProcessImageNameW(handle,0,buf,C.byref(length)) else ''
 finally:k.CloseHandle(handle)
def selection_monitor():
 if not IS_WINDOWS:
  mac.monitor(events,selection_enabled,bridge_stop);return
 # Browser PDF accessibility ranges may point to unrelated text on the page.
 # Only observe gestures here. Read text via a fresh copy after an explicit click.
 watch=None
 def read_watch():
  cache={}
  for line in watch.stdout:
   if bridge_stop.is_set():break
   f=line.decode('utf-8-sig').strip().split('|')
   if f[0]=='CLEAR':
    if len(f)==4 and f[2].isdigit() and f[3].isdigit():
     detail=dict(reason=f[1],at=int(f[2]),pid=int(f[3]));events.put(('clear',detail));record_stage('clear_received',**detail)
    continue
   if len(f)!=6 or not all(re.fullmatch(r'-?\d+',v) for v in f):continue
   if not selection_enabled.is_set():continue
   pid=f[0]
   if pid not in cache:cache[pid]=source_process(pid)
   if cache[pid] not in {'msedge','chrome','firefox','qianwen','360se','360chrome','qqbrowser','quark','acrobat','acrord32','sumatrapdf','wps','winword','notepad','notepad++','pdfxedit','foxitpdfreader'}:continue
   event=dict(pid=int(f[0]),hwnd=int(f[1]),x=int(f[2]),y=int(f[3]),id=int(f[4]),emitted=int(f[5]),word='')
   events.put(('gesture',event));record_stage('gesture_received',id=event['id'],source_pid=event['pid'],app=cache[pid])
 try:
  watch=start_bridge(['watch',str(os.getpid())],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  read_watch()
 except Exception as exc:
  record_stage('listener_error',error=type(exc).__name__);events.put(('status','自动检测暂不可用，复制单词也可弹出查询'))
 finally:
  for proc in (watch,):
   if proc:
    if proc.poll() is None:proc.terminate()
    forget(proc)
class App:
 def __init__(self,testing=False):
  self.lexicon=Lexicon(BASE);self.db=self.lexicon.db;self.result=None;self.online=None;self.use_online=False;self.word='';self.seq=clipboard_sequence();self.popup=None;self.testing=testing
  self.speech=SpeechEngine(BASE,DATA/'speech-cache',user_root=DATA/'speech')
  self.preference_store=PreferenceStore(DATA/'preferences.json',read_only=testing)
  self.preferences=self.read_preferences();self.settings_popup=None
  self.preferred_accent=self.preferences.get('preferred_accent',2)
  self.audio_serial=0;self.audio_lock=threading.Lock();self.accent=self.preferences.get('accent',0);self.last_prompt='';self.last_prompt_time=0;self.pending_source=None;self.clipboard_suppress_until=0;self.selection_version=0
  self.root=tk.Tk();self.root.title('沃尔翻译官');self.dpi=u.GetDpiForSystem() if IS_WINDOWS and hasattr(u,'GetDpiForSystem') else 96;self.scale=self.dpi/96;
  if IS_WINDOWS:self.root.tk.call('tk','scaling',self.dpi/72)
  self.root.geometry(f'{round(380*self.scale)}x{round(420*self.scale)}');self.root.configure(bg='#dce7fb');self.root.overrideredirect(True);self.root.attributes('-topmost',True)
  self.root.option_add('*Font',(UI_FONT,10))
  self.root.report_callback_exception=self.on_error
  sizes=[16,18,20,24,27,30,32,36,40,48,64];size=min(sizes,key=lambda n:abs(n-18*self.scale))
  self.brand_icon=tk.PhotoImage(file=str(BASE/'assets'/f'brand-{size}.png'))
  if IS_WINDOWS:self.root.iconbitmap(str(BASE/'assets'/'沃尔翻译官.ico'))
  else:
   self.root.iconphoto(True,self.brand_icon);self.root.createcommand('tk::mac::Quit',self.root.destroy)
  self.root.bind('<Escape>',lambda e:self.hide())
  f=tk.Frame(self.root,bg='white',padx=16,pady=9);f.pack(fill='both',expand=True,padx=1,pady=1)
  head=tk.Frame(f,bg='white');head.pack(fill='x',pady=(0,5))
  self.button(head,'×',self.hide,small=True).pack(side='left')
  tk.Label(head,text='英文  ⇄  中文',bg='white',fg='#5b6d78',font=(UI_FONT,10)).pack(side='left',expand=True)
  self.menu_button=self.button(head,'···',self.menu,small=True);self.menu_button.pack(side='right')
  self.root.bind('<Configure>',self.follow_settings)
  for target in [head]:
   target.bind('<ButtonPress-1>',lambda e:setattr(self,'drag',(e.x_root-self.root.winfo_x(),e.y_root-self.root.winfo_y())))
   target.bind('<B1-Motion>',lambda e:self.root.geometry(f'+{e.x_root-self.drag[0]}+{e.y_root-self.drag[1]}'))
  self.card=tk.Canvas(f,bg='white',highlightthickness=0,height=round(79*self.scale));self.card.pack(fill='x')
  self.card.bind('<Configure>',self.paint_card)
  self.card_inner=tk.Frame(self.card,bg='#d5f4fc')
  self.card_window=self.card.create_window(round(18*self.scale),round(7*self.scale),anchor='nw',window=self.card_inner)
  row=tk.Frame(self.card_inner,bg='#d5f4fc');row.pack(fill='x',pady=(0,1))
  self.entry=tk.Entry(row,bd=0,highlightthickness=0,bg='#d5f4fc',fg='#102e3b',font=(LATIN_FONT,19,'bold'),width=10,insertbackground='#17a7c6')
  self.entry.pack(side='left',fill='x',expand=True);self.entry.insert(0,'选词即可查');self.entry.bind('<Return>',lambda e:self.lookup(self.entry.get()))
  search=self.button(row,'⌕',lambda:self.lookup(self.entry.get()),small=True);search.config(bg='#d5f4fc');search.pack(side='right')
  pronunciations=tk.Frame(self.card_inner,bg='#d5f4fc');pronunciations.pack(fill='x')
  pronunciations.columnconfigure(0,weight=1,uniform='accent');pronunciations.columnconfigure(1,weight=1,uniform='accent')
  self.uk=self.pronunciation(pronunciations,'英',1);self.us=self.pronunciation(pronunciations,'美',2)
  self.uk.config(text='');self.us.config(text='')
  self.meta=tk.Label(f,text='',bg='white',fg='#87959e',font=(UI_FONT,9))
  nav=tk.Frame(f,bg='white');nav.pack(fill='x',pady=(6,0))
  favorite=self.button(nav,'♡ 收藏',self.save,small=True);favorite.config(font=(UI_FONT,9));favorite.pack(side='right')
  self.active_tab='definition';self.nav={};self.details_expanded=False
  for key,label in [('definition','释义'),('examples','例句'),('forms','词形')]:
   b=self.button(nav,label,lambda k=key:self.select_tab(k),small=True);b.pack(side='left',padx=(0,18),pady=(2,4));self.nav[key]=b
  tk.Frame(f,bg='#eef3f6',height=1).pack(fill='x')
  area=tk.Frame(f,bg='white');area.pack(fill='both',expand=True,pady=(3,4))
  style=ttk.Style();style.theme_use('clam');style.configure('Vertical.TScrollbar',troughcolor='white',background='#dceaf0',bordercolor='white',arrowcolor='#8da7b2',width=9)
  scroll=ttk.Scrollbar(area,orient='vertical');scroll.pack(side='right',fill='y')
  self.text=tk.Text(area,wrap='word',width=1,height=7,bg='white',fg='#243e4a',relief='flat',bd=0,padx=2,pady=6,spacing3=3,font=(UI_FONT,12),yscrollcommand=scroll.set)
  self.text.pack(fill='both',expand=True);scroll.config(command=self.text.yview)
  self.text.tag_configure('pos',foreground='#82949c',font=(LATIN_FONT,12,'italic'))
  self.text.tag_configure('heading',foreground='#168fae',font=(UI_FONT,10,'bold'),spacing1=6,spacing3=4)
  self.text.tag_configure('example',foreground='#3b7189')
  self.text.tag_configure('meaning',foreground='#203b49',font=(UI_FONT,12),spacing1=1,spacing3=6)
  self.text.tag_configure('label',foreground='#697e8a',font=(UI_FONT,9,'bold'),spacing1=5,spacing3=3)
  self.text.tag_configure('note',foreground='#738895',font=(UI_FONT,9),spacing1=2,spacing3=5)
  self.text.tag_configure('english',foreground='#536d7b',font=(UI_FONT,10),spacing1=2,spacing3=5)
  self.text.tag_configure('source',foreground='#8a9aa5',font=(UI_FONT,9),spacing1=7,spacing3=4)
  self.text.tag_configure('form_heading',foreground='#244859',font=(UI_FONT,11,'bold'),spacing1=7,spacing3=3)
  self.text.tag_configure('form_meaning',foreground='#3b5360',font=(UI_FONT,10),spacing3=3)
  self.more=self.button(f,'补充释义与来源  ▾',self.toggle_details,small=True);self.more.config(font=(UI_FONT,9),fg='#718b9b')
  bottom=self.bottom=tk.Frame(f,bg='white');bottom.pack(fill='x')
  self.status=tk.Label(bottom,text='选中单词后，点击查词' if IS_WINDOWS else '正在准备 Mac 划词服务，可先手动查词…',bg='white',fg='#6c8692',font=(UI_FONT,8),anchor='w',width=30);self.status.pack(side='left',fill='x',expand=True)
  self.status.bind('<Button-1>',lambda event:self.audio_sources() if self.speech.last_source else None)
  source_button=self.button(bottom,'来源 ↗',self.source_link,small=True);source_button.config(font=(UI_FONT,9),fg='#8599a5');source_button.pack(side='right')
  self.settext('选中英文，点击「查词」。\n\n完整离线释义，不调用第三方私有接口。')
  self.select_tab('definition')
  self.selection=tk.BooleanVar(value=self.preferences.get('selection',True));self.auto=tk.BooleanVar(value=self.preferences.get('copy_prompt',True))
  if self.selection.get():selection_enabled.set()
  self.selection.trace_add('write',lambda *args:self.save_preferences());self.auto.trace_add('write',lambda *args:self.save_preferences())
  if not testing:
   threading.Thread(target=hotkeys,daemon=True).start();threading.Thread(target=selection_monitor,daemon=True).start()
  self.root.bind('<Destroy>',lambda e:self.shutdown() if e.widget is self.root else None)
  from update_ui import UpdatePanel
  self.current_version=(BASE/'VERSION').read_text(encoding='utf-8').strip()
  self.updates=UpdatePanel(self,events,self.current_version,DATA,testing)
  self.root.after(25,self.poll)
  if not testing:self.root.after(180,self.warm_toolbar)
  if not IS_WINDOWS and not testing and not self.preferences.get('mac_guide_seen',False):self.root.after(600,self.mac_welcome)
 def open_mac_guide(self):
  import webbrowser
  guide=BASE/'docs'/'MAC_FIRST_RUN.html'
  webbrowser.open(guide.resolve().as_uri() if guide.is_file() else 'https://github.com/blueaaa333/woer-translator/blob/main/docs/MAC_FIRST_RUN.md')
 def mac_welcome(self):
  if getattr(self,'welcome_popup',None) and self.welcome_popup.winfo_exists():self.welcome_popup.lift();return
  popup=self.welcome_popup=tk.Toplevel(self.root);popup.title('Mac 首次运行指南');popup.configure(bg='white');popup.transient(self.root)
  body=tk.Frame(popup,bg='white',padx=24,pady=20);body.pack(fill='both',expand=True)
  tk.Label(body,text='欢迎使用沃尔翻译官',font=(UI_FONT,16,'bold'),bg='white',fg='#183d50',anchor='w').pack(fill='x',pady=(0,12))
  tk.Label(body,text='完整指南可随时从右上角「···」重新打开。\n\n本版本尚未取得 Apple 公证。遇到首次打开拦截时，请先核对下载来源与 SHA-256，再按指南处理；并不是每个人都需要运行终端命令。\n\n划词需要在系统设置中允许辅助功能与输入监控，未授权也可手动输入或主动复制查询。',wraplength=350,justify='left',bg='white',fg='#405f70',font=(UI_FONT,11)).pack(fill='x',pady=(0,14))
  self.button(body,'阅读完整首次运行指南 ↗',self.open_mac_guide,small=True).pack(anchor='w',pady=8)
  self.button(body,'启用 Mac 划词权限',lambda:mac.request_permissions(events),small=True).pack(anchor='w',pady=5)
  def done():
   if not self.testing:self.preferences['mac_guide_seen']=True;self.save_preferences()
   popup.destroy()
  self.button(body,'开始查词',done).pack(anchor='e',pady=(8,0));popup.protocol('WM_DELETE_WINDOW',done)
  popup.update_idletasks();popup.geometry(f'+{max(20,self.root.winfo_x()+15)}+{max(40,self.root.winfo_y()+15)}')
  self.watch_mac_window(popup)
 def on_error(self,exc,value,tb):
  write_error('interface',exc,value,tb)
  try:self.status.config(text='操作未完成，错误已记录')
  except (AttributeError,tk.TclError):pass
 def shutdown(self):
  for callback in self.root.tk.call('after','info'):
   try:self.root.after_cancel(callback)
   except tk.TclError:pass
  if getattr(self,'updates',None):self.updates.close()
  self.audio_serial+=1
  self.speech.close()
  if not self.testing:stop_children()
  winsound.PlaySound(None,0)
 def warm_toolbar(self):
  if self.popup and self.popup.winfo_exists():return
  self._warming=True
  try:self.prompt('warmup')
  finally:self._warming=False;self.last_prompt=''
 def paint_card(self,event):
  c=self.card;w,h=event.width,event.height;r=round(18*self.scale)
  c.delete('background')
  c.create_polygon(r,0,w-r,0,w,0,w,r,w,h-r,w,h,w-r,h,r,h,0,h,0,h-r,0,r,0,0,fill='#d5f4fc',smooth=True,splinesteps=32,outline='',tags='background')
  c.tag_lower('background');c.itemconfigure(self.card_window,width=max(1,w-round(36*self.scale)))
 def pronunciation(self,parent,label,accent):
  row=tk.Frame(parent,bg='#d5f4fc');row.grid(row=0,column=accent-1,sticky='nsew',padx=(0,4),pady=1)
  icon=tk.Canvas(row,width=round(17*self.scale),height=round(17*self.scale),bg='#d5f4fc',highlightthickness=0,cursor='hand2');icon.pack(side='left',padx=(0,5))
  sc=self.scale*.8
  icon.create_polygon(*[v*sc for v in [2,8,6,8,11,4,11,17,6,13,2,13]],fill='',outline='#19adc9',width=2*sc)
  icon.create_arc(5*sc,3*sc,18*sc,18*sc,start=-55,extent=110,style='arc',outline='#19adc9',width=1.5*sc)
  icon.bind('<Button-1>',lambda e:self.speak(accent))
  tk.Label(row,text=label,bg='#d5f4fc',fg='#376476',font=(UI_FONT,9)).pack(side='left',padx=(0,7))
  phon=tk.Label(row,text='',bg='#d5f4fc',fg='#5a8294',anchor='w',font=(LATIN_FONT,9),wraplength=round(121*self.scale),cursor='hand2');phon.pack(side='left',fill='x',expand=True);phon.bind('<Button-1>',lambda e:self.speak(accent))
  return phon
 def source_link(self):
  import webbrowser
  webbrowser.open(self.result['community'][0]['url'] if self.result and self.result.get('community') else 'https://kaikki.org/dictionary/English/')
 def select_tab(self,key):
  self.active_tab=key
  for k,b in self.nav.items():b.config(fg='#119dbb' if k==key else '#637681',font=(UI_FONT,12,'bold' if k==key else 'normal'))
  if self.result:self.render()
 def render(self):
  self.more.pack_forget()
  if self.active_tab=='examples':body=examples_text(self.result)
  elif self.active_tab=='forms':
   self.render_forms();return
  else:
   self.render_definition();return
  self.settext(body)
 def render_forms(self):
  rows=form_rows(self.lexicon,self.result)
  self.text.config(state='normal');self.text.delete('1.0','end');group=None
  for row in rows:
   if row['base']!=group:
    group=row['base'];self.text.insert('end',group+' 的词形\n','source')
   self.text.insert('end',row['label']+'  '+row['form']+('  · 当前词' if row['current'] else '')+'\n','form_heading')
   self.text.insert('end',row['meaning']+'\n','form_meaning')
   if row['usage']:self.text.insert('end',row['usage']+'\n','note')
  if not rows:self.text.insert('end','当前来源未提供常用词形变化。','note')
  self.text.config(state='disabled');self.text.yview_moveto(0)
 def toggle_details(self):
  self.details_expanded=not self.details_expanded;self.render_definition()
  if self.details_expanded:self.text.see('supplement_start')
 def render_definition(self):
  sections=definition_sections(self.result)
  self.text.config(state='normal');self.text.delete('1.0','end')
  for section in sections['primary']:self.text.insert('end',section['text']+'\n',section['kind'])
  self.text.mark_set('supplement_start','end-1c');self.text.mark_gravity('supplement_start','left')
  if self.details_expanded:
   self.text.insert('end','补充释义\n','label')
   for section in sections['details']:self.text.insert('end',section['text']+'\n',section['kind'])
  if sections['sources']:self.text.insert('end','来源：'+' · '.join(sections['sources'])+'\n','source')
  self.text.config(state='disabled');self.text.yview_moveto(0)
  if sections['details']:
   self.more.config(text='收起补充释义与来源  ▴' if self.details_expanded else '补充释义与来源  ▾')
   self.more.pack(before=self.bottom,anchor='w',pady=(1,3))
  else:self.more.pack_forget()
 def button(self,parent,label,command,small=False):
  b=tk.Button(parent,text=label,command=command,bg='white' if small else '#eafaff',fg='#536783' if small else '#149fbc',activebackground='#e4eeff',activeforeground='#2463db',relief='flat',bd=0,padx=4 if small else 8,pady=1 if small else 4,cursor='hand2',font=(UI_FONT,10))
  b.bind('<Enter>',lambda e:b.config(bg='#eaf2ff'));b.bind('<Leave>',lambda e:b.config(bg='white' if small else '#eafaff'))
  return b
 def hide(self):
  self.root.withdraw()
  self.close_floating()
 def read_preferences(self):
  return self.preference_store.read()
 def save_preferences(self):
  data=dict(self.preferences,auto_read=self.accent!=0,accent=self.accent,preferred_accent=self.preferred_accent,selection=self.selection.get(),copy_prompt=self.auto.get())
  self.preferences=self.preference_store.write(data)
 def set_accent(self,accent):
  self.accent=accent
  if accent:self.preferred_accent=accent
  self.save_preferences()
 def close_floating(self,reason='explicit'):
  self.selection_version+=1
  if self.popup and self.popup.winfo_exists():
   record_stage('popup_closed',reason=reason,id=self.pending_source['id'] if self.pending_source else None,age_ms=round((time.monotonic()-self.last_prompt_time)*1000))
  for win in (self.popup,self.settings_popup):
   if win and win.winfo_exists():win.destroy()
  self.pending_source=None
 def dismiss_from_input(self,detail):
  if detail and self.pending_source and detail['at']<=self.pending_source['emitted']:
   record_stage('clear_ignored_stale',reason=detail['reason'],id=self.pending_source['id']);return
  self.close_floating(detail['reason'] if detail else 'explicit')
 def round_window(self,win,radius=13):
  if not IS_WINDOWS:return
  win.update_idletasks();hwnd=u.GetParent(win.winfo_id())
  gdi=C.windll.gdi32
  gdi.CreateRoundRectRgn.argtypes=[C.c_int]*6;gdi.CreateRoundRectRgn.restype=C.c_void_p
  u.SetWindowRgn.argtypes=[C.c_void_p,C.c_void_p,C.c_int];gdi.DeleteObject.argtypes=[C.c_void_p]
  r=round(radius*self.scale);region=gdi.CreateRoundRectRgn(0,0,win.winfo_width()+1,win.winfo_height()+1,r*2,r*2)
  if not u.SetWindowRgn(hwnd,region,True):gdi.DeleteObject(region)
 def menu(self):
  if self.settings_popup and self.settings_popup.winfo_exists():self.settings_popup.destroy();return
  m=self.settings_popup=tk.Toplevel(self.root);m.withdraw();m.overrideredirect(True);m.attributes('-topmost',True);m.configure(bg='#dce5ec')
  f=tk.Frame(m,bg='white',padx=round(14*self.scale),pady=round(12*self.scale));f.pack(fill='both',expand=True,padx=1,pady=1)
  head=tk.Frame(f,bg='white');head.pack(fill='x',pady=(0,7))
  tk.Label(head,image=self.brand_icon,bg='white').pack(side='left',padx=(0,7))
  tk.Label(head,text='沃尔翻译官',bg='white',fg='#23475b',font=(UI_FONT,11,'bold')).pack(side='left')
  self.button(head,'×',m.destroy,small=True).pack(side='right')
  def section(text):tk.Label(f,text=text,bg='white',fg='#8a9aa6',font=(UI_FONT,9),anchor='w').pack(fill='x',pady=(9,5))
  def toggle(label,getter,action):
   row=tk.Frame(f,bg='white');row.pack(fill='x',pady=4)
   tk.Label(row,text=label,bg='white',fg='#405969',font=(UI_FONT,10)).pack(side='left')
   def click():action();render()
   b=tk.Button(row,command=click,bd=0,relief='flat',cursor='hand2',padx=9,pady=3,font=(UI_FONT,9))
   def render():
    enabled=getter();b.config(text='开启  ●' if enabled else '○  关闭',bg='#e2f1f4' if enabled else '#f0f3f6',fg='#28576b' if enabled else '#81909c',activebackground='#dfebef')
   render();b.pack(side='right');return b
  section('划词与复制')
  def select_toggle():
   self.selection.set(not self.selection.get())
   selection_enabled.set() if self.selection.get() else selection_enabled.clear()
  toggle('选中后显示浮条',self.selection.get,select_toggle)
  toggle('复制后显示浮条',self.auto.get,lambda:self.auto.set(not self.auto.get()))
  tk.Frame(f,bg='#edf1f4',height=1).pack(fill='x',pady=(10,2))
  section('发音偏好')
  def recordings_toggle():
   self.preferences['prefer_recordings']=not self.preferences.get('prefer_recordings',True);self.save_preferences()
  toggle('优先真人发音（联网）',lambda:self.preferences.get('prefer_recordings',True),recordings_toggle)
  self.button(f,'发音来源与许可 ↗',self.audio_sources,small=True).pack(anchor='w',pady=3)
  toggle('查词后自动朗读',lambda:self.accent!=0,lambda:self.set_accent(0 if self.accent else self.preferred_accent))
  row=tk.Frame(f,bg='white');row.pack(fill='x',pady=(5,8))
  tk.Label(row,text='默认口音',bg='white',fg='#7c8d9a',font=(UI_FONT,9)).pack(side='left')
  def choose(accent):
   self.preferred_accent=accent
   if self.accent:self.accent=accent
   self.save_preferences();paint_accents()
  uk=self.button(row,'英式',lambda:choose(1),small=True);uk.pack(side='right',padx=(8,0))
  us=self.button(row,'美式',lambda:choose(2),small=True);us.pack(side='right')
  def paint_accents():
   for button,accent in ((uk,1),(us,2)):
    selected=self.preferred_accent==accent
    button.config(bg='#e7f1f4' if selected else 'white',fg='#23475b' if selected else '#5b6d78')
  for button in (uk,us):
   button.bind('<Enter>',lambda e:paint_accents());button.bind('<Leave>',lambda e:paint_accents())
  paint_accents()
  if IS_WINDOWS:self.button(f,'下载英美离线语音（约150 MB）',self.install_voices,small=True).pack(anchor='w',pady=5)
  else:
   self.button(f,'Mac 首次运行指南 ↗',self.open_mac_guide,small=True).pack(anchor='w',pady=5)
   self.button(f,'启用 macOS 划词权限',lambda:mac.request_permissions(events),small=True).pack(anchor='w',pady=5)
  section('软件更新')
  def update_toggle():
   self.preferences['check_updates']=not self.preferences.get('check_updates',True);self.save_preferences()
  toggle('自动检查更新',lambda:self.preferences.get('check_updates',True),update_toggle)
  self.button(f,'检查更新 · v'+self.current_version,lambda:self.updates.check(True),small=True).pack(anchor='w',pady=5)
  tk.Frame(f,bg='#edf1f4',height=1).pack(fill='x',pady=(3,7))
  footer=tk.Frame(f,bg='white');footer.pack(fill='x')
  self.button(footer,'关闭菜单',m.destroy,small=True).pack(side='left')
  quit=self.button(footer,'退出应用',self.root.destroy,small=True);quit.config(fg='#8d6669');quit.pack(side='right')
  m.update_idletasks();self.settings_size=(max(round(258*self.scale),f.winfo_reqwidth()+2),f.winfo_reqheight()+2)
  from menu_layout import show_settings
  show_settings(self,m)
  self.watch_mac_window(m)
  m.bind('<Escape>',lambda e:m.destroy())
 def follow_settings(self,event):
  if event.widget is self.root:self.position_settings()
 def position_settings(self):
  m=self.settings_popup
  if not m or not m.winfo_exists() or not hasattr(self,'settings_size'):return
  width,height=self.settings_size;b=self.menu_button
  right=b.winfo_rootx()+b.winfo_width();top=b.winfo_rooty();bottom=top+b.winfo_height()
  rect=self.work_area(right,top);gap=round(5*self.scale)
  x=max(rect.left+4,min(right-width,rect.right-width-4))
  y=bottom+gap if bottom+gap+height<=rect.bottom-4 else top-gap-height
  y=max(rect.top+4,min(y,rect.bottom-height-4))
  m.geometry(f'{width}x{height}{x:+d}{y:+d}')
  if not IS_WINDOWS:self.sync_mac_regions()
 def sync_mac_regions(self):
  if IS_WINDOWS:return
  regions=[]
  for win in (self.popup,self.settings_popup,getattr(self,'welcome_popup',None)):
   if win and win.winfo_exists() and win.winfo_ismapped():
    regions.append(dict(left=win.winfo_rootx(),top=win.winfo_rooty(),right=win.winfo_rootx()+win.winfo_width(),bottom=win.winfo_rooty()+win.winfo_height()))
  mac.update_regions(regions)
 def watch_mac_window(self,win):
  if IS_WINDOWS:return
  win.bind('<Configure>',lambda e:self.sync_mac_regions() if e.widget is win else None,add='+')
  win.bind('<Destroy>',lambda e:self.root.after_idle(self.sync_mac_regions) if e.widget is win else None,add='+')
  self.sync_mac_regions()
 def work_area(self,x,y):
  if not IS_WINDOWS:
   from types import SimpleNamespace
   return mac.work_area(x,y) or SimpleNamespace(left=0,top=0,right=self.root.winfo_screenwidth(),bottom=self.root.winfo_screenheight())
  from ctypes import wintypes
  class MONITORINFO(C.Structure):
   _fields_=[('cbSize',wintypes.DWORD),('rcMonitor',wintypes.RECT),('rcWork',wintypes.RECT),('dwFlags',wintypes.DWORD)]
  u.MonitorFromPoint.argtypes=[wintypes.POINT,wintypes.DWORD];u.MonitorFromPoint.restype=C.c_void_p
  u.GetMonitorInfoW.argtypes=[C.c_void_p,C.POINTER(MONITORINFO)]
  info=MONITORINFO();info.cbSize=C.sizeof(info)
  monitor=u.MonitorFromPoint(wintypes.POINT(x,y),2);u.GetMonitorInfoW(monitor,C.byref(info));return info.rcWork
 def position(self,win,width,height,x=None,y=None,physical=False):
  if not physical:width,height=round(width*self.scale),round(height*self.scale)
  x=self.root.winfo_pointerx() if x is None else x;y=self.root.winfo_pointery() if y is None else y
  rect=self.work_area(x,y)
  x=max(rect.left+4,min(x+10,rect.right-width-4));y=y+24 if y+height+30<rect.bottom else y-height-12
  y=max(rect.top+4,min(y,rect.bottom-height-4));win.geometry(f'{width}x{height}{x:+d}{y:+d}')
 def prompt(self,s,source=None):
  s=normalize_query(s)
  if not source and not valid_query(s):return
  if self.popup and self.popup.winfo_exists():
   # A clipboard notification has no selection identity. It must neither supply
   # a word for this gesture nor recreate its strip at the current pointer.
   if not source and self.pending_source:
    record_stage('clipboard_ignored_for_selection',id=self.pending_source['id']);return
   if s and s==self.last_prompt and not source:return
   self.popup.destroy()
  self.selection_version+=1
  self.pending_source=source;self.last_prompt=s;self.last_prompt_time=time.monotonic()
  p=self.popup=tk.Toplevel(self.root);p.withdraw();p.overrideredirect(True);p.attributes('-topmost',True);p.configure(bg='#dce7fb')
  bar=tk.Frame(p,bg='white',padx=8,pady=5);bar.pack(fill='both',expand=True,padx=1,pady=1)
  def choose(accent=None):
   x,y=p.winfo_x(),p.winfo_y();p.withdraw()
   anchor=(x-10,y-24)
   if source:self.query_source(source,accent,anchor=anchor)
   elif s:self.lookup(s,accent,anchor=anchor)
   p.destroy()
  def copy():
   if source:self.query_source(source,0,copy_only=True)
   elif s:self.root.clipboard_clear();self.root.clipboard_append(s)
   p.destroy()
  tk.Label(bar,image=self.brand_icon,bg='white').pack(side='left',padx=(2,7))
  query=self.button(bar,'⌕ 查词',choose);query.config(bg='#edf4f8',fg='#163c55',font=(UI_FONT,10,'bold'));query.bind('<Enter>',lambda e:query.config(bg='#dfedf4'));query.bind('<Leave>',lambda e:query.config(bg='#edf4f8'));query.pack(side='left',padx=2)
  self.button(bar,'🔊 英',lambda:choose(1),small=True).pack(side='left',padx=3)
  self.button(bar,'🔊 美',lambda:choose(2),small=True).pack(side='left',padx=3)
  self.button(bar,'复制',copy,small=True).pack(side='left',padx=3)
  self.button(bar,'×',p.destroy,small=True).pack(side='left',padx=3)
  if getattr(self,'_warming',False):p.update_idletasks();p.destroy();return
  p.update_idletasks();self.position(p,max(round(290*self.scale),bar.winfo_reqwidth()+2),max(round(43*self.scale),bar.winfo_reqheight()+2),x=source['x'] if source else None,y=source['y'] if source else None,physical=True)
  # A mouse click on the strip must leave focus/selection in the source app.
  # Apply NOACTIVATE before mapping, rather than after the first visible frame.
  if IS_WINDOWS:
   hwnd=u.GetParent(p.winfo_id());ex=u.GetWindowLongW(hwnd,-20);u.SetWindowLongW(hwnd,-20,ex|0x80|0x08000000)
   p.deiconify();p.update_idletasks();u.ShowWindow(hwnd,4)
  else:
   try:self.root.tk.call('::tk::unsupported::MacWindowStyle','style',p._w,'help','noActivates')
   except tk.TclError:pass
   p.deiconify();p.update_idletasks()
  self.round_window(p,14)
  self.watch_mac_window(p)
  if source:record_stage('popup_shown',id=source['id'],latency_ms=round(time.time()*1000-source['emitted']))
  if source and IS_WINDOWS:
   def check_visibility():
    if not p.winfo_exists():return
    from ctypes import wintypes
    u.WindowFromPoint.argtypes=[wintypes.POINT];u.WindowFromPoint.restype=C.c_void_p
    top=u.WindowFromPoint(wintypes.POINT(p.winfo_rootx()+p.winfo_width()//2,p.winfo_rooty()+p.winfo_height()//2))
    top_pid=wintypes.DWORD();u.GetWindowThreadProcessId.argtypes=[C.c_void_p,C.POINTER(wintypes.DWORD)];u.GetWindowThreadProcessId(top,C.byref(top_pid))
    record_stage('popup_visibility',id=source['id'],mapped=bool(p.winfo_ismapped()),covered=top_pid.value!=os.getpid(),top_pid=top_pid.value)
   p.after(90,check_visibility)
  p.bind('<Enter>',lambda e:setattr(p,'hovered',True));p.bind('<Leave>',lambda e:setattr(p,'hovered',False))
  def expire():
   if p.winfo_exists():
    if getattr(p,'hovered',False):p.after(2500,expire)
    else:p.destroy()
  p.after(12000,expire)
 def query_source(self,source,accent=None,copy_only=False,anchor=None):
  if not IS_WINDOWS:return self.query_source_macos(source,accent,copy_only,anchor)
  # Only after the user clicks Query/Copy: activate the captured source, then copy.
  u.IsWindow.argtypes=[C.c_void_p];u.SetForegroundWindow.argtypes=[C.c_void_p];u.GetForegroundWindow.restype=C.c_void_p
  hwnd=source['hwnd'];version=self.selection_version
  if not copy_only:self.reset_result('正在读取本次选中的单词…')
  record_stage('query_requested',id=source['id'])
  def failed():
   if version!=self.selection_version:return
   record_stage('query_failed',id=source['id'])
   if not copy_only:self.reset_result('未能读取本次选区，请重新选中后点击查词。')
   else:self.status.config(text='未能复制本次选区，请重新选中后重试')
   if anchor is not None:self.position(self.root,380,420,x=anchor[0],y=anchor[1])
   self.show()
  if not u.IsWindow(hwnd):failed();return
  if u.GetForegroundWindow()!=hwnd:u.SetForegroundWindow(hwnd)
  def perform():
   if version!=self.selection_version:return
   if u.GetForegroundWindow()!=hwnd:failed();return
   self.clipboard_suppress_until=time.monotonic()+1.5
   # An explicit query may replace clipboard text. Clear old data first so
   # format/owner notifications cannot make a previous word look like a copy.
   self.root.clipboard_clear();self.seq=clipboard_sequence();before=self.seq
   u.keybd_event(0x11,0,0,0);u.keybd_event(0x43,0,0,0);u.keybd_event(0x43,0,2,0);u.keybd_event(0x11,0,2,0)
   def read(attempt=0):
    if version!=self.selection_version:return
    if u.GetClipboardSequenceNumber()!=before:
     word=normalize_query(clipboard())
     if valid_query(word):
      self.seq=clipboard_sequence()
      record_stage('query_copied',id=source['id'])
      if not copy_only:self.lookup(word,accent,anchor=anchor)
      return
    if attempt<15:self.root.after(35,lambda:read(attempt+1))
    else:failed()
   self.root.after(25,read)
  self.root.after(45,perform)
 def reset_result(self,message):
  self.word='';self.result=None;self.online=None
  self.more.pack_forget();self.details_expanded=False
  self.entry.delete(0,'end');self.uk.config(text='');self.us.config(text='')
  self.meta.config(text='本次选区');self.status.config(text=message)
  self.settext(message)
 def settext(self,s,target=None):
  s=simplified(s)
  target=target or self.text;target.config(state='normal');target.delete('1.0','end');target.insert('1.0',s)
  for m in re.finditer(r'(?m)^(?:n|v|adj|adv|vt|vi|prep|pron|conj|interj|num|det|aux)\.',s):
   target.tag_add('pos',f'1.0+{m.start()}c',f'1.0+{m.end()}c')
  for m in re.finditer(r'(?m)^(?:英文释义|本地补充|词形变化|考试标签|常用义.*|完整分义.*)$',s):
   target.tag_add('heading',f'1.0+{m.start()}c',f'1.0+{m.end()}c')
  target.config(state='disabled');target.yview_moveto(0)
 def show(self):
  self.root.deiconify();self.root.lift();self.root.attributes('-topmost',True);self.root.after(400,lambda:self.root.attributes('-topmost',False))
 def lookup(self,s,accent=None,anchor=None):
  s=normalize_query(s).lower()
  if not valid_query(s):return
  self.selection_version+=1
  self.word=s;self.entry.delete(0,'end');self.entry.insert(0,s);self.entry.icursor('end')
  self.result=self.lexicon.lookup(s)
  self.online=None
  phonetics=phonetic_labels(self.result)
  self.uk.config(text=phonetics['uk']);self.us.config(text=phonetics['us'])
  self.meta.config(text=word_form_note(self.result) or ('复合词' if self.result.get('compounds') else ''))
  self.details_expanded=False;self.active_tab='definition';self.select_tab('definition')
  self.status.config(text='正在补充在线英汉释义…' if self.use_online else '离线释义')
  self.card_height=420
  if anchor is None:self.position(self.root,380,self.card_height)
  else:self.position(self.root,380,self.card_height,x=anchor[0],y=anchor[1])
  self.show()
  chosen=self.accent if accent is None else accent
  if chosen:self.speak(chosen)
 def audio_sources(self):
  import webbrowser
  path=self.speech.recordings.attribution_path()
  webbrowser.open(path.resolve().as_uri() if path.is_file() else 'https://github.com/blueaaa333/woer-translator/blob/main/docs/SPEECH.md')
 def speak(self,accent):
  if not self.word:return
  self.audio_serial+=1;serial=self.audio_serial;word=self.word
  winsound.PlaySound(None,0)
  self.speech.prefer_recordings=self.preferences.get('prefer_recordings',True)
  self.status.config(text='正在准备'+('英式' if accent==1 else '美式')+'发音…')
  def job():
   try:
    with self.audio_lock:
     if serial!=self.audio_serial:return
     audio=self.speech.render(word,accent)
     if serial!=self.audio_serial:return
     winsound.PlaySound(str(audio),winsound.SND_FILENAME)
     if serial==self.audio_serial:events.put(('status',('英式' if accent==1 else '美式')+('真人发音 · 点击查看来源' if self.speech.last_source else '合成发音 · 播放完毕')))
   except Exception as exc:
    if serial==self.audio_serial:events.put(('status',str(exc) if isinstance(exc,SpeechUnavailable) else '发音未能播放，请检查语音设置'))
  threading.Thread(target=job,daemon=True).start()
 def install_voices(self):
  if getattr(self,'voice_installing',False):return
  self.voice_installing=True;self.status.config(text='正在下载英美离线语音，首次约150 MB…')
  def job():
   try:
    from scripts.setup_speech import install
    install(DATA.resolve());events.put(('voices_ready','英美离线语音已就绪，可点击喇叭播放'))
   except Exception:events.put(('voices_ready','语音下载未完成，请检查网络后重试'))
  threading.Thread(target=job,daemon=True).start()
 def query_source_macos(self,source,accent=None,copy_only=False,anchor=None):
  version=self.selection_version
  if not copy_only:self.reset_result('正在读取本次选中的单词…')
  self.clipboard_suppress_until=time.monotonic()+3
  self.mac_query=dict(version=version,accent=accent,copy_only=copy_only,anchor=anchor)
  if not mac.query_selection(source,version):
   self.finish_mac_query(dict(version=version,error='Mac 取词服务未就绪，请稍后重试或手动查词。'))
  def timeout():
   if getattr(self,'mac_query',None) and self.mac_query['version']==version:
    self.finish_mac_query(dict(version=version,error='取词超时，请重新选词或手动输入；窗口仍可继续使用。'))
  self.root.after(3500,timeout)
 def finish_mac_query(self,value):
  request=getattr(self,'mac_query',None)
  if not request or value['version']!=request['version']:return
  self.mac_query=None
  if value['version']!=self.selection_version:return
  anchor=request['anchor'];word=normalize_query(value.get('word',''))
  if valid_query(word):
   self.seq=clipboard_sequence()
   if not request['copy_only']:self.lookup(word,request['accent'],anchor=anchor)
  else:
   message=value.get('error','未能读取本次选区，请重新选词。')
   if request['copy_only']:self.status.config(text=message)
   else:self.reset_result(message)
   if anchor:self.position(self.root,380,420,x=anchor[0],y=anchor[1])
   self.show()
 def save(self):
  if not self.word:return
  p=DATA/'生词本.txt';existing=p.read_text(encoding='utf-8') if p.exists() else ''
  if self.word not in existing.splitlines():p.write_text(existing+self.word+'\n',encoding='utf-8')
  self.status.config(text='已加入生词本')
 def poll(self):
  try:
   seq=clipboard_sequence()
   if seq!=self.seq:
    self.seq=seq
    if self.auto.get() and time.monotonic()>=self.clipboard_suppress_until:self.prompt(clipboard())
   deadline=time.monotonic()+.008
   while not events.empty() and time.monotonic()<deadline:
    kind,value=events.get_nowait()
    if kind=='clear':self.dismiss_from_input(value)
    elif kind=='gesture':self.prompt('',value)
    elif kind=='resolved':
     identifier,word=value
     if self.pending_source and self.pending_source['id']==identifier:self.pending_source['word']=word
    elif kind=='lookup':self.lookup(value)
    elif kind=='hotkey_source':
     self.selection_version+=1;self.query_source(value,anchor=(value['x']-10,value['y']-24))
    elif kind=='mac_query_result':self.finish_mac_query(value)
    elif kind=='mac_bridge_ready':self.native_ready=True;self.sync_mac_regions()
    elif kind=='app_update':self.updates.receive(value)
    elif kind=='voices_ready':self.voice_installing=False;self.status.config(text=value)
    elif kind=='selection':
     if self.selection.get():self.prompt(value)
    elif kind=='show':self.show();self.status.config(text=value)
    else:self.status.config(text=value)
  except Exception:
   self.on_error(*sys.exc_info())
  finally:
   try:self.root.after(25,self.poll)
   except tk.TclError:pass
def main():
 if '--check-menu-layout' in sys.argv:
  from menu_layout_checks import frozen_check
  frozen_check(App,sys.argv[sys.argv.index('--check-menu-layout')+1]);return
 if '--smoke-test' in sys.argv:
  from smoke_test import run
  try:report=run(BASE)
  except Exception as error:report={'error':str(error)}
  encoded=json.dumps(report,ensure_ascii=False)
  if '--smoke-report' in sys.argv:Path(sys.argv[sys.argv.index('--smoke-report')+1]).write_text(encoded,encoding='utf-8')
  if sys.stdout:print(encoded)
  raise SystemExit(1 if 'error' in report else 0)
 if IS_WINDOWS:
  mutex=k.CreateMutexW(None,False,'QingCiDesktopDictionaryV1')
  if k.GetLastError()==183:
   hwnd=u.FindWindowW(None,'沃尔翻译官');u.ShowWindow(hwnd,9);u.SetForegroundWindow(hwnd);return
 else:
  if not mac.single_instance(DATA):return
 try:
  app=App()
  # Real startup is checked with the same listeners and mainloop as user launches.
  if '--gui-self-test' in sys.argv:
   from scripts.check_runtime import schedule
   schedule(app,Path(sys.argv[sys.argv.index('--gui-report')+1]))
  app.root.mainloop()
 except Exception:
  exc,value,tb=sys.exc_info();write_error('startup',exc,value,tb)
  if IS_WINDOWS:u.MessageBoxW(None,'启动失败，详细信息已写入：\n'+str(DATA/'application-errors.log'),'沃尔翻译官',16)
  else:mac.show_error('启动失败，详细信息已写入：'+str(DATA/'application-errors.log'))
if __name__=='__main__':main()
