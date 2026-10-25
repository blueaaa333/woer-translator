import hashlib,io,json,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from scripts import setup_speech


class SpeechInstallTests(unittest.TestCase):
    def test_large_model_ranges_are_validated_and_joined_in_order(self):
        payload=b'0123456789';ranges=[]
        def response(request,**kwargs):
            start,end=map(int,request.get_header('Range').split('=')[1].split('-'));ranges.append((start,end))
            stream=io.BytesIO(payload[start:end+1]);stream.headers={'Content-Range':f'bytes {start}-{end}/10'}
            return stream
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'model.part'
            with patch.object(setup_speech,'CHUNK_BYTES',4),patch.object(setup_speech.urllib.request,'urlopen',side_effect=response):
                setup_speech.fetch_asset(dict(url='https://huggingface.co/model',bytes=10),target)
            self.assertEqual(target.read_bytes(),payload)
            self.assertEqual(ranges,[(0,3),(4,7),(8,9)])

    def test_upgrade_keeps_old_voice_and_does_not_rewrite_identical_runtime(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';(source/'scripts').mkdir(parents=True)
            target=root/'user';legacy=target/'speech/voices/uk/voice.onnx';legacy.parent.mkdir(parents=True);legacy.write_bytes(b'legacy-model')
            runtime=target/'speech/runtime/piper/piper.exe';runtime.parent.mkdir(parents=True);runtime.write_bytes(b'runtime')
            before=runtime.stat().st_mtime_ns
            archive=io.BytesIO()
            with zipfile.ZipFile(archive,'w') as output:output.writestr('piper/piper.exe',b'runtime')
            payloads={'https://example/model':b'new-model','https://example/runtime':archive.getvalue()}
            files=[dict(url=url,path=path,sha256=hashlib.sha256(payloads[url]).hexdigest()) for url,path in
                [('https://example/model','speech/voices/uk/dictionary-voice.onnx'),('https://example/runtime','speech/piper_windows_amd64.zip')]]
            (source/'scripts/speech-downloads.json').write_text(json.dumps(dict(files=files)))
            with patch.object(setup_speech,'ROOT',source),patch.object(setup_speech.urllib.request,'urlopen',side_effect=lambda request,**kwargs:io.BytesIO(payloads[request.full_url])):
                setup_speech.install(target)
            self.assertEqual(legacy.read_bytes(),b'legacy-model')
            self.assertEqual((target/'speech/voices/uk/dictionary-voice.onnx').read_bytes(),b'new-model')
            self.assertEqual(runtime.stat().st_mtime_ns,before)
