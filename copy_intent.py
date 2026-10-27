"""Require a real Copy keystroke and a subsequent clipboard change."""
import threading,time
class CopyIntent:
 def __init__(self):self.lock=threading.Lock();self.value=None
 def record(self,pid,hwnd,sequence,at):
  with self.lock:self.value=(pid,hwnd,sequence,at)
 def cancel(self,at):
  with self.lock:
   if self.value and at>self.value[3]:self.value=None
 def consume(self,pid,hwnd,sequence,now=None):
  now=int(time.time()*1000) if now is None else now
  with self.lock:
   value=self.value
   if not value:return False
   if not 0<=now-value[3]<=1500:self.value=None;return False
   if value[0:2]!=(pid,hwnd) or value[2]==sequence:return False
   self.value=None;return True
recent_copy=CopyIntent()
