import re
from functools import lru_cache
from opencc import OpenCC

_converter=OpenCC('t2s')

@lru_cache(maxsize=4096)
def simplified(text):
    text=_converter.convert(text)
    text=re.sub(r'(?m)^\s*=+\s*翻译\s*=+\s*\n(?:\s*翻译\s*\n)?','',text)
    # Source dictionaries sometimes embed script labels and both spellings.
    text=re.sub(r'(?m)^\s*[*•]?\s*(?:正体中文|繁体中文|简体中文)\s*[：:]\s*','',text)
    lines=[]
    for line in text.split('\n'):
        if re.search(r'[\u3400-\u9fff]',line) and '/' in line:
            parts=line.split('/')
            if len(parts)>1 and all(p.strip()==parts[0].strip() for p in parts):line=parts[0].strip()
        if lines and line.strip()==lines[-1].strip() and re.search(r'[\u3400-\u9fff]',line):continue
        lines.append(line)
    return '\n'.join(lines)
