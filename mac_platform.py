"""macOS integration. Imports Apple frameworks lazily; no Windows emulation."""
import os,re,subprocess,threading,time
from types import SimpleNamespace

_tap=None
_loop=None
_callback=None
_instance_file=None
SUPPORTED={'com.apple.Safari','com.google.Chrome','com.microsoft.edgemac','org.mozilla.firefox',
           'com.apple.Preview','com.apple.TextEdit','com.microsoft.Word','com.kingsoft.wpsoffice.mac'}

def clipboard_sequence():
    from AppKit import NSPasteboard
    return int(NSPasteboard.generalPasteboard().changeCount())

def clipboard_text():
    from AppKit import NSPasteboard,NSPasteboardTypeString
    value=NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString)
    return str(value) if value and len(value)<=256 else ''

def trusted(prompt=False):
    from ApplicationServices import AXIsProcessTrustedWithOptions,kAXTrustedCheckOptionPrompt
    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt:prompt}))

def request_permissions(events):
    import Quartz
    trusted(True)
    if hasattr(Quartz,'CGRequestListenEventAccess'):Quartz.CGRequestListenEventAccess()
    events.put(('status','请在系统设置→隐私与安全中允许辅助功能及输入监控；也可手动输入查词。'))

def frontmost():
    from AppKit import NSWorkspace
    app=NSWorkspace.sharedWorkspace().frontmostApplication()
    return (int(app.processIdentifier()),str(app.bundleIdentifier() or '')) if app else (0,'')

def source_is_frontmost(pid):return frontmost()[0]==int(pid)

def activate_source(pid):
    from AppKit import NSRunningApplication,NSApplicationActivateIgnoringOtherApps
    app=NSRunningApplication.runningApplicationWithProcessIdentifier_(int(pid))
    return bool(app and app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps))

def copy_selection():
    if not trusted():return False
    import Quartz as Q
    for down in (True,False):
        event=Q.CGEventCreateKeyboardEvent(None,8,down) # physical C key
        Q.CGEventSetFlags(event,Q.kCGEventFlagMaskCommand)
        Q.CGEventPost(Q.kCGHIDEventTap,event)
    return True

def work_area(x,y):
    from AppKit import NSScreen
    screens=NSScreen.screens();main=screens[0].frame();main_top=main.origin.y+main.size.height
    areas=[]
    for screen in screens:
        frame=screen.visibleFrame()
        rect=SimpleNamespace(left=round(frame.origin.x),top=round(main_top-frame.origin.y-frame.size.height),
                             right=round(frame.origin.x+frame.size.width),bottom=round(main_top-frame.origin.y))
        if rect.left<=x<rect.right and rect.top<=y<rect.bottom:return rect
        areas.append(rect)
    return min(areas,key=lambda r:max(r.left-x,0,x-r.right)**2+max(r.top-y,0,y-r.bottom)**2)

def monitor(events,enabled,stop):
    global _tap,_loop,_callback
    import Quartz as Q
    from CoreFoundation import CFMachPortCreateRunLoopSource,CFRunLoopAddSource,CFRunLoopGetCurrent,CFRunLoopRunInMode,kCFRunLoopCommonModes,kCFRunLoopDefaultMode
    warned=False
    while not stop.is_set():
        if not trusted():
            if not warned:events.put(('status','macOS：在“···”中启用划词权限，或复制 / 手动输入单词。'));warned=True
            stop.wait(3);continue
        state={'start':None,'serial':0}
        def source(event):
            pid,bundle=frontmost()
            if pid==os.getpid():return None
            point=Q.CGEventGetLocation(event);state['serial']+=1
            return dict(pid=pid,hwnd=pid,x=round(point.x),y=round(point.y),id=state['serial'],emitted=round(time.time()*1000),word='',supported=bundle in SUPPORTED)
        def process_event(proxy,event_type,event,info):
            if event_type in (Q.kCGEventTapDisabledByTimeout,Q.kCGEventTapDisabledByUserInput):
                if _tap:Q.CGEventTapEnable(_tap,True)
                return event
            if Q.CGEventGetIntegerValueField(event,Q.kCGEventSourceUnixProcessID)==os.getpid():return event
            current=source(event)
            if current is None:return event
            if event_type==Q.kCGEventLeftMouseDown:state['start']=current
            elif event_type==Q.kCGEventLeftMouseUp:
                initial=state['start'];state['start']=None
                dragged=bool(initial and initial['pid']==current['pid'] and abs(initial['x']-current['x'])+abs(initial['y']-current['y'])>=5)
                double=Q.CGEventGetIntegerValueField(event,Q.kCGMouseEventClickState)>=2
                if (dragged or double) and enabled.is_set() and current['supported']:events.put(('gesture',current))
                elif not double:events.put(('clear',dict(reason='click',at=current['emitted'],pid=current['pid'])))
            elif event_type==Q.kCGEventRightMouseUp:events.put(('clear',dict(reason='click',at=current['emitted'],pid=current['pid'])))
            elif event_type==Q.kCGEventKeyDown:
                key=Q.CGEventGetIntegerValueField(event,Q.kCGKeyboardEventKeycode);flags=Q.CGEventGetFlags(event)
                command=bool(flags&Q.kCGEventFlagMaskCommand);option=bool(flags&Q.kCGEventFlagMaskAlternate)
                if command and option and key==2:events.put(('hotkey_source',current))
                elif not (command and key==8):events.put(('clear',dict(reason='keyboard',at=current['emitted'],pid=current['pid'])))
            return event
        def callback(proxy,event_type,event,info):
            import objc
            with objc.autorelease_pool():return process_event(proxy,event_type,event,info)
        _callback=callback
        mask=sum(1<<int(kind) for kind in (Q.kCGEventLeftMouseDown,Q.kCGEventLeftMouseUp,Q.kCGEventRightMouseUp,Q.kCGEventKeyDown))
        _tap=Q.CGEventTapCreate(Q.kCGSessionEventTap,Q.kCGHeadInsertEventTap,Q.kCGEventTapOptionListenOnly,mask,_callback,None)
        if _tap is None:
            if not warned:events.put(('status','请允许辅助功能及输入监控；复制查词和手动查询仍可使用。'));warned=True
            stop.wait(3);continue
        _loop=CFRunLoopGetCurrent();source_ref=CFMachPortCreateRunLoopSource(None,_tap,0)
        CFRunLoopAddSource(_loop,source_ref,kCFRunLoopCommonModes);Q.CGEventTapEnable(_tap,True)
        events.put(('status','macOS 划词已就绪 · ⌘⌥D 查询选词'))
        while not stop.is_set():CFRunLoopRunInMode(kCFRunLoopDefaultMode,.25,False)
        Q.CGEventTapEnable(_tap,False);_tap=None;_loop=None;return

def stop_monitor():
    if _loop:
        from CoreFoundation import CFRunLoopStop
        CFRunLoopStop(_loop)

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
