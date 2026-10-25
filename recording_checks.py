"""Check the bundled native decoder without network or third-party recordings."""
import io
import wave


def exercise():
    import miniaudio
    import tempfile
    from pathlib import Path
    from audio_output import test_tone
    source = io.BytesIO()
    with wave.open(source, 'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(22050)
        output.writeframes(b'\0\0' * 6615)
    result = miniaudio.decode(source.getvalue(), output_format=miniaudio.SampleFormat.SIGNED16,
                             nchannels=1, sample_rate=44100)
    assert 12000 < len(result.samples) < 14000
    with tempfile.TemporaryDirectory() as folder:
        tone=test_tone(Path(folder)/'tone.wav')
        test=miniaudio.decode(tone.read_bytes(),output_format=miniaudio.SampleFormat.SIGNED16,nchannels=2,sample_rate=44100)
        assert max(abs(value) for value in test.samples)>1000
    return dict(native_decoder='ok', pcm_bits=16, sample_rate=44100)
