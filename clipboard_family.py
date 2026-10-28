"""Read-only process relationship checks for multi-process clipboard owners."""
import ctypes as C
from ctypes import wintypes
from pathlib import PureWindowsPath
class Entry(C.Structure):
 _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('pid',wintypes.DWORD),('heap',C.c_size_t),('module',wintypes.DWORD),('threads',wintypes.DWORD),('parent',wintypes.DWORD),('priority',wintypes.LONG),('flags',wintypes.DWORD),('name',wintypes.WCHAR*260)]
def matches(source,owner,parents,paths):
 if source==owner:return True
 if parents.get(owner)!=source and parents.get(source)!=owner:return False
 a=PureWindowsPath(paths.get(source,''));b=PureWindowsPath(paths.get(owner,''))
 return a.is_absolute() and b.is_absolute() and str(a.parent).casefold()==str(b.parent).casefold()
def metadata(pids):
 k=C.windll.kernel32;k.CreateToolhelp32Snapshot.restype=C.c_void_p;k.CloseHandle.argtypes=[C.c_void_p]
 k.Process32FirstW.argtypes=[C.c_void_p,C.POINTER(Entry)];k.Process32NextW.argtypes=[C.c_void_p,C.POINTER(Entry)]
 parents={};paths={};snapshot=k.CreateToolhelp32Snapshot(2,0)
 if snapshot not in (None,C.c_void_p(-1).value):
  try:
   row=Entry();row.dwSize=C.sizeof(row);valid=k.Process32FirstW(snapshot,C.byref(row))
   while valid:
    if row.pid in pids:parents[row.pid]=row.parent
    if len(parents)==len(pids):break
    valid=k.Process32NextW(snapshot,C.byref(row))
  finally:k.CloseHandle(snapshot)
 k.OpenProcess.restype=C.c_void_p;k.QueryFullProcessImageNameW.argtypes=[C.c_void_p,wintypes.DWORD,wintypes.LPWSTR,C.POINTER(wintypes.DWORD)]
 for pid in pids:
  handle=k.OpenProcess(0x1000,False,pid)
  if not handle:continue
  try:
   buffer=C.create_unicode_buffer(32768);length=wintypes.DWORD(len(buffer))
   if k.QueryFullProcessImageNameW(handle,0,buffer,C.byref(length)):paths[pid]=buffer.value
  finally:k.CloseHandle(handle)
 return parents,paths
def related_owner(source,owner):
 if not source or not owner:return False
 try:return matches(source,owner,*metadata({source,owner}))
 except (OSError,ValueError,AttributeError):return False
