"""Optional LibreTranslate client; no third-party dictionary scraping."""
import json
import urllib.request
from urllib.parse import urlsplit
from chinese_text import simplified

class TranslationUnavailable(Exception): pass

def translate(text, endpoint='http://127.0.0.1:5000'):
    parsed=urlsplit(endpoint)
    if parsed.scheme not in ('http','https') or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise TranslationUnavailable('翻译服务地址无效')
    if parsed.scheme=='http' and parsed.hostname not in ('localhost','127.0.0.1','::1'):
        raise TranslationUnavailable('远程服务必须使用 HTTPS')
    if not isinstance(text,str) or not 1<=len(text)<=400:
        raise TranslationUnavailable('短语长度超出限制')
    body=json.dumps(dict(q=text,source='en',target='zh',format='text')).encode('utf-8')
    request=urllib.request.Request(endpoint.rstrip('/')+'/translate',data=body,headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=12) as response:
            if urlsplit(response.url).netloc!=parsed.netloc:
                raise TranslationUnavailable('翻译服务发生跨站跳转')
            data=json.loads(response.read(65537))
        value=data.get('translatedText')
        if not isinstance(value,str) or not value.strip() or len(value)>6000:
            raise ValueError('invalid response')
        return simplified(value.strip())
    except TranslationUnavailable: raise
    except Exception as error:
        raise TranslationUnavailable('本地翻译服务未就绪，请在设置中查看部署指南') from error

def accept_result(current_serial,current_word,payload):
    return payload[0]==current_serial and payload[1]==current_word
