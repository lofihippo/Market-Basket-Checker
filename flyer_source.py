"""Discover and archive the official weekly PDF without replacing good state.

The website's JSON endpoint supplies discovery metadata. Offers still come
from PDF extraction; raw API products are archived for later comparison.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
from http.client import HTTPException
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.error import URLError
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

import pymupdf

from json_output import write_json

SOURCE_PAGE = "https://www.shopmarketbasket.com/weekly-flyer/"
API_URL = "https://www.shopmarketbasket.com/wp-json/mb/v1/weekly-flyer"
JSON_LIMIT = 5_000_000
PDF_LIMIT = 50_000_000
_HOSTS = {"www.shopmarketbasket.com", "shopmarketbasket.com"}
_MONTHS = {name: index for index, name in enumerate(
    "January February March April May June July August September October November December".split(), 1)}


class SourceError(ValueError):
    """The current flyer could not be safely identified or acquired."""


@dataclass(frozen=True)
class Download:
    body: bytes
    url: str
    content_type: str


def _checked_url(value):
    if not isinstance(value, str) or not value.strip():
        raise SourceError("Missing flyer URL")
    url = urljoin(SOURCE_PAGE, value.strip())
    parts = urlsplit(url)
    try:
        allowed = (parts.scheme == 'https' and parts.hostname in _HOSTS
                   and parts.port in (None, 443) and not parts.username and not parts.password)
    except ValueError:
        allowed = False
    if not allowed:
        raise SourceError("Flyer URL must use HTTPS on the official Market Basket host")
    return url


def resolve_pdf_url(value):
    """Unwrap the website's embedded-pdf link; also accept direct PDF links."""
    url = _checked_url(value)
    parts = urlsplit(url)
    if parts.path.rstrip('/') == '/embedded-pdf':
        values = parse_qs(parts.query).get('id', [])
        if len(values) != 1 or not values[0]:
            raise SourceError("The embedded PDF link has no unique download id")
        url = _checked_url(values[0])
        if urlsplit(url).path.rstrip('/') == '/embedded-pdf':
            raise SourceError("Nested embedded PDF links are not supported")
    return url


def _source_date(value):
    if not isinstance(value, str):
        raise SourceError("Flyer dates must be strings")
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            return date.fromisoformat(value)
        match = re.fullmatch(r'([A-Za-z]+) (\d{1,2}), (\d{4})', value.strip())
        if not match:
            raise ValueError()
        return date(int(match[3]), _MONTHS[match[1]], int(match[2]))
    except (ValueError, KeyError) as exc:
        raise SourceError(f"Invalid flyer date: {value!r}") from exc


def parse_metadata(payload, today):
    if not isinstance(payload, dict) or not isinstance(payload.get('dates'), dict):
        raise SourceError("Flyer metadata must contain a dates object")
    if type(payload.get('active')) is not bool:
        raise SourceError("Flyer active flag must be a boolean")
    for key in ('products', 'departments'):
        if (not isinstance(payload.get(key), list)
                or not all(isinstance(item, dict) for item in payload[key])):
            raise SourceError(f"Flyer {key} must be an array of objects")
    start = _source_date(payload['dates'].get('start_date'))
    end = _source_date(payload['dates'].get('end_date'))
    if start > end:
        raise SourceError("Flyer end date precedes its start date")
    freshness = 'upcoming' if today < start else 'expired' if today > end else 'current'
    if not payload['active']:
        freshness = 'inactive'
    title = payload.get('title')
    if title is not None and not isinstance(title, str):
        raise SourceError("Flyer title must be text")
    return {'title': title, 'start_date': start.isoformat(), 'end_date': end.isoformat(),
            'active': payload['active'], 'freshness': freshness,
            'pdf_url': resolve_pdf_url(payload.get('pdf'))}


class _OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, _checked_url(newurl))


def download(url, *, limit, timeout):
    """Bound requests and redirects; never disable TLS verification."""
    request = Request(_checked_url(url), headers={
        'User-Agent': 'MarketBasketWeeklyChecker/0.1', 'Accept-Encoding': 'identity'})
    try:
        with build_opener(_OfficialRedirects()).open(request, timeout=timeout) as response:
            body = response.read(limit + 1)
            if len(body) > limit:
                raise SourceError(f"Download exceeds {limit} bytes")
            return Download(body, _checked_url(response.geturl()),
                            response.headers.get_content_type())
    except (URLError, OSError, HTTPException) as exc:
        raise SourceError(f"Could not download {url}: {exc}") from exc


def _pdf_info(body, metadata):
    if not body.startswith(b'%PDF-') or b'%%EOF' not in body[-1024:]:
        raise SourceError("Download is not a complete PDF")
    try:
        with pymupdf.open(stream=body, filetype='pdf') as doc:
            if not doc.is_pdf or doc.needs_pass or doc.is_repaired or not 1 <= len(doc) <= 100:
                raise SourceError("PDF is empty, encrypted, damaged, or has too many pages")
            texts = [page.get_text() for page in doc]
            # The current flyer prints numeric dates in its page footers.
            # Reject recognized conflicts, and expose an unrecognized format.
            ranges = set()
            for text in texts:
                for match in re.finditer(
                    r'Effective\s*(\d{1,2}-\d{1,2}-\d{2,4})\s*(?:to|thru)\s*'
                    r'(\d{1,2}-\d{1,2}-\d{2,4})', text, re.I):
                    values = []
                    for value in match.groups():
                        month, day, year = map(int, value.split('-'))
                        values.append(date(2000 + year if year < 100 else year, month, day).isoformat())
                    ranges.add(tuple(values))
            if ranges and ranges != {(metadata['start_date'], metadata['end_date'])}:
                raise SourceError("PDF effective dates disagree with the official metadata")
            return {'page_count': len(doc), 'text_page_count': sum(bool(t.strip()) for t in texts),
                    'dates_verified': bool(ranges)}
    except SourceError:
        raise
    except Exception as exc:
        raise SourceError(f"Could not validate the PDF: {exc}") from exc


def _digest(body):
    return hashlib.sha256(body).hexdigest()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2,
                       allow_nan=False) + '\n').encode('utf-8')


def _content_id(payload, pdf_hash):
    """Ignore the observed cache-busting timestamp, retaining other metadata.

    The raw API response and request URL are still archived without changes.
    Content change detection must not treat a fresh tmstv as a new sale.
    """
    metadata = dict(payload)
    url = urlsplit(resolve_pdf_url(payload['pdf']))
    query = [(key, value) for key, value in parse_qsl(url.query, keep_blank_values=True)
             if key != 'tmstv']
    metadata['pdf'] = urlunsplit(url._replace(query=urlencode(query), fragment=''))
    return _digest(_json_bytes({'metadata': metadata, 'pdf_sha256': pdf_hash}))


def _write_archive(path, body):
    """Write a complete archive object, reusing identical existing content."""
    path = Path(path)
    if path.exists():
        if path.read_bytes() != body:
            raise SourceError(f"Archive content mismatch: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.download-', delete=False) as out:
            temporary = Path(out.name)
            out.write(body)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fetch_current(source_dir, *, today=None, timeout=30, fetcher=None):
    """Archive a verified current flyer, publishing current.json last.

    Failures never fall back silently to stale data. ``changed`` describes the
    source content, including metadata except the URL cache timestamp, and is returned to callers
    without being stored in the manifest. Tests inject a fetcher and date.
    """
    if not math.isfinite(timeout) or timeout <= 0:
        raise SourceError("Timeout must be finite and positive")
    source_dir = Path(source_dir)
    today = today or datetime.now(ZoneInfo('America/New_York')).date()
    fetcher = fetcher or download
    try:
        api = fetcher(API_URL, limit=JSON_LIMIT, timeout=timeout)
        if len(api.body) > JSON_LIMIT:
            raise SourceError("Flyer metadata exceeds its size limit")
        _checked_url(api.url)
        try:
            payload = json.loads(api.body)
        except (ValueError, UnicodeError) as exc:
            raise SourceError("Official endpoint did not return valid JSON") from exc
        metadata = parse_metadata(payload, today)
        if metadata['freshness'] != 'current':
            raise SourceError(f"Official flyer is {metadata['freshness']} "
                              f"({metadata['start_date']} through {metadata['end_date']}); "
                              "previous files were retained")
        pdf = fetcher(metadata['pdf_url'], limit=PDF_LIMIT, timeout=timeout)
        if len(pdf.body) > PDF_LIMIT:
            raise SourceError("Flyer PDF exceeds its size limit")
        _checked_url(pdf.url)
        info = _pdf_info(pdf.body, metadata)
        api_hash, pdf_hash = _digest(api.body), _digest(pdf.body)
        api_path, pdf_path = f'objects/{api_hash}.json', f'objects/{pdf_hash}.pdf'
        record = {'schema_version': 1, 'source_page': SOURCE_PAGE,
                  'content_id': _content_id(payload, pdf_hash),
                  **{key: value for key, value in metadata.items() if key != 'pdf_url'},
                  'api': {'path': api_path, 'url': api.url, 'sha256': api_hash,
                          'size_bytes': len(api.body), 'product_count': len(payload.get('products', []))},
                  'pdf': {'path': pdf_path, 'url': metadata['pdf_url'], 'download_url': pdf.url,
                          'sha256': pdf_hash, 'size_bytes': len(pdf.body), **info},
                  'issues': [] if info['dates_verified'] else ['pdf_dates_unverified']}
        snapshot_id = _digest(_json_bytes(record))
        snapshot_path = f'snapshots/{snapshot_id}.json'
        checked_at = datetime.now(timezone.utc).isoformat()
        if (source_dir / snapshot_path).exists():
            archived = json.loads((source_dir / snapshot_path).read_text(encoding='utf-8'))
            if not isinstance(archived, dict):
                raise SourceError("Stored snapshot metadata must be an object")
            if {key: value for key, value in archived.items() if key != 'fetched_at'} != record:
                raise SourceError("Stored snapshot metadata is inconsistent")
            record = archived
        else:
            record['fetched_at'] = checked_at
        current_path = source_dir / 'current.json'
        previous = json.loads(current_path.read_text(encoding='utf-8')) if current_path.exists() else {}
        if not isinstance(previous, dict):
            raise SourceError("Stored current manifest must be an object")
        _write_archive(source_dir / api_path, api.body)
        _write_archive(source_dir / pdf_path, pdf.body)
        _write_archive(source_dir / snapshot_path, _json_bytes(record))
        manifest = {**record, 'snapshot_id': snapshot_id, 'snapshot_path': snapshot_path,
                    'checked_at': checked_at}
        write_json(current_path, manifest)
        return {**manifest, 'changed': previous.get('content_id') != record['content_id']}
    except SourceError:
        raise
    except (OSError, ValueError, TypeError, URLError) as exc:
        raise SourceError(f"Flyer refresh failed; previous manifest retained: {exc}") from exc
