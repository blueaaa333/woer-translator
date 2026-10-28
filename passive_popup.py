"""Show only our window without activation; avoid existing small floating windows."""
import ctypes as C,os
from ctypes import wintypes
def intersects(a,b,gap=6):return a[0]<b[2]+gap and a[2]+gap>b[0] and a[1]<b[3]+gap and a[3]+gap>b[1]
def choose_position(rect,obstacles,work):
 x,y,right,bottom=rect;w=right-x;h=bottom-y
 candidates=[(x,y)]
 for a,b,c,d in obstacles:candidates.extend(((x,d+8),(x,b-h-8),(c+8,y),(a-w-8,y)))
 candidates.sort(key=lambda pos:abs(pos[0]-x)+abs(pos[1]-y))
 for px,py in candidates:
  px=max(work[0]+4,min(px,work[2]-w-4));py=max(work[1]+4,min(py,work[3]-h-4))
  if all(not intersects((px,py,px+w,py+h),other) for other in obstacles):return px,py
 return x,y
def foreign_floaters(user,point):
 result=[];callback_type=C.WINFUNCTYPE(wintypes.BOOL,C.c_void_p,C.c_void_p)
 def check(hwnd,_):
  if not user.IsWindowVisible(C.c_void_p(hwnd)):return True
  pid=wintypes.DWORD();user.GetWindowThreadProcessId(C.c_void_p(hwnd),C.byref(pid))
  if pid.value==os.getpid():return True
  rect=wintypes.RECT()
  if not user.GetWindowRect(C.c_void_p(hwnd),C.byref(rect)):return True
  w=rect.right-rect.left;h=rect.bottom-rect.top
  if 70<=w<=1000 and 22<=h<=240 and abs(rect.top-point[1])<240:
   result.append((rect.left,rect.top,rect.right,rect.bottom))
  return True
 callback=callback_type(check);user.EnumWindows.argtypes=[callback_type,C.c_void_p];user.EnumWindows(callback,None)
 return result
def show_without_activation(window,user):
 user.GetParent.restype=C.c_void_p;user.GetForegroundWindow.restype=C.c_void_p
 before=user.GetForegroundWindow();hwnd=user.GetParent(C.c_void_p(window.winfo_id()))
 style=user.GetWindowLongW(C.c_void_p(hwnd),-20)
 user.SetWindowLongW(C.c_void_p(hwnd),-20,style|0x80|0x08000000)
 # Tk's deiconify uses an activating ShowWindow mode; a disabled window cannot
 # activate. Re-enable only after mapping, then retain WS_EX_NOACTIVATE.
 window.attributes('-disabled',True)
 try:
  window.deiconify();window.update_idletasks();user.ShowWindow(C.c_void_p(hwnd),4)
 finally:window.attributes('-disabled',False)
 user.SetWindowPos(C.c_void_p(hwnd),C.c_void_p(-1),0,0,0,0,0x1|0x2|0x10)
 return before,user.GetForegroundWindow()
