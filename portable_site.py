"""Portable, verified weekly archives and static sites for Pages or self-hosting.

Git tracks corrections to per-week JSON; SQLite is rebuilt on each hosted run.
Only public flyer metadata is exported, never a machine's absolute paths.
"""
from contextlib import closing, contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import tempfile
from urllib.parse import urlsplit

from dashboard import render_dashboard
from deal_history import record_week, _validate
from json_output import write_json
from reporting import dashboard_data

MAX_ARCHIVE_BYTES = 800 * 1024 * 1024
MAX_SITE_BYTES = 25 * 1024 * 1024
SOURCE_FIELDS = ('schema_version', 'start_date', 'end_date', 'title', 'source_page',
                 'fetched_at', 'checked_at', 'content_id', 'issues', 'import_note')
OBJECT_FIELDS = ('sha256', 'url', 'download_url', 'page_count', 'text_page_count',
                 'dates_verified', 'product_count', 'size_bytes')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def safe_source(source):
    result = {key: copy.deepcopy(source[key]) for key in SOURCE_FIELDS if key in source}
    for kind in ('pdf', 'api'):
        if kind in source:
            result[kind] = {key: source[kind][key] for key in OBJECT_FIELDS if key in source[kind]}
    return result


def object_path(entry, suffix):
    sha = entry.get('sha256', '')
    if not re.fullmatch('[0-9a-f]{64}', sha):
        raise ValueError('Source object requires a lowercase SHA-256')
    return f'objects/{sha}.{suffix}'


def verified_bytes(root, relative, sha):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root):
        raise ValueError('Source path must stay inside its archive')
    raw = path.read_bytes()
    if digest(raw) != sha:
        raise ValueError(f'Source checksum mismatch: {Path(relative).name}')
    return raw


@contextmanager
def directory_build(destination, marker):
    """Publish a complete owned directory, restoring the previous one on failure."""
    destination = Path(destination).absolute()
    if destination.is_symlink() or (destination.exists() and not (destination / marker).is_file()):
        raise ValueError(f'Refusing to replace an unrelated directory: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.basket-build-', dir=destination.parent) as temporary:
        stage = Path(temporary) / 'new'
        stage.mkdir()
        yield stage
        backup = Path(temporary) / 'previous'
        if destination.exists():
            os.replace(destination, backup)
        try:
            os.replace(stage, destination)
        except BaseException:
            if backup.exists():
                os.replace(backup, destination)
            raise


def export_archive(history_db, destination):
    """Save active weekly exports and their verified PDF/API sources.

    Previous revisions remain in the data branch's Git history. No artifacts or
    caches are needed to restore observations on the next scheduled run.
    """
    db = Path(history_db).resolve()
    if db.is_relative_to(Path(destination).resolve()):
        raise ValueError('Archive destination must not contain its database')
    with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True)) as connection:
        rows = connection.execute('SELECT r.payload_json FROM history_active a '
                                  'JOIN history_runs r ON r.run_id=a.run_id '
                                  'ORDER BY r.start_date,r.end_date').fetchall()
    if not rows:
        raise ValueError('Cannot publish an empty history archive')
    with directory_build(destination, 'archive.json') as stage:
        entries = []
        for (raw,) in rows:
            payload = json.loads(raw)
            start, end = _validate(payload)
            source = payload['source']
            portable = {'pages': payload['pages'], 'source': safe_source(source)}
            if 'extraction' in payload:
                portable['extraction'] = payload['extraction']
            for kind, suffix in (('pdf', 'pdf'), ('api', 'json')):
                entry = source.get(kind)
                if not entry:
                    continue
                path = object_path(entry, suffix)
                content = verified_bytes(source.get('archive_root') or '.', entry['path'], entry['sha256'])
                target = stage / path
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(content)
                portable['source'][kind]['path'] = path
            path = f'weeks/{start}_{end}.json'
            write_json(stage / path, portable)
            entries.append({'path': path, 'sha256': digest((stage / path).read_bytes())})
        write_json(stage / 'archive.json', {'schema_version': 1, 'weeks': entries})
        if sum(p.stat().st_size for p in stage.rglob('*') if p.is_file()) > MAX_ARCHIVE_BYTES:
            raise ValueError('Archive exceeds the 800 MiB storage budget; retain the previous publication')
    return len(entries)


def restore_archive(archive, history_db):
    """Verify the whole archive before atomically replacing a derived database."""
    root, destination = Path(archive).resolve(), Path(history_db).absolute()
    if destination.resolve().is_relative_to(root):
        raise ValueError('Derived database must be outside the source archive')
    index = json.loads((root / 'archive.json').read_text())
    if index.get('schema_version') != 1 or not isinstance(index.get('weeks'), list) or not index['weeks']:
        raise ValueError('Unsupported or empty archive index')
    payloads, seen = [], set()
    for entry in index['weeks']:
        payload = json.loads(verified_bytes(root, entry['path'], entry['sha256']))
        start, end = _validate(payload)
        expected = f'weeks/{start}_{end}.json'
        if entry['path'] != expected or expected in seen:
            raise ValueError('Duplicate week or mismatched archive filename')
        seen.add(expected)
        source = payload['source']
        for kind, suffix in (('pdf', 'pdf'), ('api', 'json')):
            if kind in source:
                obj = source[kind]
                if obj.get('path') != object_path(obj, suffix):
                    raise ValueError('Archive object path is not canonical')
                verified_bytes(root, obj['path'], obj['sha256'])
        source['archive_root'] = str(root)
        payloads.append(payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.basket-db-', dir=destination.parent) as temporary:
        db = Path(temporary) / 'history.sqlite3'
        for payload in payloads:
            record_week(db, payload)
        os.replace(db, destination)
    return len(payloads)


def build_site(history_db, destination, source_base_url=None):
    """Build index.html with portable sources; hosted PDFs stay in the data branch."""
    if Path(history_db).resolve().is_relative_to(Path(destination).resolve()):
        raise ValueError('Site destination must not contain its database')
    if source_base_url:
        parsed = urlsplit(source_base_url)
        if parsed.scheme != 'https' or not parsed.netloc or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('Source base URL must be an HTTPS directory URL')
    with directory_build(destination, '.basket-site') as stage:
        data = dashboard_data(history_db, stage / 'index.html')
        if not data['weeks']:
            raise ValueError('Cannot publish an empty site')
        for week in data['weeks']:
            original = week['source']
            source = safe_source(original)
            pdf = original['pdf']
            path = object_path(pdf, 'pdf')
            raw = verified_bytes(original.get('archive_root') or '.', pdf['path'], pdf['sha256'])
            if source_base_url:
                source['pdf_href'] = source_base_url.rstrip('/') + '/' + path
            else:
                target = stage / path
                target.parent.mkdir(exist_ok=True)
                target.write_bytes(raw)
                source['pdf_href'] = path
            week['source'] = source
        render_dashboard(data, stage / 'index.html')
        (stage / '.nojekyll').touch()
        (stage / '.basket-site').write_text('Market Basket portable website v1\n')
        size = sum(p.stat().st_size for p in stage.rglob('*') if p.is_file())
        if source_base_url and size > MAX_SITE_BYTES:
            raise ValueError('Website exceeds the 25 MiB deployment budget')
    return {'weeks': data['week_count'], 'bytes': size}
