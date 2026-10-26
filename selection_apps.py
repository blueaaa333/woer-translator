"""Process routing only: showing an action strip never reads selected text."""
SUPPORTED = frozenset({'msedge','chrome','firefox','qianwen','360se','360chrome','qqbrowser','quark','acrobat','acrord32','sumatrapdf','wps','winword','notepad','notepad++','pdfxedit','foxitpdfreader','chatgpt','codex','wechat','weixin','msedgewebview2'})
EXCLUDED = frozenset({'explorer','shellexperiencehost','startmenuexperiencehost','searchhost','lockapp','logonui','credentialuibroker','keepass','keepassxc','1password','bitwarden','desktopbridge','woertranslator','qingci'})

def supported_process(name, compatibility=True):
    name=name.strip().lower()
    if name.endswith('.exe'):name=name[:-4]
    if not name or name in EXCLUDED:return False
    return name in SUPPORTED or bool(compatibility)
