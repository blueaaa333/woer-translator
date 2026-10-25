"""Check the bundled native decoder without network or third-party recordings."""
import io
import wave


def exercise():
    import miniaudio
    source = io.BytesIO()
    with wave.open(source, 'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(22050)
        output.writeframes(b'\0\0' * 6615)
    result = miniaudio.decode(source.getvalue(), output_format=miniaudio.SampleFormat.SIGNED16,
                             nchannels=1, sample_rate=44100)
    assert 12000 < len(result.samples) < 14000
    return dict(native_decoder='ok', pcm_bits=16, sample_rate=44100)
