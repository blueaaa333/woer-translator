import json,tempfile,unittest
from pathlib import Path
from voice_profile import voice_files


class VoiceProfileTests(unittest.TestCase):
    def test_new_pack_is_preferred_but_original_frontend_is_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('voice','dictionary-voice'):
                (root/(name+'.onnx')).write_bytes(b'model')
                (root/(name+'.onnx.json')).write_text(json.dumps(dict(language=dict(code='en_US'),espeak=dict(voice='en'))))
            before=(root/'dictionary-voice.onnx.json').read_bytes()
            model,path,data,upgraded,key=voice_files(root,2)
            self.assertTrue(upgraded);self.assertEqual(model.name,'dictionary-voice.onnx')
            self.assertEqual(data['espeak']['voice'],'en')
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(len(key),64)

    def test_partial_download_does_not_replace_working_old_voice(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'voice.onnx').write_bytes(b'old')
            (root/'voice.onnx.json').write_text(json.dumps(dict(language=dict(code='en_GB'),espeak=dict(voice='en'))))
            (root/'dictionary-voice.onnx').write_bytes(b'partial')
            self.assertFalse(voice_files(root,1)[3])
            with self.assertRaises(ValueError):voice_files(root,2)
