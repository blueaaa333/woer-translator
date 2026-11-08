"""Visible, single-instance speech installation; workers never touch Tk or open URLs."""
import queue
import threading
import tkinter as tk
from tkinter import ttk

def show(app, data):
    previous=getattr(app,'voice_download_window',None)
    if previous and previous.winfo_exists():previous.deiconify();previous.lift();return
    menu=getattr(app,'settings_popup',None)
    if menu and menu.winfo_exists():menu.destroy()
    window=app.voice_download_window=tk.Toplevel(app.root)
    window.title('下载英美离线语音');window.configure(bg='white');window.transient(app.root)
    body=tk.Frame(window,bg='white',padx=22,pady=18);body.pack(fill='both',expand=True)
    tk.Label(body,text='英美离线语音',bg='white',fg='#23475b',font=('',14,'bold')).pack(anchor='w')
    tk.Label(body,text='从语音项目上游下载约 200 MB 文件，校验后安装。\n本窗口直接下载，无需前往词典网页。',bg='white',fg='#526d7b',justify='left',wraplength=390).pack(anchor='w',pady=10)
    status=tk.Label(body,text='准备下载…',bg='white',fg='#23475b',justify='left',wraplength=390);status.pack(fill='x',pady=6)
    bar=ttk.Progressbar(body,mode='indeterminate',length=360);bar.pack(fill='x',pady=7)
    messages=queue.Queue();state={'running':False}
    def begin():
        if state['running']:return
        state['running']=True;app.voice_installing=True;retry.config(state='disabled');bar.start(12)
        status.config(text='正在连接语音下载源…')
        def progress(value):messages.put(('progress',value))
        def worker():
            try:
                from scripts.setup_speech import install
                install(data.resolve(),progress=progress)
                messages.put(('done','英美语音安装完成，可以点击小喇叭播放。'))
            except Exception as error:
                # Only the error class is shown: remote/local exception strings
                # may contain URLs or private filesystem paths.
                messages.put(('error','下载未完成（'+type(error).__name__+'）。请检查网络后重试；已安装的语音保留。'))
        threading.Thread(target=worker,daemon=True).start()
    retry=app.button(body,'开始／重试下载',begin);retry.pack(anchor='w',pady=5)
    app.button(body,'收起，继续后台下载',window.withdraw,small=True).pack(anchor='e')
    window.protocol('WM_DELETE_WINDOW',window.withdraw)
    window.bind('<Escape>',lambda event:window.withdraw())
    def poll():
        if not window.winfo_exists():return
        while not messages.empty():
            kind,value=messages.get_nowait();status.config(text=value)
            if kind=='done':
                app.audio_serial+=1
                if app.player:app.player.stop()
                app.speech.root=data/'speech';app.preferences['prefer_recordings']=False;app.save_preferences()
                app.voice_install_button.pack_forget()
            if kind in ('done','error'):
                state['running']=False;app.voice_installing=False;bar.stop();retry.config(state='normal')
                app.status.config(text=value)
        window.after(75,poll)
    window._speech_messages=messages;window._speech_state=state;window._speech_status=status
    window.update_idletasks();window.geometry(f'+{max(10,app.root.winfo_x())}+{max(20,app.root.winfo_y())}')
    window.deiconify();window.lift();window.focus_set();poll();begin()
