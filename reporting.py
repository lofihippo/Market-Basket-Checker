"""Connect verified exports, persistent observations, and the local dashboard."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import quote, urlsplit

from deal_categories import categorize_payload
from deal_history import build_history, record_week
from seasonality import seasonal_context


def read_catalog(payload):
    """Use only the exact archived API response belonging to this export."""
    source = payload.get('source', {})
    entry = source.get('api', {})
    if not entry.get('path') or not source.get('archive_root'):
        return []
    root = Path(source['archive_root']).resolve()
    path = (root / entry['path']).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return []
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != entry.get('sha256'):
        raise ValueError('Archived category source checksum does not match its manifest')
    catalog = json.loads(raw).get('products', [])
    if not isinstance(catalog, list) or not all(isinstance(item, dict) for item in catalog):
        raise ValueError('Archived category source has an invalid products array')
    return catalog


def enriched_export(payload):
    return categorize_payload(payload, read_catalog(payload))


def dashboard_data(history_db, html_path):
    data = build_history(history_db)
    output = Path(html_path).resolve()
    for week in data['weeks']:
        source = dict(week['source'])
        pdf = source.get('pdf', {})
        root = Path(source.get('archive_root') or '.').resolve()
        path = (root / pdf.get('path', '')).resolve()
        if pdf.get('path') and path.is_relative_to(root) and path.is_file():
            source['pdf_href'] = quote(os.path.relpath(path, output.parent), safe='/')
        else:
            remote = pdf.get('download_url') or pdf.get('url') or source.get('source_page')
            source['pdf_href'] = remote if remote and urlsplit(remote).scheme in ('http', 'https') else None
        week['source'] = source
    data['seasonality'] = seasonal_context()
    data['generated_at'] = datetime.now(timezone.utc).isoformat()
    data['notes'] = [
        'Counts describe extracted advertised offers, not store inventory, purchases, or percentage discounts.',
        'Categories come from the archived retailer departments when a name matches; other categories are labeled estimates.',
        'Image-only offers and logos can be missed. Review flags identify known issues, not a guarantee that every other offer is correct.',
        'Price history matches the same printed name, details, package, unit, and multibuy quantity. A derived per-item price does not guarantee single-item eligibility.',
        'Unobserved months are missing data. Recurring seasonal price patterns require comparable observations across seasons and repeated years.',
    ]
    return data


def render_history(history_db, html_path):
    from dashboard import render_dashboard
    data = dashboard_data(history_db, html_path)
    render_dashboard(data, html_path)
    return data


def record_and_render(payload, history_db, html_path):
    revision = record_week(history_db, enriched_export(payload))
    data = render_history(history_db, html_path)
    return {**revision, 'week_count': data['week_count'], 'html_path': str(html_path)}
