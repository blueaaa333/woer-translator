import atexit,ctypes,hashlib,json,os,subprocess,threading,wave,queue,time,sys,platform
from pathlib import Path
from lexicon import normalize_query,valid_query
from recorded_audio import Recordings
from voice_profile import voice_files

def phonetic_labels(result):
    target=normalize_query(result['word']).replace(' ','-').lower()
    selected={};generic=''
    def same(word):return normalize_query(word).replace(' ','-').lower()==target
    def ipa(text):return '/'+text.strip('/[] ').replace('ә','ə').replace("'",'ˈ').replace(':','ː')+'/'
    for entry in result['entries']:
        if same(entry['word']) and entry['phonetic']:
            generic=ipa(entry['phonetic']);break
    for entry in result.get('community',[]):
        if not same(entry['lemma']):continue
        for sound in entry['sounds']:
            tags=set(tag.lower() for tag in sound['tags']);value=sound['ipa']
            score=(3 if value.startswith('/') else 0)+(2 if entry['edition']=='en' else 0)
            accents=[]
            if tags&{'uk','received-pronunciation','british'}:accents.append(1)
            if tags&{'us','general-american','american'}:accents.append(2)
            for accent in accents:
                if accent not in selected or score>selected[accent][0]:selected[accent]=(score,value)
            if not generic and not tags and value.startswith('/'):generic=value
    missing=[accent for accent in (1,2) if accent not in selected]
    note=''
    if generic and missing:note='通用音标' if len(missing)==2 else ('英音栏为通用音标' if missing[0]==1 else '美音栏为通用音标')
    return dict(uk=selected.get(1,(0,generic))[1],us=selected.get(2,(0,generic))[1],note=note)

class SpeechUnavailable(RuntimeError):pass

def _ascii_piper_path(path,working_dir):
    path=Path(path)
    try:relative=os.path.relpath(str(path),str(working_dir))
    except ValueError:relative=str(path)
    if relative.isascii():return relative
    if os.name!='nt':return str(path)
    buffer=ctypes.create_unicode_buffer(32768)
    length=ctypes.windll.kernel32.GetShortPathNameW(str(path),buffer,len(buffer))
    short=buffer.value
    if not length or not short or not short.isascii():
        raise SpeechUnavailable('离线语音路径包含当前 Piper 无法读取的字符')
    return short

class SpeechEngine:
    def __init__(self,base,cache,user_root=None):
        self.bundle_root=Path(base)/'speech';self.root=Path(user_root) if user_root else self.bundle_root;self.cache=Path(cache)
        self.recordings=Recordings(self.cache/'recordings');self.prefer_recordings=True;self.last_source=None
        self.recording_gate=threading.Lock()
        self.processes=set();self.servers={};self.lock=threading.RLock();self.closed=threading.Event()
        atexit.register(self.close);threading.Thread(target=self.reap,daemon=True).start()
    def _voice_folder(self,accent):
        name='uk' if accent==1 else 'us'
        user_folder=self.root/'voices'/name
        bundled_folder=self.bundle_root/'voices'/name
        for folder in (user_folder,bundled_folder):
            try:
                model,_,_,_,_=voice_files(folder,accent)
                if model.name=='dictionary-voice.onnx' and model.stat().st_size<1_000_000:
                    raise ValueError('Managed voice model is incomplete')
                return folder
            except (OSError,ValueError,KeyError,TypeError):pass
        return user_folder
    def _runtime_executable(self):
        candidates=(self.root/'runtime'/'piper'/'piper.exe',self.root/'runtime'/'piper.exe',
            self.bundle_root/'runtime'/'piper'/'piper.exe',self.bundle_root/'runtime'/'piper.exe')
        return next((path for path in candidates if path.is_file()),None)
    def cached_synthesis(self,word,accent):
        try:
            model,_,config,upgraded,config_hash=voice_files(self._voice_folder(accent),accent)
            expected='en_GB' if accent==1 else 'en_US'
            length_scale='1.0' if upgraded else '1.05'
            key=f'dictionary-profile-v1|{expected}|{config_hash}|{length_scale}|{config.get("dataset")}|{model.stat().st_size}|{model.stat().st_mtime_ns}|{word.lower()}'
            target=self.cache/(hashlib.sha256(key.encode()).hexdigest()+'.wav')
            return target if target.exists() and self.valid_wave(target) else None
        except (OSError,ValueError):return None
    def quick_recording(self,word,accent):
        try:
            voice_files(self._voice_folder(accent),accent)
            local_available=True
        except (OSError,ValueError):local_available=False
        if not local_available:return self.recordings.get(word,accent)
        if not self.recording_gate.acquire(blocking=False):return None
        done=threading.Event();result=[]
        def fetch():
            try:
                worker=Recordings(self.recordings.folder)
                audio=worker.get(word,accent)
                if audio:result.append((audio,worker.last))
            except Exception:pass
            finally:
                self.recording_gate.release();done.set()
        threading.Thread(target=fetch,daemon=True).start()
        done.wait(.2)
        if done.is_set() and result:
            audio,self.recordings.last=result[0];return audio
        return None
    def render(self,word,accent):
        if self.closed.is_set():raise RuntimeError('Speech engine closed')
        word=normalize_query(word)
        if accent not in (1,2) or not valid_query(word):raise ValueError('Invalid speech request')
        self.last_source=None
        if self.prefer_recordings:
            audio=self.recordings.cached(word.lower(),accent)
            if audio:
                self.last_source=self.recordings.last
                return audio
        local=self.cached_synthesis(word,accent)
        if local:return local
        if self.prefer_recordings:
            # Fetch on a separate bounded worker: a slow network must not hold
            # up an installed local voice. Never queue repeated background jobs.
            audio=self.quick_recording(word,accent)
            if self.closed.is_set():raise RuntimeError('Speech engine closed')
            if audio:
                self.last_source=self.recordings.last
                return audio
        if sys.platform=='darwin':return self.render_system_voice(word,accent)
        folder=self._voice_folder(accent)
        try:model,config_path,config,upgraded,config_hash=voice_files(folder,accent)
        except FileNotFoundError:
            label='英式' if accent==1 else '美式'
            prefix='本次未取得'+label+'真人录音，且' if self.prefer_recordings else ''
            raise SpeechUnavailable(prefix+label+'离线语音尚未安装；请在“···”下载或升级语音（约200 MB）')
        expected='en_GB' if accent==1 else 'en_US'
        length_scale='1.0' if upgraded else '1.05'
        executable=self._runtime_executable()
        if executable is None:raise SpeechUnavailable('请在“···”中下载英美离线语音')
        self.cache.mkdir(parents=True,exist_ok=True)
        key=f'dictionary-profile-v1|{expected}|{config_hash}|{length_scale}|{config.get("dataset")}|{model.stat().st_size}|{model.stat().st_mtime_ns}|{word.lower()}'
        target=self.cache/(hashlib.sha256(key.encode()).hexdigest()+'.wav')
        if target.exists() and self.valid_wave(target):return target
        # This upstream Windows runtime uses narrow file paths. Pass ASCII-only
        # paths relative to its working directory, including under Chinese names.
        temporary_dir=self.cache/'_speech_tmp';temporary_dir.mkdir(parents=True,exist_ok=True)
        temporary=temporary_dir/(target.stem+'.wav')
        with self.lock:
            if self.closed.is_set():raise RuntimeError('Speech engine closed')
            server=self.servers.get(accent)
            signature=(str(model),model.stat().st_mtime_ns,config_hash,length_scale)
            if server is not None and server.get('signature')!=signature:
                if server['proc'].poll() is None:server['proc'].terminate()
                self.processes.discard(server['proc']);server=None
            if server is None or server['proc'].poll() is not None:
                command=[str(executable),'--model',_ascii_piper_path(model,executable.parent),'--config',_ascii_piper_path(config_path,executable.parent),'--espeak_data','espeak-ng-data','--json-input','--length_scale',length_scale,'--quiet']
                proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0,cwd=executable.parent)
                responses=queue.Queue()
                def reader():
                    for line in proc.stdout:responses.put(line.decode('utf-8',errors='replace').strip())
                    responses.put(None)
                threading.Thread(target=reader,daemon=True).start()
                server=dict(proc=proc,responses=responses,last=time.monotonic(),signature=signature)
                self.servers[accent]=server;self.processes.add(proc)
            server['last']=time.monotonic();proc=server['proc']
            try:
                output_dir=_ascii_piper_path(temporary_dir,executable.parent)
                request=dict(text=word+'.' if upgraded else word,output_file=os.path.join(output_dir,temporary.name))
                proc.stdin.write((json.dumps(request)+'\n').encode('utf-8'));proc.stdin.flush()
                answer=server['responses'].get(timeout=30)
                if answer is None or Path(answer.replace('\\','/')).name!=temporary.name or not self.valid_wave(temporary):raise RuntimeError('Offline synthesis failed')
                target.write_bytes(temporary.read_bytes());temporary.unlink();server['last']=time.monotonic();return target
            except Exception:
                if proc.poll() is None:proc.kill()
                self.servers.pop(accent,None);self.processes.discard(proc);raise
    def render_system_voice(self,word,accent):
        from mac_platform import choose_voice
        catalog=subprocess.check_output(['/usr/bin/say','-v','?'],text=True,timeout=10)
        voice=choose_voice(catalog,accent)
        if not voice:raise SpeechUnavailable('系统缺少'+('英式' if accent==1 else '美式')+'语音，请在 macOS“辅助功能→朗读内容→系统声音”中下载对应口音')
        self.cache.mkdir(parents=True,exist_ok=True)
        key='macOS|'+platform.mac_ver()[0]+'|'+voice+'|'+str(accent)+'|'+word.lower()
        target=self.cache/(hashlib.sha256(key.encode()).hexdigest()+'.wav')
        if target.exists() and self.valid_wave(target):return target
        temporary=target.with_suffix('.aiff')
        with self.lock:
            if self.closed.is_set():raise RuntimeError('Speech engine closed')
            proc=subprocess.Popen(['/usr/bin/say','-v',voice,'-o',str(temporary)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            self.processes.add(proc)
            try:
                proc.communicate(word.encode('utf-8'),timeout=30)
                if proc.returncode:raise SpeechUnavailable('系统语音合成失败，请检查所选口音是否已下载')
                subprocess.run(['/usr/bin/afconvert','-f','WAVE','-d','LEI16',str(temporary),str(target)],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15)
                if not self.valid_wave(target):raise SpeechUnavailable('系统语音未生成有效音频')
                return target
            finally:
                if proc.poll() is None:proc.kill()
                self.processes.discard(proc)
                if temporary.exists():temporary.unlink()
    @staticmethod
    def valid_wave(path):
        try:
            with wave.open(str(path),'rb') as wav:return wav.getnframes()>wav.getframerate()*.1 and wav.getsampwidth()==2
        except (OSError,EOFError,wave.Error):return False
    def close(self):
        self.closed.set()
        # Do not wait for a synthesis holding the request lock during shutdown.
        processes=self.processes.copy()
        for proc in processes:
            if proc.poll() is None:
                try:proc.terminate()
                except OSError:pass
    def reap(self):
        while not self.closed.wait(5):
            with self.lock:
                for accent,server in list(self.servers.items()):
                    if time.monotonic()-server['last']>90:
                        proc=server['proc']
                        if proc.poll() is None:proc.terminate()
                        self.processes.discard(proc);self.servers.pop(accent,None)
