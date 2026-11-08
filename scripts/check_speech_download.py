"""Check real download menu routing without network, playback, or global listeners."""
import sys,tempfile,time,threading,json
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import App
from menu_layout_checks import descendants
app=App(testing=True)
try:
 app.save_preferences=Mock()
 app.root.update();app.menu();app.root.update()
 button=next(w for w in descendants(app.settings_popup) if w.winfo_class()=='Button' and w.cget('text').startswith('下载／升级英美'))
 x=button.winfo_rootx()+button.winfo_width()//2;y=button.winfo_rooty()+button.winfo_height()//2
 assert app.root.winfo_containing(x,y)==button, 'Download control is covered or outside its native region'
 started=threading.Event();release=threading.Event();calls=[]
 def install(target,progress=None):
  calls.append(target);started.set();progress('正在下载测试文件 1/2');release.wait(3)
  if len(calls)==1:raise TimeoutError('private/path/not/shown')
 def wait_for(predicate):
  end=time.monotonic()+4
  while time.monotonic()<end:
   app.root.update()
   if predicate():return
   time.sleep(.01)
  raise AssertionError('Dialog did not reach expected state')
 with patch('scripts.setup_speech.install',side_effect=install),patch('webbrowser.open') as browser:
  button.invoke();wait_for(started.is_set)
  window=app.voice_download_window
  assert window.winfo_ismapped() and not app.settings_popup.winfo_exists()
  app.install_voices();assert len(calls)==1, 'Must not start duplicate downloads'
  window.withdraw();app.install_voices();app.root.update();assert window.winfo_ismapped()
  release.set();wait_for(lambda:not window._speech_state['running'])
  text=window._speech_status.cget('text');assert 'TimeoutError' in text and 'private' not in text
  retry=next(w for w in descendants(window) if w.winfo_class()=='Button' and w.cget('text')=='开始／重试下载')
  retry.invoke();wait_for(lambda:not window._speech_state['running'])
  assert '安装完成' in window._speech_status.cget('text') and len(calls)==2
  browser.assert_not_called()
 print(json.dumps(dict(menu_hit_target='ok',deduplicated=True,network_error_visible=True,retry='ok',no_browser_open=True)))
finally:app.root.destroy()
