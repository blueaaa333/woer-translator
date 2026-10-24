import atexit,hashlib,json,os,subprocess,threading,wave,queue,time
from pathlib import Path
from lexicon import normalize_query,valid_query

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

class SpeechEngine:
    def __init__(self,base,cache):
        self.root=Path(base)/'speech';self.cache=Path(cache)
        self.processes=set();self.servers={};self.lock=threading.RLock();self.closed=threading.Event()
        atexit.register(self.close);threading.Thread(target=self.reap,daemon=True).start()
    def render(self,word,accent):
        if self.closed.is_set():raise RuntimeError('Speech engine closed')
        word=normalize_query(word)
        if accent not in (1,2) or not valid_query(word):raise ValueError('Invalid speech request')
        folder=self.root/'voices'/('uk' if accent==1 else 'us')
        model=folder/'voice.onnx';config_path=folder/'voice.onnx.json'
        config=json.loads(config_path.read_text(encoding='utf-8'))
        expected='en_GB' if accent==1 else 'en_US'
        if config.get('language',{}).get('code')!=expected:raise ValueError('Voice accent does not match button')
        executable=next((p for p in [self.root/'runtime'/'piper'/'piper.exe',self.root/'runtime'/'piper.exe'] if p.exists()),None)
        if executable is None:raise FileNotFoundError('Offline voice runtime missing')
        self.cache.mkdir(parents=True,exist_ok=True)
        key=f'{expected}|{config.get("dataset")}|{model.stat().st_size}|{model.stat().st_mtime_ns}|{word.lower()}'
        target=self.cache/(hashlib.sha256(key.encode()).hexdigest()+'.wav')
        if target.exists() and self.valid_wave(target):return target
        # This upstream Windows runtime uses narrow file paths. Pass ASCII-only
        # paths relative to its working directory, including under Chinese names.
        temporary_dir=executable.parent/'_speech_tmp';temporary_dir.mkdir(exist_ok=True)
        temporary=temporary_dir/(target.stem+'.wav')
        with self.lock:
            if self.closed.is_set():raise RuntimeError('Speech engine closed')
            server=self.servers.get(accent)
            if server is None or server['proc'].poll() is not None:
                command=[str(executable),'--model',os.path.relpath(model,executable.parent),'--config',os.path.relpath(config_path,executable.parent),'--espeak_data','espeak-ng-data','--json-input','--length_scale','1.05','--quiet']
                proc=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,creationflags=0x08000000 if os.name=='nt' else 0,cwd=executable.parent)
                responses=queue.Queue()
                def reader():
                    for line in proc.stdout:responses.put(line.decode('utf-8',errors='replace').strip())
                    responses.put(None)
                threading.Thread(target=reader,daemon=True).start()
                server=dict(proc=proc,responses=responses,last=time.monotonic())
                self.servers[accent]=server;self.processes.add(proc)
            server['last']=time.monotonic();proc=server['proc']
            try:
                request=dict(text=word,output_file='_speech_tmp/'+temporary.name)
                proc.stdin.write((json.dumps(request)+'\n').encode('utf-8'));proc.stdin.flush()
                answer=server['responses'].get(timeout=30)
                if answer is None or Path(answer.replace('\\','/')).name!=temporary.name or not self.valid_wave(temporary):raise RuntimeError('Offline synthesis failed')
                target.write_bytes(temporary.read_bytes());temporary.unlink();server['last']=time.monotonic();return target
            except Exception:
                if proc.poll() is None:proc.kill()
                self.servers.pop(accent,None);self.processes.discard(proc);raise
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
