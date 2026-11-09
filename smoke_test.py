"""Noninteractive checks executed against each frozen platform build."""
from pathlib import Path
import sys
from lexicon import Lexicon,definition_sections

def run(base):
    import certifi
    from recording_checks import exercise
    audio=exercise()
    assert Path(certifi.where()).is_file()
    base=Path(base)
    from scripts.distribution_audit import audit
    distribution=audit(base)
    lexicon=Lexicon(base)
    assert '经过充分研究' in definition_sections(lexicon.lookup('well-researched'))['primary'][0]['text']
    assert lexicon.lookup('current')['community']
    complete_meanings={
        'optimum':('最适条件','最佳效果','最优的','最适宜的'),
        'current':('涌流','趋势','流通的','现在的','当前的','流行的'),
        'bank':('银行','堤','岸','库'),
    }
    for word,expected in complete_meanings.items():
        primary='\n'.join(section['text'] for section in definition_sections(lexicon.lookup(word))['primary'])
        for meaning in expected:assert meaning in primary,f'{word} is missing public Chinese meaning: {meaning}'
    optimum='\n'.join(section['text'] for section in definition_sections(lexicon.lookup('optimum'))['primary'])
    assert 'adj.' in optimum,'optimum lost its adjective sense'
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
    return dict(platform=sys.platform,dictionaries='ok',assets='ok',native_imports='ok',audio=audio,distribution=distribution)
