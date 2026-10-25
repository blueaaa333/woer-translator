"""Small update panel; all worker results enter Tk through the App queue."""
import re
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk
import urllib.error
import updater
UI_FONT = 'Microsoft YaHei UI' if sys.platform == 'win32' else 'PingFang SC'


class UpdatePanel:
    def __init__(self, app, events, current, data, testing=False):
        self.app, self.events, self.current = app, events, current
        self.cache = data / 'updates'
        self.testing = testing
        self.window = None
        self.release = self.artifact = None
        self.busy = ''
        self.cancelled = threading.Event()
        self.closed = False
        if not testing:
            app.root.after(20000, self.automatic)
            app.root.after(4000, self.cleanup)

    def cleanup(self):
        def job():
            try:
                updater.cleanup_previous(self.cache, self.current)
            except (OSError, ValueError, KeyError):
                pass
        threading.Thread(target=job, daemon=True).start()

    def automatic(self):
        if self.closed:
            return
        last = self.app.preferences.get('last_update_check', 0)
        if not isinstance(last, (int, float)):
            last = 0
        if self.app.preferences.get('check_updates', True) and time.time()-last >= 86400:
            self.check(False)
        self.app.root.after(3600000, self.automatic)

    def emit(self, action, payload=None):
        if not self.closed:
            self.events.put(('app_update', (action, payload)))

    def check(self, manual=True):
        if self.busy:
            if manual:
                self.show()
            return
        self.busy = 'check'
        if manual:
            self.show()
            self.message.config(text='正在检查新版本…')
            self.action.config(state='disabled', text='正在检查…')
        def job():
            try:
                self.emit('checked', (updater.check(self.current), manual))
            except Exception as exc:
                self.emit('check_error', (self.friendly(exc), manual))
        threading.Thread(target=job, daemon=True).start()

    @staticmethod
    def friendly(error):
        if isinstance(error, updater.UpdateError):
            return str(error)
        if isinstance(error, urllib.error.HTTPError) and error.code in (403, 429):
            return '更新服务暂时限流，请稍后重试。'
        return '暂时无法连接更新服务，请检查网络后重试。'

    def show(self):
        if self.window and self.window.winfo_exists():
            self.window.deiconify()
            self.window.lift()
            return
        app = self.app
        win = self.window = tk.Toplevel(app.root)
        win.title('沃尔翻译官 · 软件更新')
        win.configure(bg='white')
        win.attributes('-topmost', True)
        win.resizable(False, False)
        body = tk.Frame(win, bg='white', padx=22, pady=18)
        body.pack(fill='both', expand=True)
        tk.Label(body, text='软件更新', bg='white', fg='#173c50', font=(UI_FONT, 16, 'bold')).pack(anchor='w')
        self.version_label = tk.Label(body, text='当前版本 v' + self.current, bg='white', fg='#6b8492', font=(UI_FONT, 10))
        self.version_label.pack(anchor='w', pady=(7, 12))
        self.notes = tk.Text(body, width=36, height=6, wrap='word', bd=0, bg='#f1f8fc', fg='#345362', padx=12, pady=10, font=(UI_FONT, 11))
        self.notes.insert('1.0', '发现新版本后，可在这里下载并更新。\n\n更新会保留本机设置、生词本和已下载的语音。')
        self.notes.config(state='disabled')
        self.notes.pack(fill='x')
        self.progress = ttk.Progressbar(body, maximum=100)
        self.progress.pack(fill='x', pady=(12, 6))
        self.message = tk.Label(body, text='', height=3, bg='white', fg='#577787', font=(UI_FONT, 10), wraplength=340, justify='left')
        self.message.pack(anchor='w', pady=(0, 10))
        self.action = app.button(body, '检查更新', lambda:self.check(True))
        self.action.pack(side='right')
        app.button(body, '稍后', win.withdraw, small=True).pack(side='left')
        win.protocol('WM_DELETE_WINDOW', win.withdraw)
        win.update_idletasks()
        app.position(win, max(round(395*app.scale),body.winfo_reqwidth()),body.winfo_reqheight(),x=app.root.winfo_x(),y=app.root.winfo_y(),physical=True)
        if self.release:
            self.display_release()
        if self.busy:
            self.action.config(state='disabled', text='正在处理…')

    def display_release(self):
        release = self.release
        self.version_label.config(text=f'v{self.current}  →  v{release.version}')
        notes = release.notes.split('<!-- installer-downloads:end -->')[-1].strip()
        notes = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', notes)
        notes = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', notes)
        notes = re.sub(r'[`#*]', '', notes)
        self.notes.config(state='normal')
        self.notes.delete('1.0', 'end')
        self.notes.insert('1.0', notes[:1000] or '包含功能改进与问题修复。')
        self.notes.config(state='disabled')
        self.progress['value'] = 100 if self.artifact else 0
        if self.artifact:
            self.message.config(text='下载完成，SHA-256 校验通过。安装时会退出并重启软件。')
            self.action.config(state='normal', text='重启并更新', command=self.install)
        else:
            self.message.config(text=f'发现新版本 · 安装包约 {release.size/1048576:.1f} MB')
            self.action.config(state='normal', text='下载更新', command=self.download)

    def download(self):
        if self.busy or not self.release:
            return
        self.busy = 'download'
        self.cancelled.clear()
        self.action.config(text='暂停下载', command=self.cancelled.set, state='normal')
        self.message.config(text='正在下载，查词功能可继续使用…')
        last = [0.0]
        def progress(done, total):
            now = time.monotonic()
            if now-last[0] >= .2 or done == total:
                last[0] = now
                self.emit('progress', (done, total))
        def job():
            try:
                self.emit('downloaded', updater.download(self.release, self.cache, progress, cancelled=self.cancelled))
            except Exception as exc:
                self.emit('download_error', self.friendly(exc))
        threading.Thread(target=job, daemon=True).start()

    def install(self):
        if self.busy or not self.artifact:
            return
        if not getattr(sys, 'frozen', False):
            self.message.config(text='当前从源码运行，请通过源码仓库更新；已下载的安装包已保留。')
            return
        self.busy = 'install'
        self.action.config(state='disabled', text='正在准备安装…')
        self.message.config(text='正在准备更新。系统可能要求确认安装或重新授权。')
        def job():
            try:
                if sys.platform == 'darwin':
                    updater.prepare_mac(self.release, self.artifact, self.cache)
                else:
                    updater.install_windows(self.release, self.artifact)
                self.emit('install_ready')
            except Exception as exc:
                self.emit('install_error', str(exc) if isinstance(exc, updater.UpdateError) else '安装未能准备完成，当前版本仍保留，请重试。')
        threading.Thread(target=job, daemon=True).start()

    def receive(self, event):
        action, payload = event
        if action == 'checked':
            self.busy = ''
            self.app.preferences['last_update_check'] = time.time()
            self.app.save_preferences()
            release, manual = payload
            if release:
                self.release, self.artifact = release, None
                self.show()
                self.display_release()
            elif manual:
                self.message.config(text='当前已是最新版本。')
                self.action.config(state='normal', text='重新检查', command=lambda:self.check(True))
        elif action == 'check_error':
            self.busy = ''
            text, manual = payload
            if manual:
                self.message.config(text=text)
                self.action.config(state='normal', text='重试', command=lambda:self.check(True))
        elif action == 'progress':
            if self.window and self.window.winfo_exists():
                done, total = payload
                self.progress['value'] = done/total*100
                self.message.config(text=f'正在下载 {done/1048576:.1f} / {total/1048576:.1f} MB')
        elif action == 'downloaded':
            self.busy, self.artifact = '', payload
            self.show()
            self.display_release()
        elif action in ('download_error', 'install_error'):
            self.busy = ''
            self.show()
            self.display_release()
            self.message.config(text=payload)
            if action == 'download_error':
                self.action.config(text='继续下载', command=self.download)
        elif action == 'install_ready':
            self.app.root.destroy()

    def close(self):
        self.closed = True
        self.cancelled.set()
