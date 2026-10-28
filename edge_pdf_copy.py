"""Opt-in Edge PDF fallback. Never clear the user's clipboard to detect a selection."""
import ctypes
from ctypes import wintypes
def request_copy(source,user):
 if source.get('app')!='msedge':return None
 user.GetForegroundWindow.restype=ctypes.c_void_p
 if user.GetForegroundWindow()!=source['hwnd']:return None
 pid=wintypes.DWORD();user.GetWindowThreadProcessId(ctypes.c_void_p(source['hwnd']),ctypes.byref(pid))
 if pid.value!=source['pid']:return None
 title=ctypes.create_unicode_buffer(512)
 user.GetWindowTextW(ctypes.c_void_p(source['hwnd']),title,len(title))
 if '.pdf' not in title.value.lower():return None
 # Do not interfere with a still-held mouse button or user keyboard chord.
 if any(user.GetAsyncKeyState(key)&0x8000 for key in (1,2,16,17,18,91,92)):return None
 before=user.GetClipboardSequenceNumber()
 try:
  user.keybd_event(17,0,0,0);user.keybd_event(67,0,0,0)
 finally:
  user.keybd_event(67,0,2,0);user.keybd_event(17,0,2,0)
 return before
def fresh_copy(source,before,sequence,owner_pid):
 return owner_pid==source['pid'] and (before&0xffffffff)!=(sequence&0xffffffff)
