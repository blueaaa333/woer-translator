"""UI-side macOS services; system monitoring runs in a separate process."""
import os,re,subprocess,threading
from types import SimpleNamespace
from mac_bridge import MacBridge

_client=None
_instance_file=None

def clipboard_sequence():return _client.clipboard()[0] if _client else 0

def clipboard_text():return _client.clipboard()[1] if _client else ''

def request_permissions(events):
    if _client and _client.send('permissions'):
        events.put(('status','请在系统设置中允许辅助功能和输入监控，再返回阅读页面选词。'))
    else:events.put(('status','Mac 服务正在启动，请稍后再点击启用划词权限。'))

def query_selection(source,version):
    return bool(_client and _client.send('query',pid=source['pid'],version=version))

def monitor(events,enabled,stop):
    global _client
    from app_paths import user_data_dir
    _client=MacBridge(events,enabled,stop,user_data_dir())
    _client.run()

def stop_monitor():
    if _client:
        _client.stop.set()
        if _client.process and _client.process.poll() is None:
            try:_client.process.terminate()
            except OSError:pass

def ready():return bool(_client and _client.ready.is_set())

def update_regions(regions):
    if _client:_client.send('regions',regions=regions)

def work_area(x,y):
    areas=[SimpleNamespace(**r) for r in _client.areas()] if _client else []
    for area in areas:
        if area.left<=x<area.right and area.top<=y<area.bottom:return area
    return min(areas,key=lambda r:max(r.left-x,0,x-r.right)**2+max(r.top-y,0,y-r.bottom)**2) if areas else None

def single_instance(data):
    global _instance_file
    import fcntl
    _instance_file=(data/'application.lock').open('a+')
    try:fcntl.flock(_instance_file,fcntl.LOCK_EX|fcntl.LOCK_NB);return True
    except BlockingIOError:
        from AppKit import NSRunningApplication,NSApplicationActivateIgnoringOtherApps
        for app in NSRunningApplication.runningApplicationsWithBundleIdentifier_('io.github.blueaaa333.woer-translator'):
            if app.processIdentifier()!=os.getpid():app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        return False

def show_error(message):
    from AppKit import NSAlert
    alert=NSAlert.alloc().init();alert.setMessageText_('沃尔翻译官');alert.setInformativeText_(message);alert.runModal()

def choose_voice(lines,accent):
    expected='en_GB' if accent==1 else 'en_US'
    for line in lines.splitlines():
        match=re.match(r'(.+?)\s+(en_[A-Z]{2})\s+#',line)
        if match and match[2]==expected:return match[1].strip()
    return None

class MacSound:
    SND_FILENAME=0
    def __init__(self):self.process=None;self.lock=threading.Lock()
    def PlaySound(self,path,flags=0):
        with self.lock:
            if self.process and self.process.poll() is None:self.process.terminate()
            self.process=subprocess.Popen(['/usr/bin/afplay',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL) if path else None
            process=self.process
        if process:process.wait()
sound=MacSound()
