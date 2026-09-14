"""Interpret flyer price glyphs and explicitly written package offers.

These helpers preserve source span identity. They do not decide which product
owns a price, or whether a multibuy permits buying a single item at that rate.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re


_NUMERIC = re.compile(r"^[\d$.,¢]+$")
_AMOUNT = r"\d+(?:\.\d{1,2})?"
_MULTI = re.compile(rf"^(\d+)\s*(?:for|/)\s*\$?({_AMOUNT})$", re.I)
_INLINE = re.compile(r"\$(\d+(?:\.\d{2})?)(?![\d.])")
_UNIT = re.compile(r"^(lb|lbs|pound|pounds|ea|each|pkg|package|bag|bunch)\.?$", re.I)
_QUANTITY = re.compile(
    r"^(?:pack|count|ct|varieties|piece|pieces|oz|lb|lbs|ltr|ml|liter|litre|kg|g)\.?$", re.I
)


def _box(span):
    return span["bbox"]


def _center(span):
    b = _box(span)
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _red(color):
    return (color >> 16) & 255 >= 180 and (color >> 8) & 255 <= 90 and color & 255 <= 90


def _unit(text):
    match = _UNIT.fullmatch(text.strip())
    if not match:
        return None
    value = match[1].lower()
    return {"lbs": "lb", "pound": "lb", "pounds": "lb", "each": "ea",
            "package": "pkg"}.get(value, value)


def _overprints(spans):
    """Later text supersedes earlier text at the same glyph position."""
    kept = []
    conflicting = set()
    for span in spans:
        b = _box(span)
        for old in kept[:]:
            a = _box(old)
            intersection = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(
                0, min(a[3], b[3]) - max(a[1], b[1]))
            small_area = min((a[2]-a[0]) * (a[3]-a[1]), (b[2]-b[0]) * (b[3]-b[1]))
            if small_area > 0 and intersection / small_area >= 0.8:
                if old['text'] != span['text'] or id(old) in conflicting:
                    conflicting.add(id(span))
                kept.remove(old)
        kept.append(span)
    return kept, conflicting


def _quantity_digit(span, spans):
    if not re.fullmatch(_AMOUNT, span["text"].strip()):
        return False
    x, y = _center(span)
    for label in spans:
        if not _QUANTITY.fullmatch(label["text"].strip()):
            continue
        b = _box(label)
        if b[0] - 2 <= x <= b[2] + 2 and abs(_center(label)[1] - y) <= 1.5 * label["size"]:
            if span["size"] <= label["size"] * 1.2:
                return True
    return False


def price_runs(spans):
    """Return numeric price runs with the extractor's x0/x1/y/size/spans shape.

    Small raised cents are retained; package-count digits and overprinted old
    prices are removed. A complete small $amount belongs to ``inline_offers``.
    ``spans`` contains original numeric spans and an adjacent unit when found.
    """
    spans = list(spans)
    candidates = []
    for span in spans:
        text = span["text"].strip()
        if not _red(span["color"]) or span["size"] < 5:
            continue
        if not (_NUMERIC.fullmatch(text) or _MULTI.fullmatch(text)):
            continue
        if re.fullmatch(r"\$\d+\.\d{2}", text) and span["size"] < 20:
            continue
        if not _quantity_digit(span, spans):
            candidates.append(span)
    candidates, overprinted = _overprints(candidates)
    candidates.sort(key=lambda s: (_center(s)[1], _box(s)[0]))
    bands = []
    for span in candidates:
        y = _center(span)[1]
        for band in bands:
            if abs(y - band["y"]) <= max(band["size"], span["size"]) * 0.55:
                band["spans"].append(span)
                band["y"] = sum(_center(s)[1] for s in band["spans"]) / len(band["spans"])
                band["size"] = max(band["size"], span["size"])
                break
        else:
            bands.append({"spans": [span], "y": y, "size": span["size"]})

    result = []
    for band in bands:
        groups = []
        for span in sorted(band["spans"], key=lambda s: _box(s)[0]):
            if groups and _box(span)[0] - max(_box(s)[2] for s in groups[-1]) <= 0.65 * max(
                    span["size"], max(s["size"] for s in groups[-1])):
                groups[-1].append(span)
            else:
                groups.append([span])
        for group in groups:
            dominant = max(group, key=lambda s: s["size"])
            size = dominant["size"]
            kept = [s for s in group if s["size"] >= 0.35 * size and (
                not dominant.get("font") or not s.get("font")
                or s["font"] == dominant["font"] or s["size"] >= 0.7 * size)]
            if size < 10 or not any(re.search(r"\d", s["text"]) for s in kept):
                continue
            result.append({"x0": min(_box(s)[0] for s in kept),
                           "x1": max(_box(s)[2] for s in kept),
                           "y": sum(_center(s)[1] for s in kept) / len(kept),
                           "size": size, "spans": kept,
                           "_issues": (["overprinted_price_text"]
                                       if any(id(s) in overprinted for s in kept) else [])})

    # Attach a unit only inside the local price neighborhood. Product-level
    # association remains the caller's responsibility.
    for span in spans:
        if not _unit(span["text"]):
            continue
        x, y = _center(span)
        nearby = []
        for run in result:
            y0 = min(_box(s)[1] for s in run["spans"])
            y1 = max(_box(s)[3] for s in run["spans"])
            margin = max(10, run["size"] * 0.35)
            if run["x0"] - margin <= x <= run["x1"] + margin and y0 - 4 <= y <= y1 + margin:
                nearby.append((abs(x - run["x1"]) + abs(y - y1), run))
        if nearby:
            min(nearby, key=lambda pair: pair[0])[1]["spans"].append(span)
    return sorted(result, key=lambda run: (run["x0"], run["y"]))


def _digits_amount(spans):
    texts = [s["text"].strip().replace("$", "") for s in spans]
    joined = "".join(texts)
    if re.fullmatch(_AMOUNT, joined) and "." in joined:
        return joined
    if len(texts) > 1 and joined.isdigit():
        # Dollar and cents glyphs are often separate, including raised 00.
        if len(texts[-1]) == 2:
            return "".join(texts[:-1]) + "." + texts[-1]
        dominant = max(s["size"] for s in spans)
        cut = len(spans)
        while cut > 0 and spans[cut-1]["size"] < dominant * 0.8:
            cut -= 1
        if 0 < cut < len(spans) and len("".join(texts[cut:])) == 2:
            return "".join(texts[:cut]) + "." + "".join(texts[cut:])
    return joined


def price_string(spans):
    """Build a canonical display price and normalized unit from one run."""
    spans = list(spans)
    units = [_unit(s["text"]) for s in spans if _unit(s["text"])]
    unit = units[0] if units else None
    numeric = sorted([s for s in spans if _NUMERIC.fullmatch(s["text"].strip())
                      or _MULTI.fullmatch(s["text"].strip())], key=lambda s: _box(s)[0])
    if not numeric:
        return None, unit
    joined = "".join(s["text"].strip() for s in numeric)
    multi = _MULTI.fullmatch(joined)
    if multi:
        return f"{int(multi[1])} for ${multi[2]}", unit
    if joined.endswith("¢") and re.fullmatch(r"\d+¢", joined):
        return joined, unit
    # A dollar symbol AFTER a quantity means multibuy; a leading dollar
    # symbol is ordinary currency, even when the amount contains a decimal.
    if "$" in joined and not joined.startswith("$"):
        before, after = joined.split("$", 1)
        if before.isdigit() and re.fullmatch(_AMOUNT, after):
            dollar_index = next(i for i, s in enumerate(numeric) if "$" in s["text"])
            amount_spans = list(numeric[dollar_index:])
            suffix = amount_spans[0]["text"].split("$", 1)[1]
            amount_spans[0] = dict(amount_spans[0], text=suffix)
            amount = _digits_amount([s for s in amount_spans if s["text"].strip()])
            return f"{int(before)} for ${amount}", unit
    amount = _digits_amount([s for s in numeric if s["text"].strip() != "$"])
    if re.fullmatch(_AMOUNT, amount):
        return amount, unit
    return None, unit


def offer_terms(display):
    """Return quantity, total amount and arithmetic per-unit price.

    The arithmetic unit_price does not establish single-purchase eligibility.
    Missing or invalid displays return three None values.
    """
    empty = {"quantity": None, "amount": None, "unit_price": None}
    if not isinstance(display, str):
        return empty
    text = display.strip()
    multi = _MULTI.fullmatch(text)
    quantity = int(multi[1]) if multi else 1
    if multi:
        value = multi[2]
    elif re.fullmatch(r"\d+¢", text):
        value = str(Decimal(text[:-1]) / 100)
    elif re.fullmatch(rf"\$?{_AMOUNT}", text):
        value = text.lstrip("$")
    else:
        return empty
    if quantity <= 0:
        return empty
    try:
        amount = Decimal(value)
    except InvalidOperation:
        return empty
    return {"quantity": quantity, "amount": float(amount),
            "unit_price": float(amount / quantity)}


def price_to_number(display):
    """Return the total advertised offer amount, not a multibuy unit price."""
    return offer_terms(display)["amount"]


def inline_offers(spans):
    """Extract explicit $prices with their size/variant labels and provenance.

    Savings and coupon amounts are excluded. A standalone small dollar price
    is accepted only with an adjacent package-size label, e.g. 2-LB. BAG.
    """
    spans = list(spans)
    result = []
    for span in spans:
        text = span["text"].strip()
        if re.match(r"(?:save\b|sale price|instant coupon|final cost)", text, re.I):
            continue
        for match in _INLINE.finditer(text):
            prefix = text[:match.start()]
            # Never treat a later savings amount as another variant price.
            if re.search(r"\bsave\b", prefix, re.I):
                continue
            label = prefix.strip(" *•:–—-")
            multibuy = re.search(r"(?:^|\s)(\d+)\s*(?:for|/)\s*$", label, re.I)
            quantity = int(multibuy[1]) if multibuy else None
            if multibuy:
                label = label[:multibuy.start()].strip()
                if not label:
                    # Some variant notes lead with the offer and put the
                    # qualifier afterward: '*2 for $3 plant-based, 5.3 oz.'.
                    label = text[match.end():].strip(" *•:,–—-")
            sources = [span]
            if label and not text.startswith(("•", "*")):
                # Native text may wrap a variant label onto the line directly
                # above its price (e.g. '•Iced Coffee' / '50 oz. 2 for $7').
                b = _box(span)
                preceding = []
                for candidate in spans:
                    a = _box(candidate)
                    overlap = min(a[2], b[2]) - max(a[0], b[0])
                    if (candidate["text"].strip().startswith("•")
                            and "$" not in candidate["text"]
                            and candidate["color"] == span["color"]
                            and candidate.get("font") == span.get("font")
                            and abs(candidate["size"] - span["size"]) < 0.5
                            and 0 < b[1] - a[1] <= span["size"] * 1.5
                            and overlap > 0.6 * min(a[2]-a[0], b[2]-b[0])):
                        preceding.append(candidate)
                if preceding:
                    previous = max(preceding, key=lambda s: _box(s)[1])
                    label = previous["text"].strip(" •") + " " + label
                    sources.append(previous)
            if not label:
                if quantity is not None:
                    continue
                if span["size"] >= 20:
                    continue
                x, y = _center(span)
                labels = [s for s in spans if re.search(
                    r"\d.*\b(?:oz|lb|pack|count|piece)\b", s["text"], re.I)
                    and "$" not in s["text"] and s is not span
                    and abs(_center(s)[0] - x) <= max(45, _box(s)[2]-_box(s)[0])
                    and 0 <= _box(span)[1] - _box(s)[3] <= 25]
                if not labels:
                    continue
                package = min(labels, key=lambda s: abs(_center(s)[1] - y))
                label = package["text"].strip(" •")
                sources.append(package)
            if re.fullmatch(r"\d+\s*(?:for|/)?", label, re.I):
                continue
            following = text[match.end():].lstrip()
            unit_match = re.match(r"(lb|lbs|ea|each|pkg|package)\.?\b", following, re.I)
            unit = _unit(unit_match[0]) if unit_match else None
            price = f"{quantity} for ${match[1]}" if quantity is not None else match[1]
            result.append({"label": label, "price": price, "unit": unit,
                           "price_n": price_to_number(price),
                           "_bbox": [round(min(_box(s)[0] for s in sources), 1),
                                     round(min(_box(s)[1] for s in sources), 1),
                                     round(max(_box(s)[2] for s in sources), 1),
                                     round(max(_box(s)[3] for s in sources), 1)]})
    return result
