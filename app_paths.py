"""Locations shared by source runs and PyInstaller applications."""
import os,sys
from pathlib import Path

def resource_root():
    return Path(sys._MEIPASS) if getattr(sys,'frozen',False) else Path(__file__).resolve().parent

def user_data_dir():
    if sys.platform=='darwin':return Path.home()/'Library'/'Application Support'/'WoerTranslator'
    return Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))/'QingCi'
