import unittest
from selection_apps import supported_process

class SelectionAppsTests(unittest.TestCase):
    def test_embedded_browser_and_wechat(self):
        for name in ('ChatGPT.exe','Codex','WeChat','Weixin.exe','msedgewebview2'):
            self.assertTrue(supported_process(name,False),name)
    def test_compatibility_for_unknown_application(self):
        self.assertTrue(supported_process('ExamplePDFViewer',True))
        self.assertFalse(supported_process('ExamplePDFViewer',False))
    def test_system_and_credential_apps_are_excluded(self):
        for name in ('','explorer','LockApp','CredentialUIBroker','1Password.exe','Bitwarden','WoerTranslator'):
            self.assertFalse(supported_process(name,True),name)
