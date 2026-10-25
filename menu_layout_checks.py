"""Check visible controls and the native clip, including high DPI and resizing."""
import ctypes
import json
import sys
import tkinter as tk
from pathlib import Path


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def inspect_panel(panel):
    panel.update_idletasks()
    width, height = panel.winfo_width(), panel.winfo_height()
    buttons = [w for w in descendants(panel) if isinstance(w, tk.Button)]
    labels = [w.cget('text') for w in buttons]
    assert '关闭菜单' in labels and '退出应用' in labels and '×' in labels, labels
    for button in buttons:
        left, top = button.winfo_rootx()-panel.winfo_rootx(), button.winfo_rooty()-panel.winfo_rooty()
        assert button.winfo_ismapped(), button.cget('text')
        assert 0 <= left and left+button.winfo_width() <= width, (button.cget('text'), left, width)
        assert 0 <= top and top+button.winfo_height() <= height, (button.cget('text'), top, height)
    result = dict(size=[width,height], controls=len(buttons), close_visible=True)
    if sys.platform == 'win32':
        class RECT(ctypes.Structure):
            _fields_=[('left',ctypes.c_long),('top',ctypes.c_long),('right',ctypes.c_long),('bottom',ctypes.c_long)]
        user, gdi = ctypes.windll.user32, ctypes.windll.gdi32
        user.GetParent.argtypes=[ctypes.c_void_p];user.GetParent.restype=ctypes.c_void_p
        user.GetWindowRgn.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        gdi.CreateRectRgn.restype=ctypes.c_void_p
        gdi.GetRgnBox.argtypes=[ctypes.c_void_p,ctypes.POINTER(RECT)]
        gdi.DeleteObject.argtypes=[ctypes.c_void_p]
        region = gdi.CreateRectRgn(0,0,0,0)
        try:
            assert user.GetWindowRgn(user.GetParent(panel.winfo_id()),region)>0
            box = RECT();gdi.GetRgnBox(region,ctypes.byref(box))
            assert width <= box.right <= width+2 and height <= box.bottom <= height+2, (width,height,box.right,box.bottom)
            result['native_clip']=[box.right,box.bottom]
        finally:
            gdi.DeleteObject(region)
    return result


def exercise(app):
    app.root.update()
    checks=[]
    for _ in range(3):
        app.menu();app.root.update()
        panel=app.settings_popup
        checks.append(inspect_panel(panel))
        width,height=panel.winfo_width(),panel.winfo_height()
        panel.geometry(f'{width+32}x{height+12}')
        app.root.update()
        checks.append(inspect_panel(panel))
        close=next(w for w in descendants(panel) if isinstance(w,tk.Button) and w.cget('text')=='关闭菜单')
        close.invoke();app.root.update()
        assert not panel.winfo_exists()
        assert app.root.winfo_exists()
    return dict(dpi=getattr(app,'dpi',None), checks=checks, repeated_open_close=3, resize_clip='ok')


def frozen_check(app_type, report):
    app=app_type(testing=True)
    try:
        result=exercise(app)
        Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        app.root.destroy()
    from preference_checks import exercise as check_preferences
    result['preferences']=check_preferences(app_type)
    Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
