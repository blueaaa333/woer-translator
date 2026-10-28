"""Bounded, disposable accessibility checks. Never synthesize Copy to detect selection."""
import base64,queue,subprocess,sys,threading,os
from pathlib import Path

def source_is_active(source):
    if sys.platform!='win32':return True
    import ctypes
    user=ctypes.windll.user32;user.GetForegroundWindow.restype=ctypes.c_void_p
    return user.GetForegroundWindow()==source['hwnd']

def check_selection(base,source,timeout=.65):
    if sys.platform=='win32':
        command=[str(Path(base)/'DesktopBridge.exe'),'verify',str(source['pid']),str(source['hwnd']),str(source['x']),str(source['y'])]
    else:
        command=[sys.executable]
        if not getattr(sys,'frozen',False):command.append(str(Path(base)/'app.py'))
        command+=['--mac-verify-selection',str(source['pid']),str(source['x']),str(source['y'])]
    expected=source.get('clipboard_word','')
    value=base64.b64encode(expected.encode()).decode()+'\n'
    process=None
    try:
        process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                                 creationflags=0x08000000 if sys.platform=='win32' else 0)
        output,_=process.communicate(value.encode(),timeout=timeout)
        return process.returncode==0 and output.strip()==b'SELECTED'
    except (OSError,subprocess.TimeoutExpired):return False
    finally:
        if process and process.poll() is None:
            process.kill();process.communicate(timeout=2)

class SelectionVerifier:
    def __init__(self,base,events):
        self.base,self.events=base,events;self.jobs=queue.Queue(maxsize=1);self.stop=threading.Event();self.thread=None;self.server=None;self.lines=None;self.lock=threading.Lock()
    def warm(self):
        if self.thread is None:
            self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def reset_server(self):
        with self.lock:
            server=self.server;self.server=None
        if server and server.poll() is None:
            server.kill()
            try:server.wait(timeout=1)
            except (OSError,subprocess.TimeoutExpired):pass
    def windows_check(self,source=None):
        self.last_reason='starting'
        try:
            if not self.server or self.server.poll() is not None:
                self.reset_server();lines=queue.Queue()
                server=subprocess.Popen([str(Path(self.base)/'DesktopBridge.exe'),'verify-server',str(os.getpid())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=0x08000000)
                with self.lock:self.server=server
                self.lines=lines
                def read():
                    for line in server.stdout:lines.put(line.strip())
                    lines.put(b'EXIT')
                threading.Thread(target=read,daemon=True).start()
                if lines.get(timeout=2)!=b'READY':raise OSError('Verifier not ready')
            if source is None:return False
            encoded=base64.b64encode(source.get('clipboard_word','').encode()).decode()
            message='|'.join(str(source[key]) for key in ('pid','hwnd','x','y'))+'|'+encoded+'|'+('W' if source.get('_warm') else 'V')+'\n'
            server=self.server
            if server is None or self.stop.is_set():return False
            server.stdin.write(message.encode());server.stdin.flush()
            answer=self.lines.get(timeout=1.5)
            status,_,reason=answer.partition(b'|')
            if status not in (b'SELECTED',b'EMPTY'):raise OSError('Verifier stopped')
            self.last_reason=reason.decode('ascii',errors='replace') or status.decode()
            return status==b'SELECTED'
        except (OSError,queue.Empty,ValueError) as error:
            self.last_reason='timeout' if isinstance(error,queue.Empty) else type(error).__name__
            self.reset_server();return False
    def prepare(self,source):self.submit(None,dict(source,_warm=True))
    def submit(self,serial,source):
        if self.stop.is_set():return
        try:self.jobs.get_nowait()
        except queue.Empty:pass
        self.jobs.put_nowait((serial,dict(source)))
        self.warm()
    def run(self):
        if sys.platform=='win32':self.windows_check()
        while not self.stop.is_set():
            try:serial,source=self.jobs.get(timeout=.1)
            except queue.Empty:continue
            confirmed=self.windows_check(source) if sys.platform=='win32' else check_selection(self.base,source)
            if not self.stop.is_set() and not source.get('_warm'):self.events.put(('selection_verified',(serial,source,confirmed)))
    def close(self):self.stop.set();self.reset_server()
