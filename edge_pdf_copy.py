"""Opt-in automatic Copy confirmation. Never clear the user's clipboard."""
import ctypes
from ctypes import wintypes
NEVER_COPY=frozenset({'windowsterminal','wt','powershell','pwsh','cmd','conhost','mintty','putty','wezterm','alacritty','ssh'})
class GuiThreadInfo(ctypes.Structure):
 _fields_=[('cbSize',wintypes.DWORD),('flags',wintypes.DWORD),('hwndActive',wintypes.HWND),('hwndFocus',wintypes.HWND),('hwndCapture',wintypes.HWND),('hwndMenuOwner',wintypes.HWND),('hwndMoveSize',wintypes.HWND),('hwndCaret',wintypes.HWND),('rcCaret',wintypes.RECT)]
def request_copy(source,user,all_apps=False):
 from selection_apps import supported_process
 name=source.get('app','').lower().removesuffix('.exe')
 if name in NEVER_COPY or not supported_process(name,True):return None
 if not all_apps and name!='msedge':return None
 user.GetForegroundWindow.restype=ctypes.c_void_p
 if user.GetForegroundWindow()!=source['hwnd']:return None
 pid=wintypes.DWORD();user.GetWindowThreadProcessId(ctypes.c_void_p(source['hwnd']),ctypes.byref(pid))
 if pid.value!=source['pid']:return None
 if not all_apps:
  title=ctypes.create_unicode_buffer(512)
  user.GetWindowTextW(ctypes.c_void_p(source['hwnd']),title,len(title))
  if '.pdf' not in title.value.lower():return None
 info=GuiThreadInfo();info.cbSize=ctypes.sizeof(info)
 if user.GetGUIThreadInfo(0,ctypes.byref(info)) and info.hwndFocus:
  name_buffer=ctypes.create_unicode_buffer(64)
  user.GetClassNameW(ctypes.c_void_p(info.hwndFocus),name_buffer,len(name_buffer))
  if 'edit' in name_buffer.value.lower() and user.GetWindowLongW(ctypes.c_void_p(info.hwndFocus),-16)&0x20:return None
 # Do not interfere with a still-held mouse button or user keyboard chord.
 if any(user.GetAsyncKeyState(key)&0x8000 for key in (1,2,16,17,18,91,92)):return None
 before=user.GetClipboardSequenceNumber()
 try:
  user.keybd_event(17,0,0,0);user.keybd_event(67,0,0,0)
 finally:
  user.keybd_event(67,0,2,0);user.keybd_event(17,0,2,0)
 return before
def fresh_copy(source,before,sequence,owner_pid,owner_root=None):
 same_source=owner_pid==source['pid'] or (owner_root is not None and owner_root==source['hwnd'])
 return same_source and (before&0xffffffff)!=(sequence&0xffffffff)
