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
    app.prompt('current');app.root.update()
    assert app.popup.winfo_ismapped()
    app.close_floating();app.root.update()
    assert not app.popup.winfo_exists()
    print(json.dumps({'platform':sys.platform,'gui':'ok','lookup':'ok','anchored_settings':'ok','toolbar':'ok'}))
finally:app.root.destroy()
