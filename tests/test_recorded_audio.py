import copy
import hashlib
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from recorded_audio import Recordings, licence, select_recording
from pronunciation import SpeechEngine


def fixture():
    output = io.BytesIO()
    with wave.open(output, 'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(22050)
        stream.writeframes(b'\0\0' * 6615)
    data = output.getvalue()
    page = dict(title='File:En-us-water.wav', imageinfo=[dict(
        url='https://upload.wikimedia.org/wikipedia/commons/a/ab/En-us-water.wav',
        descriptionurl='https://commons.wikimedia.org/wiki/File:En-us-water.wav',
        size=len(data), duration=0.3, mime='audio/wav', sha1=hashlib.sha1(data).hexdigest(),
        extmetadata={k:dict(value=v) for k,v in dict(Artist='<b>Test Speaker</b>',
            LicenseUrl='https://creativecommons.org/licenses/by-sa/3.0/', Restrictions='').items()})])
    return page, data


class RecordedAudioTests(unittest.TestCase):
    def test_accepts_specific_free_licences_only(self):
        for url in ('https://creativecommons.org/licenses/by-sa/3.0/',
                    'http://creativecommons.org/licenses/by/3.0/us/deed.en',
                    'https://creativecommons.org/publicdomain/zero/1.0/'):
            self.assertIsNotNone(licence(url))
        for url in ('https://creativecommons.org/licenses/by-nc/4.0/',
                    'https://creativecommons.org/licenses/by-nd/4.0/',
                    'https://creativecommons.org.attacker.example/licenses/by/4.0/', '', 'MIT'):
            self.assertIsNone(licence(url))

    def test_never_substitutes_accent_or_another_word(self):
        page, _ = fixture()
        self.assertIsNotNone(select_recording(page, 'water', 2))
        self.assertIsNone(select_recording(page, 'water', 1))
        self.assertIsNone(select_recording(page, 'waters', 2))
        for key in ('Artist', 'LicenseUrl'):
            changed = copy.deepcopy(page)
            changed['imageinfo'][0]['extmetadata'].pop(key)
            self.assertIsNone(select_recording(changed, 'water', 2))
        page['imageinfo'][0]['extmetadata']['Restrictions']['value'] = 'personality rights'
        self.assertIsNone(select_recording(page, 'water', 2))

    def test_original_hash_attribution_and_offline_cache(self):
        page, original = fixture()
        catalog = json.dumps(dict(query=dict(pages=[page]))).encode()
        with tempfile.TemporaryDirectory() as folder:
            client = Recordings(folder)
            with patch('recorded_audio.download', side_effect=[catalog, original]) as fetch:
                result = client.get('water', 2)
                self.assertTrue(result.is_file())
                self.assertEqual(fetch.call_count, 2)
            self.assertEqual(client.last['author'], 'Test Speaker')
            self.assertEqual(client.last['licence'], 'CC BY-SA 3.0')
            self.assertEqual((Path(folder)/client.last['original_file']).read_bytes(), original)
            self.assertIn('Test Speaker', client.attribution_path().read_text(encoding='utf-8'))
            with patch('recorded_audio.download', side_effect=AssertionError('offline')):
                self.assertEqual(Recordings(folder).get('water', 2), result)

    def test_mismatched_hash_and_network_failure_do_not_play_audio(self):
        page, _ = fixture()
        catalog = json.dumps(dict(query=dict(pages=[page]))).encode()
        with tempfile.TemporaryDirectory() as folder:
            client = Recordings(folder)
            with patch('recorded_audio.download', side_effect=[catalog, b'incorrect']):
                self.assertIsNone(client.get('water', 2))
            self.assertFalse(list(Path(folder).glob('*.wav')))
            with patch('recorded_audio.download', side_effect=TimeoutError) as fetch:
                client = Recordings(folder)
                self.assertIsNone(client.get('water', 2))
                self.assertIsNone(client.get('hello', 2))
                self.assertEqual(fetch.call_count, 1)

    def test_recording_does_not_require_a_local_voice_model(self):
        with tempfile.TemporaryDirectory() as folder:
            engine = SpeechEngine(folder, Path(folder)/'cache')
            try:
                engine.recordings.last = {'kind':'recording','accent':1}
                expected = Path(folder)/'human.wav'
                with patch.object(engine.recordings, 'get', return_value=expected):
                    self.assertEqual(engine.render('water', 1), expected)
                self.assertEqual(engine.last_source['accent'], 1)
                engine.prefer_recordings = False
                with patch.object(engine.recordings, 'get', side_effect=AssertionError('network disabled')):
                    with patch.object(engine, 'render_system_voice', return_value=Path(folder)/'system.wav'), patch('pronunciation.sys.platform', 'darwin'):
                        self.assertEqual(engine.render('water', 2).name, 'system.wav')
                self.assertIsNone(engine.last_source)
            finally:
                engine.close()
