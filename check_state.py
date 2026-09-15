"""Reuse a successful scheduled build only while all its inputs/outputs match."""
import hashlib
import json
from pathlib import Path
import platform

import pymupdf

from json_output import write_json


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def build_key(root, manifest, config):
    # Hash executable/report sources so parser or presentation fixes rebuild
    # unchanged flyers. README, tests, generated data and mtimes do not matter.
    root = Path(root)
    files = sorted([*root.glob('*.py'), root / 'scripts/check_weekly.py',
                    *root.glob('web/dashboard.*'), *root.glob('web/assets/*.png'),
                    root / 'requirements.txt'])
    code = {str(path.relative_to(root)): file_hash(path) for path in files}
    return {'content_id': manifest.get('content_id'), 'config': config,
            'code': code, 'python': platform.python_version(),
            'pymupdf': pymupdf.VersionBind}


def reusable(path, key, outputs):
    if not key.get('content_id'):
        return False
    try:
        state = json.loads(Path(path).read_text(encoding='utf-8'))
        return (isinstance(state, dict) and state.get('key') == key
                and state.get('outputs') == {str(p.resolve()): file_hash(p) for p in outputs})
    except (OSError, ValueError, TypeError):
        return False


def save_success(path, key, outputs):
    write_json(path, {'key': key,
                     'outputs': {str(p.resolve()): file_hash(p) for p in outputs}})
