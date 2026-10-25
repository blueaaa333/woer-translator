"""Persistent user choices, separate from one-off lookup pronunciation."""
import json
import os
import tempfile
from pathlib import Path


def normalize(data):
    data = dict(data) if isinstance(data, dict) else {}
    accent = data.get('accent', 0)
    if type(accent) is not int or accent not in (0, 1, 2):
        accent = 0
    preferred = data.get('preferred_accent', accent or 2)
    if type(preferred) is not int or preferred not in (1, 2):
        preferred = accent or 2
    enabled = data.get('auto_read', accent != 0)
    if not isinstance(enabled, bool):
        enabled = accent != 0
    data.update(auto_read=enabled, preferred_accent=preferred,
                accent=preferred if enabled else 0)
    return data


class PreferenceStore:
    def __init__(self, path, read_only=False):
        self.path = Path(path)
        self.read_only = read_only

    def read(self):
        try:
            return normalize(json.loads(self.path.read_text(encoding='utf-8')))
        except (OSError, ValueError):
            return normalize({})

    def write(self, data):
        data = normalize(data)
        if self.read_only:
            return data
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            # Replace only after the complete new file is flushed. An interrupted
            # write must not truncate the last successfully saved user choices.
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                    dir=self.path.parent, prefix='.preferences-', suffix='.tmp',
                    delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            return data
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
