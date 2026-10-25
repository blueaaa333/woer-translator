import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from audio_output import AudioOutput,test_tone


class AudioOutputTests(unittest.TestCase):
    def test_tone_has_real_nonzero_audio_and_missing_device_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            path=test_tone(Path(folder)/'tone.wav')
            output=AudioOutput()
            with patch.object(output,'stop'),patch.object(output,'devices',return_value=[]):
                with self.assertRaisesRegex(RuntimeError,'输出设备不可用'):
                    output.play(path,device_name='disconnected headphones')
            self.assertGreater(output.last['peak'],1000)

    def test_cancellation_never_reports_success_or_opens_device(self):
        with tempfile.TemporaryDirectory() as folder:
            path=test_tone(Path(folder)/'tone.wav')
            output=AudioOutput()
            with patch.object(output,'stop'),patch('miniaudio.PlaybackDevice') as device:
                self.assertFalse(output.play(path,cancelled=lambda:True))
                device.assert_not_called()

    def test_silent_wave_cannot_be_reported_as_success(self):
        import wave
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'silence.wav'
            with wave.open(str(path),'wb') as stream:
                stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(44100)
                stream.writeframes(b'\0\0'*22050)
            with patch.object(AudioOutput,'stop'):
                with self.assertRaisesRegex(RuntimeError,'静音'):AudioOutput().play(path)

    def test_legacy_checks_audio_and_does_not_use_default_beep(self):
        import sys,types
        fake=types.SimpleNamespace(PlaySound=MagicMock(),SND_FILENAME=0x20000,SND_NODEFAULT=2)
        with tempfile.TemporaryDirectory() as folder:
            path=test_tone(Path(folder)/'tone.wav');output=AudioOutput()
            with patch.dict(sys.modules,{'winsound':fake}):
                self.assertTrue(output.play(path,legacy=True))
            self.assertEqual(fake.PlaySound.call_args.args[1],0x20002)

    def test_native_backend_drains_closes_and_records_actual_device(self):
        import miniaudio
        fake=MagicMock();fake.backend='WASAPI'
        def consume(generator):
            for _ in range(15):generator.send(4410)
        fake.start.side_effect=consume
        with tempfile.TemporaryDirectory() as folder:
            path=test_tone(Path(folder)/'tone.wav');output=AudioOutput()
            with patch.object(output,'stop'),patch.object(output,'devices',return_value=[dict(name='Fake speakers',id=None,default=True)]),patch('miniaudio.PlaybackDevice',return_value=fake):
                self.assertTrue(output.play(path))
            self.assertEqual(output.last['device'],'Fake speakers')
            fake.close.assert_called_once()
