"""Use fresh text already copied by the source app; never synthesize Copy."""
import threading,time
class GestureCopy:
 def __init__(self):self.lock=threading.Lock();self.value=None
 def record(self,source):
  if 'clipboard_before' not in source:return
  with self.lock:self.value=dict(source)
 def cancel(self,at):
  with self.lock:
   if self.value and at>self.value['emitted']:self.value=None
 def consume(self,pid,hwnd,sequence,owner_pid,now=None):
  now=int(time.time()*1000) if now is None else now
  with self.lock:
   source=self.value
   if not source:return None
   if not 0<=now-source['emitted']<=700:self.value=None;return None
   if source['pid']!=pid or source['hwnd']!=hwnd or owner_pid!=pid:return None
   if (source['clipboard_before']&0xffffffff)==(sequence&0xffffffff):return None
   self.value=None;return dict(source)
recent_gesture=GestureCopy()
