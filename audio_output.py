"""Windows speech output with explicit device selection and honest diagnostics."""
import math
import struct
import threading
import time
import wave
from pathlib import Path
from collections import OrderedDict


class AudioOutput:
    def __init__(self):
        self.lock = threading.RLock()
        self.play_lock = threading.Lock()
        self.device = None
        self.generation = 0
        self.last = {}
        self.retained = None
        self.retained_key = None
        self.idle_timer = None
        self.closed = False
        self.pcm = OrderedDict()
        self.pcm_bytes = 0
        self.catalog = []
        self.catalog_at = 0

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
            token = self.generation
            device = self.device
            if device:
                try:device.stop()
                except Exception:pass
        import winsound
        try:winsound.PlaySound(None, 0)
        except RuntimeError:pass
        return token

    def close(self):
        self.stop()
        with self.lock:
            self.closed = True
            if self.idle_timer:self.idle_timer.cancel()
            self._discard()
            self.pcm.clear();self.pcm_bytes = 0

    def _discard(self):
        device=self.retained
        self.retained=None;self.retained_key=None
        if device:device.close()

    def _idle_close(self, device):
        with self.lock:
            if self.retained is device and self.device is None:self._discard()

    def _decode(self, path):
        import miniaudio
        path=Path(path);stat=path.stat()
        key=(str(path.resolve()),stat.st_size,stat.st_mtime_ns)
        with self.lock:
            if key in self.pcm:
                self.pcm.move_to_end(key)
                return (*self.pcm[key],True)
        decoded=miniaudio.decode(path.read_bytes(),output_format=miniaudio.SampleFormat.SIGNED16,
                                 nchannels=2,sample_rate=44100)
        samples=decoded.samples
        peak=max((abs(value) for value in samples),default=0)
        duration=len(samples)/88200
        if peak<=8 or not 0.1<duration<=60:raise RuntimeError('音频为空或接近静音，请重新获取发音')
        size=len(samples)*2
        with self.lock:
            if size<=8*1024*1024 and not self.closed:
                while self.pcm and (len(self.pcm)>=16 or self.pcm_bytes+size>8*1024*1024):
                    _,old=self.pcm.popitem(last=False);self.pcm_bytes-=len(old[0])*2
                self.pcm[key]=(samples,peak,duration);self.pcm_bytes+=size
        return samples,peak,duration,False

    def _ensure_device(self, device_name):
        import miniaudio
        if time.monotonic()-self.catalog_at>1:
            self.catalog=self.devices();self.catalog_at=time.monotonic()
        devices=self.catalog
        selected=next((item for item in devices if item.get('default')),None)
        if device_name:
            matches=[item for item in devices if item['name']==device_name]
            if len(matches)!=1:raise RuntimeError('所选输出设备不可用，请在“声音检查与输出设备”中重新选择')
            selected=matches[0]
        identifier=selected['id'] if selected else None
        device_label=selected['name'] if selected else '系统默认（驱动选择）'
        key=(device_name,device_label)
        with self.lock:
            if self.closed:raise RuntimeError('声音输出已关闭')
            if self.idle_timer:self.idle_timer.cancel()
            reused=self.retained is not None and self.retained_key==key
            if reused:return self.retained,device_label,True
            self._discard()
        # Slow driver initialization must not hold the UI's cancellation lock.
        device=miniaudio.PlaybackDevice(nchannels=2,sample_rate=44100,buffersize_msec=50,
            device_id=identifier,backends=[miniaudio.Backend.WASAPI,miniaudio.Backend.DSOUND,
            miniaudio.Backend.WINMM],app_name='沃尔翻译官')
        with self.lock:
            if self.closed:
                device.close();raise RuntimeError('声音输出已关闭')
            self.retained=device;self.retained_key=key
        return device,device_label,False

    def warm(self, device_name=''):
        # Opening a device emits no sound and sends no query over the network.
        def worker():
            if not self.play_lock.acquire(blocking=False):return
            try:
                device,_,_=self._ensure_device(device_name)
                with self.lock:
                    if self.retained is device and self.device is None:
                        self.idle_timer=threading.Timer(30,self._idle_close,args=(device,))
                        self.idle_timer.daemon=True;self.idle_timer.start()
            except Exception:pass  # The next explicit playback reports errors.
            finally:self.play_lock.release()
        threading.Thread(target=worker,daemon=True).start()

    def play(self, path, device_name='', legacy=False, cancelled=lambda:False):
        generation=self.stop()
        with self.play_lock:
            if self.closed or generation!=self.generation or cancelled():return False
            return self._play(path,device_name,legacy,cancelled,generation)

    def _play(self, path, device_name, legacy, cancelled, generation):
        import miniaudio
        started=time.perf_counter()
        samples,peak,duration,cached=self._decode(path)
        self.last=dict(peak=peak,duration=round(duration,3),requested_device=device_name or '系统默认',pcm_cached=cached)
        if self.closed or cancelled() or generation!=self.generation:return False
        if legacy:
            with self.lock:self._discard()
            import winsound
            self.last.update(backend='Windows 兼容播放',device='Windows 应用音量混合器指定的设备')
            winsound.PlaySound(str(path),winsound.SND_FILENAME|winsound.SND_NODEFAULT)
            return not cancelled() and generation==self.generation
        completed=threading.Event()
        first=True
        def stream():
            nonlocal first
            position=0
            required=yield b''
            while position<len(samples):
                chunk=samples[position:position+required*2];position+=len(chunk)
                if first:
                    first=False;self.last['first_pcm_ms']=round((time.perf_counter()-started)*1000,2)
                required=yield chunk
            completed.set()
            while True:required=yield b'\0'*(required*4)
        generator=stream();next(generator)
        device,device_label,reused=self._ensure_device(device_name)
        with self.lock:
            if self.closed or cancelled() or generation!=self.generation:
                if self.retained is device:
                    self.idle_timer=threading.Timer(30,self._idle_close,args=(device,))
                    self.idle_timer.daemon=True;self.idle_timer.start()
                return False
            self.device=device
            self.last.update(backend=device.backend,device=device_label,device_reused=reused)
        failed=False
        try:
            device.start(generator)
            deadline=time.monotonic()+duration+5
            while not completed.wait(.01):
                if self.closed or cancelled() or generation!=self.generation:return False
                if time.monotonic()>deadline:raise RuntimeError('声音输出超时，请检查输出设备')
            time.sleep(.06)
            return not cancelled() and generation==self.generation
        except Exception:
            failed=True;self.catalog_at=0
            raise
        finally:
            with self.lock:
                if self.device is device:self.device=None
                if self.retained is device:
                    try:device.stop()
                    except Exception:failed=True
                    if failed or self.closed:self._discard()
                    else:
                        self.idle_timer=threading.Timer(30,self._idle_close,args=(device,))
                        self.idle_timer.daemon=True;self.idle_timer.start()


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
