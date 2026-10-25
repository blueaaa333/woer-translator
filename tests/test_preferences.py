import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from preferences import PreferenceStore


class PreferenceTests(unittest.TestCase):
    def test_choice_survives_a_new_process_and_unknown_settings_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preferences.json'
            store = PreferenceStore(path)
            for accent in (1, 2, 0):
                store.write(dict(auto_read=accent != 0, accent=accent,
                                 preferred_accent=accent or 2, check_updates=False))
                source = 'from preferences import PreferenceStore;import sys,json;print(json.dumps(PreferenceStore(sys.argv[1]).read()))'
                result = json.loads(subprocess.check_output(
                    [sys.executable, '-c', source, str(path)], text=True))
                self.assertEqual(result['accent'], accent)
                self.assertEqual(result['auto_read'], accent != 0)
                self.assertEqual(result['preferred_accent'], accent or 2)
                self.assertFalse(result['check_updates'])

    def test_first_install_is_off_and_legacy_enabled_choice_migrates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preferences.json'
            store = PreferenceStore(path)
            self.assertEqual(store.read()['accent'], 0)
            for accent in (1, 2):
                path.write_text(json.dumps({'accent': accent}), encoding='utf-8')
                self.assertEqual(store.read()['accent'], accent)
                self.assertTrue(store.read()['auto_read'])

    def test_invalid_data_uses_safe_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preferences.json'
            for text in ('[]', 'null', '{', '{"accent":true,"preferred_accent":99}'):
                path.write_text(text, encoding='utf-8')
                self.assertEqual(PreferenceStore(path).read()['accent'], 0)
                self.assertEqual(PreferenceStore(path).read()['preferred_accent'], 2)

    def test_failed_replacement_keeps_previous_choice_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preferences.json'
            store = PreferenceStore(path)
            store.write({'accent': 1})
            original = path.read_bytes()
            with patch('preferences.os.replace', side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):
                    store.write({'accent': 0})
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_test_mode_cannot_overwrite_user_preferences(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'preferences.json'
            PreferenceStore(path).write({'accent': 1})
            original = path.read_bytes()
            PreferenceStore(path, read_only=True).write({'accent': 0})
            self.assertEqual(path.read_bytes(), original)
