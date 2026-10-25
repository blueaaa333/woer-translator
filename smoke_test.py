"""Noninteractive checks executed against each frozen platform build."""
from pathlib import Path
import sys
from lexicon import Lexicon,definition_sections

def run(base):
    import certifi
    from recording_checks import exercise
    audio=exercise()
    assert Path(certifi.where()).is_file()
    base=Path(base);lexicon=Lexicon(base)
    assert '经过充分研究' in definition_sections(lexicon.lookup('well-researched'))['primary'][0]['text']
    assert lexicon.lookup('current')['community']
    for name in ('brand-18.png','沃尔翻译官.png'):assert (base/'assets'/name).is_file()
    assert (base/'licenses'/'WordNet-LICENSE.txt').is_file()
    assert (base/'docs'/'MAC_FIRST_RUN.html').is_file()
    if sys.platform=='win32':assert (base/'DesktopBridge.exe').is_file()
    elif sys.platform=='darwin':
        import AppKit,Quartz,ApplicationServices
        from mac_platform import choose_voice
        assert choose_voice('Daniel en_GB # demo\nSamantha en_US # demo',1)=='Daniel'
        assert hasattr(Quartz,'CGEventTapCreate') and hasattr(ApplicationServices,'AXIsProcessTrustedWithOptions')
    for name in ('db','extra','community','exam'):
        connection=getattr(lexicon,name)
        if connection:connection.close()
    return dict(platform=sys.platform,dictionaries='ok',assets='ok',native_imports='ok',audio=audio)
