"""Accent-specific Commons recordings with per-file licence and attribution.

No dictionary vendor endpoints, API keys, or recordings ship with the app.
Only exact word/accent filenames with a verified reusable licence are accepted.
"""
import hashlib
import html
import json
import os
import re
import ssl
import time
import urllib.parse
import urllib.request
import wave
from pathlib import Path

API = 'https://commons.wikimedia.org/w/api.php'
AGENT = 'WoerTranslator/0.3.3 (https://github.com/blueaaa333/woer-translator)'
MAX_AUDIO = 2 * 1024 * 1024


def plain(value):
    return html.unescape(re.sub(r'<[^>]*>', '', str(value))).strip()


def licence(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in ('http', 'https') or parsed.netloc != 'creativecommons.org':
        return None
    match = re.fullmatch(r'/licenses/(by|by-sa)/(1\.0|2\.0|2\.5|3\.0|4\.0)/(?:([a-z]{2})/)?(?:deed\.[a-z_-]+)?', parsed.path)
    if match:
        kind, version, country = match.groups()
        return ('CC ' + kind.upper() + ' ' + version + (' ' + country if country else ''),
                'https://creativecommons.org/licenses/' + kind + '/' + version + '/' + (country + '/' if country else ''))
    if parsed.path in ('/publicdomain/zero/1.0/', '/publicdomain/zero/1.0/deed.en'):
        return ('CC0 1.0', 'https://creativecommons.org/publicdomain/zero/1.0/')
    return None


def select_recording(page, word, accent):
    region = '(?:uk|gb)' if accent == 1 else 'us'
    title = page.get('title', '')
    if not re.fullmatch(r'File:En-' + region + '-' + re.escape(word) + r'\.(ogg|oga|wav|mp3)', title, re.I):
        return None
    for info in page.get('imageinfo', []):
        meta = info.get('extmetadata', {})
        value = lambda key: plain(meta.get(key, {}).get('value', ''))
        permit = licence(value('LicenseUrl'))
        author = value('Artist')
        url = urllib.parse.urlsplit(info.get('url', ''))
        source = urllib.parse.urlsplit(info.get('descriptionurl', ''))
        if (not permit or not author or value('Restrictions') or
                url.scheme != 'https' or url.netloc != 'upload.wikimedia.org' or
                not url.path.startswith('/wikipedia/commons/') or
                source.scheme != 'https' or source.netloc != 'commons.wikimedia.org' or
                not source.path.startswith('/wiki/File:') or
                info.get('mime') not in ('application/ogg', 'audio/ogg', 'audio/wav', 'audio/x-wav', 'audio/mpeg') or
                not 0 < info.get('size', 0) <= MAX_AUDIO or
                not 0.1 < info.get('duration', 0) <= 15 or
                not re.fullmatch('[a-f0-9]{40}', info.get('sha1', ''))):
            continue
        return dict(word=word, accent=accent, title=title, author=author,
                    licence=permit[0], licence_url=permit[1], source=info['descriptionurl'],
                    url=urllib.parse.urlunsplit(url._replace(query='', fragment='')),
                    sha1=info['sha1'], size=info['size'], kind='recording',
                    changes='原录音另存为 PCM WAV，仅做格式转换；未变速、变调或裁剪。音频沿用原许可。')
    return None


def download(url, limit):
    # Keep TLS verification enabled in frozen apps as well as source launches.
    import certifi
    context = ssl.create_default_context()
    context.load_verify_locations(certifi.where())
    request = urllib.request.Request(url, headers={'User-Agent': AGENT})
    with urllib.request.urlopen(request, timeout=4, context=context) as response:
        final = urllib.parse.urlsplit(response.geturl())
        if final.scheme != 'https' or final.netloc not in ('commons.wikimedia.org', 'upload.wikimedia.org'):
            raise ValueError('Unexpected recording redirect')
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError('Recording response too large')
    return data


class Recordings:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.catalog = {}
        self.retry_after = 0
        self.last = None
        self.last_error = None

    def paths(self, word, accent):
        key = hashlib.sha256(f'{accent}|{word}'.encode()).hexdigest()
        return self.folder / key

    def read_catalog(self, word):
        path=self.folder/('lookup-'+hashlib.sha256(word.encode()).hexdigest()+'.json')
        try:
            saved=json.loads(path.read_text(encoding='utf-8'))
            if saved['word']==word and 0<=time.time()-saved['checked_at']<86400 and isinstance(saved['pages'],list):
                return saved['pages']
        except (OSError,ValueError,KeyError,TypeError):pass
        return None

    def save_catalog(self, word, pages):
        path=self.folder/('lookup-'+hashlib.sha256(word.encode()).hexdigest()+'.json')
        try:
            self.folder.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix('.part')
            temporary.write_text(json.dumps(dict(word=word,checked_at=time.time(),pages=pages)),encoding='utf-8')
            os.replace(temporary,path)
        except OSError:pass

    def cached(self, word, accent):
        stem = self.paths(word, accent)
        try:
            metadata = json.loads(stem.with_suffix('.json').read_text(encoding='utf-8'))
            target = stem.with_suffix('.wav')
            if (metadata['word'] != word or metadata['accent'] != accent or
                    not licence(metadata['licence_url']) or not metadata.get('author') or
                    hashlib.sha256(target.read_bytes()).hexdigest() != metadata['wav_sha256']):
                return None
            with wave.open(str(target), 'rb') as stream:
                if stream.getsampwidth() != 2 or not 0.1 < stream.getnframes()/stream.getframerate() <= 15:
                    return None
            if not self.attribution_path().is_file():
                self.write_attributions()
            self.last = metadata
            return target
        except (OSError, ValueError, TypeError, KeyError, EOFError, wave.Error):
            return None

    def get(self, word, accent):
        self.last = None
        self.last_error = None
        word = word.lower().strip()
        if accent not in (1, 2) or not re.fullmatch(r"[a-z][a-z '\-]{0,70}", word):
            return None
        hit = self.cached(word, accent)
        if hit:
            return hit
        if time.monotonic() < self.retry_after:
            return None
        try:
            if word not in self.catalog:
                saved=self.read_catalog(word)
                if saved is not None:self.catalog[word]=saved
            if word not in self.catalog:
                titles = [f'File:En-{region}-{word}.{extension}'
                          for region in ('uk', 'gb', 'us') for extension in ('ogg', 'oga', 'wav', 'mp3')]
                params = dict(action='query', format='json', formatversion=2,
                              prop='imageinfo', titles='|'.join(titles),
                              iiprop='url|extmetadata|sha1|size|mime',
                              iiextmetadatafilter='Artist|LicenseShortName|LicenseUrl|Restrictions')
                response = json.loads(download(API + '?' + urllib.parse.urlencode(params), MAX_AUDIO))
                pages=response.get('query',{}).get('pages')
                if not isinstance(pages,list):raise ValueError('Invalid recording catalogue')
                self.catalog[word]=pages
                self.save_catalog(word,pages)
            candidates = [select_recording(page, word, accent) for page in self.catalog[word]]
            metadata = next((candidate for candidate in candidates if candidate), None)
            if metadata is None:
                return None
            original = download(metadata['url'], MAX_AUDIO)
            if len(original) != metadata['size'] or hashlib.sha1(original).hexdigest() != metadata['sha1']:
                raise ValueError('Recording checksum mismatch')
            import miniaudio
            decoded = miniaudio.decode(original, output_format=miniaudio.SampleFormat.SIGNED16,
                                       nchannels=1, sample_rate=44100)
            if not 0.1 < len(decoded.samples)/44100 <= 15:
                raise ValueError('Invalid recording duration')
            self.folder.mkdir(parents=True, exist_ok=True)
            stem = self.paths(word, accent)
            temporary = stem.with_suffix('.part')
            try:
                with wave.open(str(temporary), 'wb') as output:
                    output.setnchannels(1);output.setsampwidth(2);output.setframerate(44100)
                    output.writeframes(decoded.samples.tobytes())
                os.replace(temporary, stem.with_suffix('.wav'))
            finally:
                temporary.unlink(missing_ok=True)
            # Keep the unmodified original and full per-file credit beside the WAV.
            suffix = Path(metadata['title']).suffix
            stem.with_suffix(suffix).write_bytes(original)
            metadata['original_file'] = stem.name + suffix
            metadata['wav_sha256'] = hashlib.sha256(stem.with_suffix('.wav').read_bytes()).hexdigest()
            stem.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
            self.write_attributions()
            self.last = metadata
            return stem.with_suffix('.wav')
        except Exception as error:
            # Network, decoding, and permission failures use the existing local
            # voices; never make the Tk UI or subsequent requests wait on retry.
            self.retry_after = time.monotonic() + 60
            self.last_error = type(error).__name__
            return None

    def attribution_path(self):
        return self.folder / 'ATTRIBUTION.html'

    def write_attributions(self):
        cards = []
        esc = html.escape
        for path in sorted(self.folder.glob('*.json')):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if not licence(data['licence_url']):
                    continue
                cards.append('<section><h2>' + esc(data['word']) + (' · 英式' if data['accent'] == 1 else ' · 美式') +
                    '</h2><p>录音作者：' + esc(data['author']) + '</p><p><a href="' + esc(data['source'], quote=True) +
                    '">原始文件与说明</a> · <a href="' + esc(data['licence_url'], quote=True) + '">' + esc(data['licence']) +
                    '</a></p><p>' + esc(data['changes']) + '</p></section>')
            except (OSError, ValueError, KeyError, TypeError):
                continue
        self.folder.mkdir(parents=True, exist_ok=True)
        self.attribution_path().write_text('<!doctype html><meta charset="utf-8"><title>沃尔翻译官 · 发音来源与许可</title>'
            '<style>body{font:16px system-ui;max-width:780px;margin:40px auto;padding:20px;color:#23475b}section{border-top:1px solid #dce5ec;padding:12px 0}a{color:#167ca4}</style>'
            '<h1>真人发音来源与许可</h1><p>录音来自 Wikimedia Commons 的独立贡献者。本项目与录音作者及 Wikimedia 没有官方合作或背书关系。'
            '每条录音保留独立许可，不适用软件的 MIT 许可。重新分享录音时请携带对应署名、来源、许可和改动说明。</p>' +
            ''.join(cards), encoding='utf-8')
