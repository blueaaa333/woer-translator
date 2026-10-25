"""Exercise the real Tk UI without global listeners or synthetic user input."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import App

app=App(testing=True)
try:
    app.root.update()
    app.accent=0
    app.lookup('well-researched',accent=0,anchor=(180,180));app.root.update()
    assert app.word=='well-researched'
    assert '经过充分研究' in app.text.get('1.0','end')
    app.lookup('positioning',accent=0,anchor=(180,180));app.select_tab('forms');app.root.update()
    assert app.word=='positioning'
    app.menu();app.root.update()
    initial=(app.settings_popup.winfo_x(),app.settings_popup.winfo_y())
    app.preferred_accent=1;app.position_settings();app.root.update()
    assert initial==(app.settings_popup.winfo_x(),app.settings_popup.winfo_y())
    app.settings_popup.destroy()
    from menu_layout_checks import exercise
    menu_check=exercise(app)
    app.prompt('current');app.root.update()
    assert app.popup.winfo_ismapped()
    app.close_floating();app.root.update()
    assert not app.popup.winfo_exists()
    from updater import Release,asset_name
    future=Release('9.9.9',asset_name('9.9.9'),'unused','0'*64,1048576,'包含软件内更新提醒和问题修复。')
    app.updates.release=future;app.updates.show();app.root.update()
    assert '9.9.9' in app.updates.version_label.cget('text')
    assert app.updates.action.cget('text')=='下载更新'
    assert app.updates.action.winfo_rooty()+app.updates.action.winfo_height()<=app.updates.window.winfo_rooty()+app.updates.window.winfo_height()
    app.updates.window.destroy()
    if sys.platform=='win32':
        from unittest.mock import patch
        import time
        with patch.object(app.player,'devices',return_value=[dict(name='Test speakers',id=None,default=True)]):
            app.audio_check();app.root.update()
            for _ in range(15):app.root.update();time.sleep(.01)
        from menu_layout_checks import descendants
        labels=[w.cget('text') for w in descendants(app.audio_window) if w.winfo_class()=='Button']
        assert '播放测试音' in labels and '复制声音检查信息' in labels
        app.audio_window.destroy()
    if sys.platform=='darwin':
        app.mac_welcome();app.root.update()
        assert app.welcome_popup.winfo_exists()
        app.welcome_popup.destroy()
    print(json.dumps({'platform':sys.platform,'gui':'ok','lookup':'ok','anchored_settings':'ok','toolbar':'ok','menu_layout':menu_check}))
finally:app.root.destroy()

from preference_checks import exercise as check_preferences
print(json.dumps({'preferences':check_preferences(App)}))

from recording_checks import exercise as check_decoder
print(json.dumps({'audio':check_decoder()}))
