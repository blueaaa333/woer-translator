"""Windows speech output with explicit device selection and honest diagnostics."""
import math
import struct
import threading
import time
import wave
from pathlib import Path


class AudioOutput:
    def __init__(self):
        self.lock = threading.RLock()
        self.device = None
        self.generation = 0
        self.last = {}

    def devices(self):
        import miniaudio
        context=miniaudio.Devices(backends=[miniaudio.Backend.WASAPI,
            miniaudio.Backend.DSOUND, miniaudio.Backend.WINMM])
        infos=miniaudio.ffi.new('ma_device_info**');count=miniaudio.ffi.new('ma_uint32*')
        result=miniaudio.lib.ma_context_get_devices(context._context,infos,count,miniaudio.ffi.NULL,miniaudio.ffi.NULL)
        if result!=miniaudio.lib.MA_SUCCESS:raise RuntimeError('无法读取声音输出设备')
        return [dict(name=miniaudio.ffi.string(infos[0][i].name).decode('utf-8',errors='replace'),
            id=miniaudio.ffi.new('ma_device_id *',infos[0][i].id),default=bool(infos[0][i].isDefault))
            for i in range(count[0])]

    def stop(self):
        with self.lock:
            self.generation += 1
            device = self.device
        if device:
            try:device.stop()
            except Exception:pass
        import winsound
        try:winsound.PlaySound(None, 0)
        except RuntimeError:pass

    def play(self, path, device_name='', legacy=False, cancelled=lambda:False):
        import miniaudio
        self.stop()
        generation = self.generation
        # Native decoder file APIs may not handle Chinese Windows user paths.
        decoded = miniaudio.decode(Path(path).read_bytes(), output_format=miniaudio.SampleFormat.SIGNED16,
                                       nchannels=2, sample_rate=44100)
        peak = max((abs(value) for value in decoded.samples), default=0)
        duration = len(decoded.samples) / 88200
        if peak <= 8 or not 0.1 < duration <= 60:
            raise RuntimeError('音频为空或接近静音，请重新获取发音')
        self.last = dict(peak=peak, duration=round(duration,3), requested_device=device_name or '系统默认')
        if cancelled() or generation != self.generation:return False
        if legacy:
            import winsound
            self.last.update(backend='Windows 兼容播放', device='Windows 应用音量混合器指定的设备')
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
            return not cancelled() and generation == self.generation
        identifier = None
        devices=self.devices()
        selected=next((item for item in devices if item.get('default')),None)
        if device_name:
            matches = [item for item in devices if item['name'] == device_name]
            if len(matches) != 1:
                raise RuntimeError('所选输出设备不可用，请在“声音检查与输出设备”中重新选择')
            selected=matches[0]
        if selected:identifier=selected['id']
        completed = threading.Event()
        def stream():
            position = 0
            required = yield b''
            while position < len(decoded.samples):
                chunk = decoded.samples[position:position + required*2]
                position += len(chunk)
                required = yield chunk
            completed.set()
            while True:
                required = yield b'\0' * (required*4)
        generator = stream();next(generator)
        device = miniaudio.PlaybackDevice(nchannels=2, sample_rate=44100, buffersize_msec=100,
            device_id=identifier, backends=[miniaudio.Backend.WASAPI, miniaudio.Backend.DSOUND,
            miniaudio.Backend.WINMM], app_name='沃尔翻译官')
        try:
            with self.lock:
                if cancelled() or generation != self.generation:return False
                self.device = device
            self.last.update(backend=device.backend,
                device=selected['name'] if selected else '系统默认（驱动选择）')
            device.start(generator)
            deadline = time.monotonic() + duration + 5
            while not completed.wait(.025):
                if cancelled() or generation != self.generation:return False
                if time.monotonic() > deadline:raise RuntimeError('声音输出超时，请检查输出设备')
            time.sleep(.15)  # Allow the final hardware buffer to drain.
            return not cancelled() and generation == self.generation
        finally:
            with self.lock:
                if self.device is device:self.device = None
            device.close()


def test_tone(path):
    """An original short test tone; requires neither Internet nor a voice pack."""
    path = Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    frames = 30870
    with wave.open(str(path),'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(44100)
        samples = [round(5000 * min(1,i/1500,(frames-i)/1500) * math.sin(2*math.pi*440*i/44100))
                   for i in range(frames)]
        output.writeframes(struct.pack('<'+'h'*len(samples),*samples))
    return path
