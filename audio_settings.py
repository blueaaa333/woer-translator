"""User-run output check. Never changes Windows mute, volume, or other apps."""
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk
from audio_output import test_tone


def show(app, data):
    previous=getattr(app,'audio_window',None)
    if previous and previous.winfo_exists():previous.lift();return
    window=app.audio_window=tk.Toplevel(app.root)
    window.title('声音检查与输出设备');window.configure(bg='white');window.transient(app.root)
    body=tk.Frame(window,bg='white',padx=20,pady=16);body.pack(fill='both',expand=True)
    tk.Label(body,text='声音检查',bg='white',fg='#23475b',font=('',14,'bold')).pack(anchor='w')
    tk.Label(body,text='测试音不需要网络或语音包。\n若测试音也听不到，请检查此应用的音量和输出设备。',
        bg='white',fg='#405969',justify='left',wraplength=350).pack(anchor='w',pady=10)
    chosen=tk.StringVar(master=window,value=app.preferences.get('audio_device','') or '系统默认')
    choice=ttk.Combobox(body,textvariable=chosen,state='readonly',width=38,values=['系统默认']);choice.pack(fill='x',pady=5)
    legacy=tk.BooleanVar(master=window,value=app.preferences.get('legacy_audio',False))
    def save(*args):
        app.preferences['audio_device']='' if chosen.get()=='系统默认' else chosen.get()
        app.preferences['legacy_audio']=legacy.get();app.save_preferences()
    choice.bind('<<ComboboxSelected>>',save)
    tk.Checkbutton(body,text='使用旧版兼容播放（按 Windows 音量混合器路由）',variable=legacy,
        command=save,bg='white',anchor='w').pack(fill='x',pady=5)
    status=tk.Label(body,text='正在读取输出设备…',bg='white',fg='#526d7b',justify='left',wraplength=350)
    status.pack(fill='x',pady=8)
    messages=queue.Queue()
    def enumerate_devices():
        try:messages.put(('devices',[item['name'] for item in app.player.devices()]))
        except Exception as error:messages.put(('status','无法读取输出设备：'+str(error)))
    threading.Thread(target=enumerate_devices,daemon=True).start()
    def test():
        save();app.audio_serial+=1;app.player.stop()
        settings=dict(app.preferences)
        button.config(state='disabled');status.config(text='正在播放短测试音…')
        def worker():
            try:
                app.player.play(test_tone(data/'audio-test.wav'),device_name=settings.get('audio_device',''),
                                legacy=settings.get('legacy_audio',False))
                messages.put(('status','测试音已发送到：'+app.player.last.get('device','')+
                    '\n若没听到，请打开音量混合器，检查“沃尔翻译官”是否静音，以及是否选错输出设备。'))
            except Exception as error:messages.put(('status','播放失败：'+str(error)))
        threading.Thread(target=worker,daemon=True).start()
    button=app.button(body,'播放测试音',test);button.pack(anchor='w',pady=4)
    app.button(body,'打开 Windows 音量混合器 ↗',lambda:os.startfile('ms-settings:apps-volume'),small=True).pack(anchor='w',pady=4)
    def copy():
        report=dict(version=getattr(app,'current_version','私人安装版'),output=dict(app.player.last),
                    selected_device=chosen.get(),legacy=legacy.get(),status=status.cget('text'))
        app.root.clipboard_clear();app.root.clipboard_append(json.dumps(report,ensure_ascii=False,indent=2))
        status.config(text='检查信息已复制，可粘贴给维护者。不含查询词或录音。')
    app.button(body,'复制声音检查信息',copy,small=True).pack(anchor='w',pady=4)
    app.button(body,'关闭',window.destroy,small=True).pack(anchor='e')
    def poll():
        if not window.winfo_exists():return
        while not messages.empty():
            kind,value=messages.get_nowait()
            if kind=='devices':
                choice.config(values=['系统默认']+value)
                status.config(text='请选择正在使用的扬声器或耳机，再播放测试音。' if value else '未检测到声音输出设备。')
            else:status.config(text=value);button.config(state='normal')
        app.root.after(75,poll)
    poll()
    window.update_idletasks();window.geometry(f'+{max(10,app.root.winfo_x())}+{max(20,app.root.winfo_y())}')
