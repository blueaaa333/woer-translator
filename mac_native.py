"""Native macOS helper: one Cocoa main thread, no Tk, private inherited socket."""
import json
import os
import queue
import socket
import sys
import threading
import time

# A gesture only offers actions. Copy text only after Query is clicked.
IGNORED_BUNDLES = {'com.apple.finder', 'com.apple.dock', 'com.apple.loginwindow',
                   'com.apple.systempreferences', 'com.apple.systemuiserver'}


def over_own_window(raw, regions):
    return raw['type'] != 'key' and any(r['left'] <= raw['x'] < r['right'] and
                                       r['top'] <= raw['y'] < r['bottom'] for r in regions)


class Gestures:
    def __init__(self, own_pids):
        self.own_pids = set(own_pids)
        self.start = None
        self.serial = 0

    def handle(self, raw, context):
        pid, bundle = context
        if pid in self.own_pids or not bundle or bundle.lower() in IGNORED_BUNDLES:
            self.start = None
            return None
        self.serial += 1
        current = dict(pid=pid, hwnd=pid, x=raw['x'], y=raw['y'], id=self.serial,
                       emitted=raw['at'], word='')
        kind = raw['type']
        if kind == 'down':
            self.start = current
        elif kind == 'up':
            initial, self.start = self.start, None
            dragged = bool(initial and initial['pid'] == pid and
                           abs(initial['x']-current['x']) + abs(initial['y']-current['y']) >= 5)
            if dragged or raw.get('clicks', 1) >= 2:
                return 'gesture', current
            return 'clear', dict(reason='click', at=raw['at'], pid=pid)
        elif kind == 'right':
            return 'clear', dict(reason='click', at=raw['at'], pid=pid)
        elif kind == 'key':
            if raw['command'] and raw['option'] and raw['key'] == 2:
                return 'hotkey_source', current
            if not (raw['command'] and raw['key'] == 8):
                return 'clear', dict(reason='keyboard', at=raw['at'], pid=pid)
        return None


def run():
    import objc
    import Quartz as Q
    from AppKit import (NSPasteboard, NSPasteboardTypeString, NSWorkspace, NSScreen,
                        NSRunningApplication, NSApplicationActivateIgnoringOtherApps)
    from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt
    from CoreFoundation import (CFMachPortCreateRunLoopSource, CFRunLoopAddSource, CFRunLoopGetCurrent,
                                CFRunLoopRunInMode, CFRunLoopRemoveSource, CFMachPortInvalidate,
                                kCFRunLoopCommonModes, kCFRunLoopDefaultMode)
    from lexicon import normalize_query, valid_query

    offset = sys.argv.index('--mac-bridge')
    channel = socket.socket(fileno=int(sys.argv[offset+1]))
    parent_pid = int(sys.argv[offset+2])
    stream = channel.makefile('rwb')
    commands = queue.Queue(maxsize=64)
    raw_events = queue.Queue(maxsize=256)
    stop = threading.Event()
    gestures = Gestures({os.getpid(), parent_pid})
    tap = source_ref = last_permissions = pending = sequence = last_screens = None
    last_clipboard = last_heartbeat = last_permissions_check = 0
    regions = []

    def emit(kind, **fields):
        stream.write((json.dumps(dict(kind=kind, **fields), ensure_ascii=False)+'\n').encode('utf-8'))
        stream.flush()

    def read_commands():
        try:
            for line in stream:
                if len(line) > 4096:
                    break
                commands.put(json.loads(line))
        finally:
            stop.set()
    threading.Thread(target=read_commands, daemon=True).start()

    def context():
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return (int(app.processIdentifier()), str(app.bundleIdentifier() or '')) if app else (0, '')

    def permissions():
        ax = bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: False}))
        listen = bool(Q.CGPreflightListenEventAccess()) if hasattr(Q, 'CGPreflightListenEventAccess') else ax
        return dict(accessibility=ax, input_monitoring=listen)

    def clipboard(force=False):
        nonlocal sequence
        board = NSPasteboard.generalPasteboard()
        count = int(board.changeCount())
        if force or sequence != count:
            initial = sequence is None
            sequence = count
            value = board.stringForType_(NSPasteboardTypeString)
            emit('clipboard', sequence=count, text=str(value) if not initial and value and len(value) <= 256 else '',pid=context()[0])
        return board, count

    def screens():
        nonlocal last_screens
        displays = NSScreen.screens()
        if not displays:
            return
        top = displays[0].frame().origin.y + displays[0].frame().size.height
        areas = []
        for screen in displays:
            frame = screen.visibleFrame()
            areas.append(dict(left=round(frame.origin.x), top=round(top-frame.origin.y-frame.size.height),
                              right=round(frame.origin.x+frame.size.width), bottom=round(top-frame.origin.y)))
        if areas != last_screens:
            last_screens = areas
            emit('screens', areas=areas)

    def callback(proxy, event_type, event, info):
        # Only primitive reads here. Cocoa lookups, permissions and IPC run later.
        if event_type in (Q.kCGEventTapDisabledByTimeout, Q.kCGEventTapDisabledByUserInput):
            if tap:
                Q.CGEventTapEnable(tap, True)
            return event
        if Q.CGEventGetIntegerValueField(event, Q.kCGEventSourceUnixProcessID) in gestures.own_pids:
            return event
        point = Q.CGEventGetLocation(event)
        kind = {Q.kCGEventLeftMouseDown:'down', Q.kCGEventLeftMouseUp:'up',
                Q.kCGEventRightMouseUp:'right', Q.kCGEventKeyDown:'key'}.get(event_type)
        if kind:
            flags = Q.CGEventGetFlags(event)
            raw = dict(type=kind, x=round(point.x), y=round(point.y), at=round(time.time()*1000),
                       clicks=Q.CGEventGetIntegerValueField(event, Q.kCGMouseEventClickState),
                       key=Q.CGEventGetIntegerValueField(event, Q.kCGKeyboardEventKeycode),
                       command=bool(flags & Q.kCGEventFlagMaskCommand), option=bool(flags & Q.kCGEventFlagMaskAlternate))
            # A nonactivating toolbar leaves the browser frontmost. Filter by
            # its bounds at capture time, before a click can hide the toolbar.
            if over_own_window(raw, regions):
                return event
            try:
                raw_events.put_nowait(raw)
            except queue.Full:
                pass
        return event

    try:
        emit('ready')
        while not stop.is_set():
            with objc.autorelease_pool():
                now = time.monotonic()
                if now-last_heartbeat >= 1:
                    emit('heartbeat')
                    screens()
                    last_heartbeat = now
                if now-last_permissions_check >= 2:
                    access = permissions()
                    if tap and not (access['input_monitoring'] or access['accessibility']):
                        Q.CGEventTapEnable(tap, False)
                        CFRunLoopRemoveSource(CFRunLoopGetCurrent(), source_ref, kCFRunLoopCommonModes)
                        CFMachPortInvalidate(tap)
                        tap = source_ref = None
                    if not tap and (access['input_monitoring'] or access['accessibility']):
                        mask = sum(1 << int(kind) for kind in (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp,
                                                              Q.kCGEventRightMouseUp, Q.kCGEventKeyDown))
                        tap = Q.CGEventTapCreate(Q.kCGSessionEventTap, Q.kCGHeadInsertEventTap,
                                                Q.kCGEventTapOptionListenOnly, mask, callback, None)
                        if tap:
                            source_ref = CFMachPortCreateRunLoopSource(None, tap, 0)
                            CFRunLoopAddSource(CFRunLoopGetCurrent(), source_ref, kCFRunLoopCommonModes)
                            Q.CGEventTapEnable(tap, True)
                    state = dict(access, listening=bool(tap))
                    if state != last_permissions:
                        last_permissions = state
                        emit('permissions', value=state)
                        if tap:
                            emit('status', value='Mac 划词已就绪 · ⌘⌥D 查询选词' if access['accessibility'] else
                                 '工具条已就绪；点击查词取词还需辅助功能权限。')
                        else:
                            emit('status', value='Mac 划词未授权：在“···”中启用划词权限；可手动或复制查询。')
                    last_permissions_check = now
                for _ in range(32):
                    try:
                        command = commands.get_nowait()
                    except queue.Empty:
                        break
                    if command['kind'] == 'permissions':
                        AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: True})
                        if hasattr(Q, 'CGRequestListenEventAccess'):
                            Q.CGRequestListenEventAccess()
                        last_permissions_check = 0
                    elif command['kind'] == 'regions':
                        regions = command['regions']
                    elif command['kind'] == 'self_test_pause' and '--native-self-test' in sys.argv:
                        emit('self_test_started')
                        time.sleep(2)
                        emit('self_test_resumed')
                    elif command['kind'] == 'query':
                        if now-command['created'] > 2:
                            emit('mac_query_result', value=dict(version=command['version'], error='取词请求已过期，请重新选词。'))
                            continue
                        if not permissions()['accessibility']:
                            emit('mac_query_result', value=dict(version=command['version'], error='请先开启辅助功能权限，再重新选中单词。'))
                            continue
                        app = NSRunningApplication.runningApplicationWithProcessIdentifier_(int(command['pid']))
                        if not app or not app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps):
                            emit('mac_query_result', value=dict(version=command['version'], error='来源应用已关闭，请重新选词。'))
                            continue
                        pending = dict(command, stage='activate', due=now+.12, deadline=now+1.5)
                if pending and now >= pending['due']:
                    if context()[0] != pending['pid']:
                        emit('mac_query_result', value=dict(version=pending['version'], error='来源应用未能激活，请重新选词。'))
                        pending = None
                    elif pending['stage'] == 'activate':
                        board = NSPasteboard.generalPasteboard()
                        board.clearContents()
                        pending.update(stage='copy', before=int(board.changeCount()), due=now+.035)
                        clipboard(force=True)
                        for down in (True, False):
                            event = Q.CGEventCreateKeyboardEvent(None, 8, down)
                            Q.CGEventSetFlags(event, Q.kCGEventFlagMaskCommand)
                            Q.CGEventPost(Q.kCGHIDEventTap, event)
                    else:
                        board, count = clipboard()
                        value = board.stringForType_(NSPasteboardTypeString) if count != pending['before'] else None
                        word = normalize_query(str(value)) if value and len(value) <= 256 else ''
                        if valid_query(word):
                            emit('mac_query_result', value=dict(version=pending['version'], word=word))
                            pending = None
                        elif now >= pending['deadline']:
                            emit('mac_query_result', value=dict(version=pending['version'], error='没有读取到本次选区，请重新选中或主动复制单词。'))
                            pending = None
                if now-last_clipboard >= .2 and not pending:
                    clipboard()
                    last_clipboard = now
                for _ in range(128):
                    try:
                        raw = raw_events.get_nowait()
                    except queue.Empty:
                        break
                    result = gestures.handle(raw, context())
                    if result:
                        emit(result[0], value=result[1])
                CFRunLoopRunInMode(kCFRunLoopDefaultMode, .025, True)
                # A run loop without any event source may return immediately.
                if not tap:
                    stop.wait(.025)
    finally:
        if tap:
            Q.CGEventTapEnable(tap, False)
            if source_ref:
                CFRunLoopRemoveSource(CFRunLoopGetCurrent(), source_ref, kCFRunLoopCommonModes)
            CFMachPortInvalidate(tap)
        channel.close()


if __name__ == '__main__':
    run()
