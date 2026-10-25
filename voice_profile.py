"""Select an installed voice without rewriting its training-time frontend."""
import hashlib
import json
from pathlib import Path


def voice_files(folder, accent):
    folder=Path(folder)
    preferred=folder/'dictionary-voice.onnx'
    preferred_config=folder/'dictionary-voice.onnx.json'
    upgraded=preferred.is_file() and preferred_config.is_file()
    model=preferred if upgraded else folder/'voice.onnx'
    config=preferred_config if upgraded else folder/'voice.onnx.json'
    if not model.is_file() or not config.is_file():raise FileNotFoundError('Voice pack is not installed')
    original=config.read_bytes();data=json.loads(original)
    if accent not in (1,2) or data.get('language',{}).get('code')!=('en_GB' if accent==1 else 'en_US'):
        raise ValueError('Voice accent does not match button')
    return model,config,data,upgraded,hashlib.sha256(original).hexdigest()
