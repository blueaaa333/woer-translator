"""Scheduled from the frozen App's real mainloop, with real native services."""
import json
import sys
import time
from pathlib import Path


def schedule(app, report):
    import mac_platform as mac
    started = time.monotonic()
    ticks = []
    errors = []
    phase = {'pause': None, 'done': False}
    original_error = app.root.report_callback_exception

    def error(exc, value, tb):
        errors.append(type(value).__name__ + ': ' + str(value))
        original_error(exc, value, tb)
    app.root.report_callback_exception = error

    def finish(problem=None):
        phase['done'] = True
        result = dict(platform=sys.platform, frozen=bool(getattr(sys, 'frozen', False)),
                      gui_heartbeats=len(ticks), elapsed=round(time.monotonic()-started, 2),
                      native_helper=mac.ready(), callback_errors=errors,
                      responsive_during_native_pause=bool(mac._client and mac._client.test_resumed.is_set()))
        if problem or errors:
            result['error'] = problem or 'UI callback failed'
        Path(report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        app.root.destroy()

    def tick():
        if phase['done']:
            return
        try:
            now = time.monotonic()
            ticks.append(now)
            if not phase['pause'] and mac.ready():
                app.lookup('well-researched', accent=0, anchor=(160, 160))
                assert '经过充分研究' in app.text.get('1.0', 'end')
                app.menu()
                app.root.update_idletasks()
                app.settings_popup.destroy()
                app.prompt('current')
                assert app.popup.winfo_exists()
                app.close_floating()
                mac._client.send('self_test_pause')
                phase['pause'] = now
            if phase['pause'] and now-phase['pause'] >= 3:
                assert mac.ready(), 'Native helper disconnected during the UI check'
                assert mac._client.test_resumed.is_set(), 'Native helper did not execute its pause'
                during = [t for t in ticks if phase['pause']+.15 <= t <= phase['pause']+1.85]
                assert len(during) >= 15, 'Tk stopped responding while helper was stalled'
                assert max(b-a for a, b in zip(during, during[1:])) < .5, 'UI heartbeat stalled'
                finish()
                return
            if now-started > 15:
                finish('Native helper never became ready')
                return
            app.root.after(50, tick)
        except Exception as exc:
            finish(str(exc))
    app.root.after(100, tick)
