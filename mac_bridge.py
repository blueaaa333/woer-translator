"""Nonblocking UI-side cache and private IPC for the macOS native helper."""
import json
import os
import queue
import select
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path


class MacBridge:
    def __init__(self, events, enabled, stop, data):
        self.events, self.enabled, self.stop = events, enabled, stop
        self.data = Path(data)
        self.commands = queue.Queue(maxsize=32)
        self.lock = threading.Lock()
        self.sequence, self.text, self.screens = 0, '', [];self.clipboard_pid=0
        self.ready = threading.Event()
        self.test_resumed = threading.Event()
        self.test_pause_started = None
        self.permissions = {}
        self.process = None

    def clipboard(self):
        with self.lock:
            return self.sequence, self.text

    def areas(self):
        with self.lock:
            return list(self.screens)

    def send(self, kind, **fields):
        try:
            if kind == 'query':
                fields['created'] = time.monotonic()
            self.commands.put_nowait(dict(kind=kind, **fields))
            return True
        except queue.Full:
            self.events.put(('status', 'Mac 系统服务忙，请稍后重试；可继续手动查词。'))
            return False

    def receive(self, message):
        kind = message['kind']
        if kind == 'clipboard':
            with self.lock:
                self.sequence = int(message['sequence'])
                self.text = message['text']
                self.clipboard_pid = int(message.get('pid',0))
        elif kind == 'screens':
            with self.lock:
                self.screens = message['areas']
        elif kind == 'ready':
            self.ready.set()
            self.events.put(('mac_bridge_ready', None))
        elif kind == 'permissions':
            with self.lock:
                self.permissions = message['value']
            self.events.put(('mac_permissions',dict(message['value'])))
        elif kind == 'self_test_resumed':
            self.test_resumed.set()
        elif kind == 'self_test_started':
            self.test_pause_started = time.monotonic()
        elif kind == 'gesture':
            if self.enabled.is_set():
                self.events.put((kind, message['value']))
        elif kind in ('clear', 'hotkey_source', 'mac_query_result', 'status'):
            self.events.put((kind, message['value']))

    def run(self):
        # Never import Cocoa or wait for native calls in the Tk process.
        self.data.mkdir(parents=True, exist_ok=True)
        for attempt in range(2):
            if self.stop.is_set():
                return
            parent, child = socket.socketpair()
            try:
                command = [sys.executable]
                if not getattr(sys, 'frozen', False):
                    command.append(str(Path(__file__).with_name('app.py')))
                command += ['--mac-bridge', str(child.fileno()), str(os.getpid())]
                if '--gui-self-test' in sys.argv:
                    command.append('--native-self-test')
                with (self.data / 'mac-native-errors.log').open('ab') as log:
                    self.process = subprocess.Popen(command, pass_fds=(child.fileno(),),
                                                    stdin=subprocess.DEVNULL, stdout=log, stderr=log)
                child.close()
                parent.setblocking(False)
                incoming = outgoing = b''
                last_message = time.monotonic()
                while not self.stop.is_set():
                    if not outgoing:
                        try:
                            outgoing = (json.dumps(self.commands.get_nowait()) + '\n').encode('utf-8')
                        except queue.Empty:
                            pass
                    readable, writable, _ = select.select([parent], [parent] if outgoing else [], [], .1)
                    if writable:
                        outgoing = outgoing[parent.send(outgoing):]
                    if readable:
                        chunk = parent.recv(65536)
                        if not chunk:
                            raise RuntimeError('Native helper disconnected')
                        last_message = time.monotonic()
                        incoming += chunk
                        if len(incoming) > 131072:
                            raise RuntimeError('Invalid helper message size')
                        while b'\n' in incoming:
                            line, incoming = incoming.split(b'\n', 1)
                            self.receive(json.loads(line))
                    if time.monotonic() - last_message > 20:
                        raise TimeoutError('Native helper did not respond')
            except Exception as error:
                if not self.stop.is_set():
                    self.events.put(('status', 'Mac 划词服务正在重新连接…' if attempt == 0 else
                                     'Mac 划词服务未就绪，请重启软件；手动查词仍可使用。'))
                    with (self.data / 'mac-native-errors.log').open('a', encoding='utf-8') as log:
                        log.write(time.strftime('%Y-%m-%d %H:%M:%S') + ' ' + type(error).__name__ + '\n')
            finally:
                self.ready.clear()
                child.close()
                parent.close()
                if self.process is not None and self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait(timeout=2)
            if self.stop.wait(1):
                return
