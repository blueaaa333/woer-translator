import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from mac_platform import choose_voice
from pronunciation import SpeechEngine,SpeechUnavailable

class PlatformSupportTests(unittest.TestCase):
    def test_accent_selection_requires_exact_locale(self):
        catalog='Alex en_US # test\nKaren en_AU # test\nDaniel en_GB # test'
        self.assertEqual(choose_voice(catalog,1),'Daniel')
        self.assertEqual(choose_voice(catalog,2),'Alex')
        self.assertIsNone(choose_voice('Karen en_AU # test',1))
    def test_missing_voice_has_actionable_message(self):
        with tempfile.TemporaryDirectory() as folder:
            engine=SpeechEngine(folder,Path(folder)/'cache')
            try:
                with patch('pronunciation.subprocess.check_output',return_value='Alex en_US # test'):
                    with self.assertRaisesRegex(SpeechUnavailable,'系统缺少英式语音'):engine.render_system_voice('current',1)
            finally:engine.close()
    def test_resources_and_user_data_separate(self):
        import app_paths
        with patch('sys.platform','darwin'),patch.object(Path,'home',return_value=Path('/example')):
            self.assertEqual(app_paths.user_data_dir(),Path('/example/Library/Application Support/WoerTranslator'))
