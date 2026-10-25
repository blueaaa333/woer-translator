"""Exercise actual menu choices and fresh App instances with isolated user data."""
import sys
import tempfile
import tkinter as tk
from pathlib import Path

from menu_layout_checks import descendants


def exercise(app_type):
    module = sys.modules[app_type.__module__]
    original = module.DATA
    app = None
    with tempfile.TemporaryDirectory() as folder:
        module.DATA = Path(folder)
        try:
            def start():
                current = app_type(testing=True)
                # Only this disposable directory may be written during the test.
                assert current.preference_store.path.parent == Path(folder)
                current.preference_store.read_only = False
                current.root.update()
                return current

            def toggle(current):
                current.menu();current.root.update()
                label = next(w for w in descendants(current.settings_popup)
                             if isinstance(w, tk.Label) and w.cget('text') == '查词后自动朗读')
                button = next(w for w in label.master.winfo_children() if isinstance(w, tk.Button))
                button.invoke()

            def accent(current, label):
                next(w for w in descendants(current.settings_popup)
                     if isinstance(w, tk.Button) and w.cget('text') == label).invoke()

            app = start()
            assert app.accent == 0
            toggle(app);accent(app, '英式')
            assert app.accent == app.preferred_accent == 1
            app.root.destroy();app = start()
            assert app.accent == app.preferred_accent == 1
            spoken = []
            app.speak = spoken.append
            app.lookup('current', accent=0)
            assert not spoken and app.accent == 1
            app.lookup('current')
            assert spoken == [1]
            app.menu();accent(app, '美式')
            assert app.accent == app.preferred_accent == 2
            app.root.destroy();app = start()
            assert app.accent == app.preferred_accent == 2
            toggle(app)
            assert app.accent == 0 and app.preferred_accent == 2
            app.root.destroy();app = start()
            assert app.accent == 0 and app.preferred_accent == 2
            toggle(app)
            assert app.accent == 2
            # Ordinary GUI tests must never change real preferences.
            saved = app.preference_store.path.read_bytes()
            app.preference_store.read_only = True
            app.set_accent(0)
            assert app.preference_store.path.read_bytes() == saved
            return dict(restart_uk='ok', restart_us='ok', restart_disabled='ok',
                        remember_accent_when_disabled='ok', query_override='ok',
                        test_mode_no_user_writes='ok')
        finally:
            if app is not None and app.root.winfo_exists():
                app.root.destroy()
            module.DATA = original
