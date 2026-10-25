import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from audio_output import AudioOutput,test_tone


class AudioOutputTests(unittest.TestCase):
    def test_slow_device_open_does_not_block_cancel_or_leak_after_close(self):
        import threading,time,sys,types
        entered=threading.Event();release=threading.Event();fake=MagicMock();output=AudioOutput()
        def opening(**kwargs):entered.set();release.wait(2);return fake
        sound=types.SimpleNamespace(PlaySound=lambda *args:None)
        with patch.dict(sys.modules,{'winsound':sound}),patch.object(output,'devices',return_value=[dict(name='speakers',id=None,default=True)]),patch('miniaudio.PlaybackDevice',side_effect=opening):
            output.warm();self.assertTrue(entered.wait(2))
            started=time.monotonic();output.close()
            self.assertLess(time.monotonic()-started,1)
            release.set()
            with output.play_lock:pass
            fake.close.assert_called_once()

    def test_pcm_cache_has_a_bound_and_invalidates_changed_file(self):
        import os,wave
        with tempfile.TemporaryDirectory() as folder:
            output=AudioOutput()
            for i in range(17):output._decode(test_tone(Path(folder)/f'tone-{i}.wav'))
            self.assertEqual(len(output.pcm),16)
            self.assertLessEqual(output.pcm_bytes,8*1024*1024)
            path=Path(folder)/'tone-16.wav';before=path.stat()
            with wave.open(str(path),'wb') as stream:
                stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(44100)
                stream.writeframes(b'\0\0'*30870)
            os.utime(path,ns=(before.st_atime_ns,before.st_mtime_ns+1000000000))
            with self.assertRaisesRegex(RuntimeError,'静音'):output._decode(path)

    def test_silent_prewarm_does_not_start_playback_and_releases_on_close(self):
        import threading
        ready=threading.Event();fake=MagicMock();fake.backend='WASAPI'
        output=AudioOutput()
        def opened(**kwargs):ready.set();return fake
        with patch.object(output,'stop',return_value=0),patch.object(output,'devices',return_value=[dict(name='speakers',id=None,default=True)]),patch('miniaudio.PlaybackDevice',side_effect=opened):
            output.warm();self.assertTrue(ready.wait(2))
            with output.play_lock:pass
            fake.start.assert_not_called()
            output.close();fake.close.assert_called_once()

    def test_tone_has_real_nonzero_audio_and_missing_device_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            path=test_tone(Path(folder)/'tone.wav')
            output=AudioOutput()
            with patch.object(output,'stop',return_value=0),patch.object(output,'devices',return_value=[]):
                with self.assertRaisesRegex(RuntimeError,'输出设备不可用'):
                    output.play(path,device_name='disconnected headphones')
            self.assertGreater(output.last['peak'],1000)

    def test_cancellation_never_reports_success_or_opens_device(self):
        with tempfile.TemporaryDirectory() as folder:
            path=test_tone(Path(folder)/'tone.wav')
            output=AudioOutput()
            with patch.object(output,'stop',return_value=0),patch('miniaudio.PlaybackDevice') as device:
                self.assertFalse(output.play(path,cancelled=lambda:True))
                device.assert_not_called()

    def test_silent_wave_cannot_be_reported_as_success(self):
        import wave
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'silence.wav'
            with wave.open(str(path),'wb') as stream:
                stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(44100)
                stream.writeframes(b'\0\0'*22050)
            with patch.object(AudioOutput,'stop',return_value=0):
                with self.assertRaisesRegex(RuntimeError,'静音'):AudioOutput().play(path)

    def test_legacy_checks_audio_and_does_not_use_default_beep(self):
        import sys,types
        fake=types.SimpleNamespace(PlaySound=MagicMock(),SND_FILENAME=0x20000,SND_NODEFAULT=2)
        with tempfile.TemporaryDirectory() as folder:
            path=test_tone(Path(folder)/'tone.wav');output=AudioOutput()
            with patch.dict(sys.modules,{'winsound':fake}):
                self.assertTrue(output.play(path,legacy=True))
            self.assertEqual(fake.PlaySound.call_args.args[1],0x20002)

    def test_native_backend_reuses_device_and_pcm_until_close(self):
        import miniaudio
        fake=MagicMock();fake.backend='WASAPI'
        def consume(generator):
            for _ in range(15):generator.send(4410)
        fake.start.side_effect=consume
        with tempfile.TemporaryDirectory() as folder:
            path=test_tone(Path(folder)/'tone.wav');output=AudioOutput()
            with patch.object(output,'stop',return_value=0),patch.object(output,'devices',return_value=[dict(name='Fake speakers',id=None,default=True)]),patch('miniaudio.PlaybackDevice',return_value=fake):
                self.assertTrue(output.play(path))
                self.assertTrue(output.play(path))
                self.assertTrue(output.last['device_reused'])
                self.assertTrue(output.last['pcm_cached'])
                self.assertEqual(output.last['device'],'Fake speakers')
                fake.close.assert_not_called()
                output.close()
                fake.close.assert_called_once()
