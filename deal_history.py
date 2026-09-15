"""Keep immutable weekly extraction revisions and conservative price history.

The active revision contributes one observation per comparable offer per week.
History measures advertised prices, not regular prices or confirmed purchases.
No fuzzy matching or size conversions are used.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from contextlib import closing
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import unicodedata

from pricing import offer_terms


_SCHEMA = """
CREATE TABLE IF NOT EXISTS history_runs (
    run_id TEXT PRIMARY KEY,
    week_id TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS history_active (
    week_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES history_runs(run_id)
);
CREATE TRIGGER IF NOT EXISTS history_runs_no_update
BEFORE UPDATE ON history_runs BEGIN
    SELECT RAISE(ABORT, 'History revisions are immutable');
END;
CREATE TRIGGER IF NOT EXISTS history_runs_no_delete
BEFORE DELETE ON history_runs BEGIN
    SELECT RAISE(ABORT, 'History revisions are immutable');
END;
"""
_FETCH_FIELDS = {"fetched_at", "checked_at", "changed"}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _normalize(value):
    """Normalize typography and whitespace, retaining meaningful punctuation."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "“": '"',
                                       "”": '"', "–": "-", "—": "-"}))
    return re.sub(r"\s+", " ", text).strip().casefold()


def _identity_content(payload):
    result = dict(payload)
    source = payload["source"]
    if source.get("content_id"):
        # Acquisition's content_id already ignores cache-busting URLs. API
        # hashes, snapshot IDs and archive paths can change solely because the
        # retailer refreshed those links; they do not create a new price week.
        result["source"] = {key: source[key] for key in (
            "content_id", "start_date", "end_date", "title", "issues") if key in source}
        result["source"]["pdf"] = {key: source["pdf"][key] for key in (
            "sha256", "page_count", "text_page_count", "dates_verified") if key in source["pdf"]}
    else:
        result["source"] = {k: v for k, v in source.items() if k not in _FETCH_FIELDS}
    return result


def _validate(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("source"), dict):
        raise ValueError("History requires source metadata")
    source = payload["source"]
    try:
        start, end = date.fromisoformat(source["start_date"]), date.fromisoformat(source["end_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("History requires ISO source start_date and end_date") from exc
    if end < start:
        raise ValueError("History end_date precedes start_date")
    if not isinstance(source.get("pdf"), dict) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", str(source["pdf"].get("sha256", ""))):
        raise ValueError("History requires the source PDF SHA-256")
    pages = payload.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("History requires extracted pages")
    page_numbers = set()
    for page in pages:
        if not isinstance(page, dict) or type(page.get("page")) is not int or page["page"] < 0:
            raise ValueError("History requires zero-based integer page numbers")
        if page["page"] in page_numbers:
            raise ValueError("History contains duplicate page numbers")
        page_numbers.add(page["page"])
        if not isinstance(page.get("deals"), list) or not page["deals"]:
            raise ValueError("History refuses an empty extracted page")
        for deal in page["deals"]:
            if not isinstance(deal, dict) or not isinstance(deal.get("item"), str) or not deal["item"].strip():
                raise ValueError("History requires an item name for every offer")
    if "page_count" in source["pdf"]:
        count = source["pdf"]["page_count"]
        if type(count) is not int or count <= 0:
            raise ValueError("History requires a positive source PDF page_count")
        if len(page_numbers) != count or page_numbers != set(range(count)):
            raise ValueError("History requires every source PDF page; partial exports are refused")
    return start.isoformat(), end.isoformat()


def record_week(db_path, payload):
    """Record a validated export atomically; retries do not add observations.

    Reprocessing a date range retains every original payload and activates its
    newest submitted revision. A failed transaction retains the previous active
    revision. The caller's payload is never mutated.
    """
    raw = _json(payload)  # Reject non-JSON values and NaN before opening the DB.
    start, end = _validate(payload)
    week_id = f"{start}_{end}"
    run_id = _digest(_identity_content(payload))
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(_SCHEMA)
        connection.execute("BEGIN IMMEDIATE")
        previous = connection.execute(
            "SELECT run_id FROM history_active WHERE week_id = ?", (week_id,)).fetchone()
        changed = previous is None or previous[0] != run_id
        connection.execute(
            "INSERT OR IGNORE INTO history_runs VALUES (?, ?, ?, ?, ?, ?)",
            (run_id, week_id, start, end, datetime.now(timezone.utc).isoformat(), raw))
        if changed:
            connection.execute(
                "INSERT INTO history_active VALUES (?, ?) "
                "ON CONFLICT(week_id) DO UPDATE SET run_id = excluded.run_id", (week_id, run_id))
    return {"run_id": run_id, "changed": changed, "week_id": week_id}


def _offer(deal, page, week_id, occurrence):
    offer = dict(deal)
    offer["page"] = page
    offer["id"] = "offer-" + _digest([week_id, page, deal, occurrence])[:24]
    terms = offer_terms(deal.get("price"))
    packages = deal.get("package_sizes") or []
    if not isinstance(packages, list):
        packages = [str(packages)]
    package_parts = sorted({_normalize(value) for value in packages if _normalize(value)})
    unit = _normalize(deal.get("unit"))
    unit = {"each": "ea", "lbs": "lb", "pound": "lb", "package": "pkg"}.get(unit, unit)
    identity = [_normalize(deal["item"]), _normalize(deal.get("details")),
                package_parts, unit, terms["quantity"]]
    offer["product_key"] = "product-" + _digest(identity)[:24]
    offer["package_label"] = " · ".join(str(value) for value in packages if value)
    reasons = []
    if deal.get("_issues") or deal.get("issues"):
        reasons.append("Extraction is flagged for review")
    if deal.get("confidence") != "high":
        reasons.append("Extraction confidence is not high")
    prices = deal.get("prices") or []
    if not isinstance(prices, list) or len(prices) > 1:
        reasons.append("Multiple or ambiguous price variants")
    if terms["amount"] is None or not math.isfinite(terms["amount"]) or terms["amount"] <= 0:
        reasons.append("No valid advertised price")
        terms = {"quantity": None, "amount": None, "unit_price": None}
    if not package_parts and unit not in {"lb", "ea", "pkg", "bag", "bunch"}:
        reasons.append("Package size and sale unit are unspecified")
    for field in ("quantity", "amount", "unit_price"):
        if deal.get(field) is not None and deal[field] != terms[field]:
            reasons.append("Advertised price and numeric terms disagree")
            break
    offer["history_eligible"] = not reasons
    offer["history_reason"] = "; ".join(reasons) if reasons else None
    offer.update(terms)
    return offer


def build_history(db_path):
    """Return active weeks and chronological comparable-price observations."""
    path = Path(db_path)
    if not path.exists():
        return {"weeks": [], "series": [], "week_count": 0}
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        rows = connection.execute(
            "SELECT r.run_id, r.week_id, r.start_date, r.end_date, r.payload_json "
            "FROM history_active a JOIN history_runs r ON a.run_id = r.run_id "
            "ORDER BY r.start_date, r.end_date, r.week_id").fetchall()
    weeks, series = [], {}
    for run_id, week_id, start, end, raw in rows:
        payload = json.loads(raw)
        offers, occurrences = [], Counter()
        for page in payload["pages"]:
            for deal in page["deals"]:
                identity = _digest([page["page"], deal])
                offers.append(_offer(deal, page["page"], week_id, occurrences[identity]))
                occurrences[identity] += 1
        groups = defaultdict(list)
        for offer in offers:
            if offer["history_eligible"]:
                groups[offer["product_key"]].append(offer)
        for duplicates in groups.values():
            if len(duplicates) > 1:
                for offer in duplicates:
                    offer["history_eligible"] = False
                    offer["history_reason"] = "Multiple matching offers in the same week"
        for offer in offers:
            if not offer["history_eligible"]:
                continue
            key = offer["product_key"]
            item = series.setdefault(key, {
                "product_key": key, "item": offer["item"],
                "package_label": offer["package_label"], "unit": offer.get("unit"),
                "quantity": offer["quantity"], "observations": []})
            # Browse by the latest eligible observation's department. Category
            # corrections must not split the same product's price history.
            item["category"] = offer.get("category") or "Uncategorized"
            item["observations"].append({
                "week_id": week_id, "start_date": start, "price": offer["price"],
                "amount": offer["amount"], "unit_price": offer["unit_price"],
                "page": offer["page"], "offer_id": offer["id"]})
        extraction = payload.get("extraction") or {}
        weeks.append({"id": week_id, "run_id": run_id, "start_date": start,
                      "end_date": end, "source": payload["source"], "offers": offers,
                      "extraction": {"method": extraction.get("method"),
                                     "page_count": len(payload["pages"])}})
    return {"weeks": weeks,
            "series": sorted(series.values(), key=lambda value: (_normalize(value["item"]), value["product_key"])),
            "week_count": len(weeks)}
