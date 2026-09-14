"""Read descriptive fields from spans already assigned to a single offer.

This module does not decide offer boundaries or interpret sale prices. Color
is deliberately ignored: size labels and savings use several flyer palettes.
"""
import math
import re


_NUMBER = r"\d+(?:\.\d+)?"
_AMOUNT = rf"{_NUMBER}(?:\s*[-–/]\s*{_NUMBER})?"
_MEASUREMENT = re.compile(
    rf"\b{_AMOUNT}\s*[-–]?\s*(?:fl\.?\s*)?"
    r"(?:oz|lbs?|ltr|liters?|litres?|ml|kg|g|ct|count|packs?|pieces?|dozen|inch(?:es)?)"
    r"\b\.?(?:\s+(?:bag|pkg|package|bottle|can)s?\b\.?)?",
    re.IGNORECASE,
)
_UNIT = re.compile(r"^(?:/|per\s+)?(lbs?|pounds?|ea|each|pkg|package)\.?$", re.I)
_COUNT_LABEL = re.compile(
    r"^(?:packs?|pieces?|dozen|varieties|count|ct|oz|lbs?|ltr|liters?|litres?|ml|kg|g)\.?$", re.I)
_RAW_NUMBER = re.compile(r"^[\d\s$¢.,]+$")
_SAVE = re.compile(r"^save\b", re.I)
_FOOTER = re.compile(
    r"^(?:store hours|sale starts|sale ends|prices effective|prices good|effective\s*\d|"
    r"open regular hours|we reserve the right|not responsible|"
    r"(?:mon|tue|wed|thu|fri|sat|sun)\w*\b.*\b(?:am|pm)\b|"
    r"\d+\s+.+\s(?:street|st\.?|road|rd\.?|avenue|ave\.?|highway)\b)", re.I,
)
_ROLE_LABELS = {"meat specials", "grocery specials", "bakery shelf", "dairy",
                "produce", "snacks & beverages", "household & pet care",
                "beef • pork • poultry", "more for your dollar", "for your dollar"}


def _text(span):
    return " ".join(span["text"].split())


def _box(span):
    return tuple(span["bbox"])


def _signature(span):
    return span["text"], _box(span)


def _unit(text):
    match = _UNIT.fullmatch(text.strip())
    if not match:
        return None
    value = match[1].lower()
    return "lb" if value in {"lb", "lbs", "pound", "pounds"} else (
        "ea" if value in {"ea", "each"} else "pkg")


def _center(box):
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def _distance(first, second):
    ax, ay = _center(first)
    bx, by = _center(second)
    return math.hypot(ax - bx, ay - by)


def _run_box(run):
    spans = run.get("spans", ())
    if spans:
        boxes = [_box(span) for span in spans]
        return (min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes))
    return run["x0"], run["y"], run["x1"], run["y"]


def _adjacent_savings_unit(label, savings):
    """A small suffix beside a Save badge describes the saving's basis."""
    lb, sb = _box(label), _box(savings)
    _, ly = _center(lb)
    _, sy = _center(sb)
    size = max(label["size"], savings["size"])
    return (-2 <= lb[0] - sb[2] <= max(8, size)
            and abs(ly - sy) <= max(3, size * .45))


def extract_fields(spans, title_spans=(), price_runs=(), primary_run=None):
    """Return details, unit, savings, package_sizes, and explicit _issues.

    Standalone ``lb``/``ea``/``pkg`` labels identify sale units. Measurements
    such as ``2-lb bag`` remain package sizes and never imply a sale unit.
    If several savings badges exist, select the one nearest primary_run.
    """
    spans = list(spans)
    price_runs = list(price_runs)
    if primary_run is None and len(price_runs) == 1:
        primary_run = price_runs[0]
    runs = price_runs + ([primary_run] if primary_run is not None else [])
    excluded = {_signature(span) for run in runs for span in run.get("spans", ())}
    titles = {_signature(span) for span in title_spans}
    issues = []
    savings_spans = [s for s in spans if _SAVE.match(_text(s))]
    unit_spans = [s for s in spans if _unit(_text(s))]
    savings_values = []
    savings_units = set()
    for saving in savings_spans:
        text = _text(saving)
        excluded.add(_signature(saving))
        inline = re.search(r"(?:/|\s+per\s+|\s+)(lb\.?|ea\.?|pkg\.?)$", text, re.I)
        basis = _unit(inline[1]) if inline else None
        if inline:
            text = text[:inline.start()].rstrip()
        for label in unit_spans:
            if _adjacent_savings_unit(label, saving):
                excluded.add(_signature(label))
                savings_units.add(_signature(label))
                label_unit = _unit(_text(label))
                if basis and label_unit != basis:
                    issues.append("conflicting_savings_units")
                else:
                    basis = label_unit
        savings_values.append((saving, text + (f"/{basis}" if basis else "")))
    savings = None
    if savings_values:
        if len({value for _, value in savings_values}) > 1:
            issues.append("multiple_savings")
        savings = min(savings_values, key=lambda pair:
                      _distance(_box(pair[0]), _run_box(primary_run))
                      if primary_run is not None else _box(pair[0])[1])[1]

    sale_units = [s for s in unit_spans if _signature(s) not in savings_units]
    values = {_unit(_text(s)) for s in sale_units}
    unit = None
    if len(values) == 1:
        unit = next(iter(values))
    elif values:
        issues.append("conflicting_sale_units")
        if primary_run is not None:
            unit = _unit(_text(min(sale_units, key=lambda s:
                                  _distance(_box(s), _run_box(primary_run)))))
    excluded.update(_signature(s) for s in unit_spans)

    # Reunite a small count printed above PACK/Varieties before removing bare
    # price glyphs. The caller's price-run membership always takes precedence.
    replacements = {}
    for label in spans:
        if not _COUNT_LABEL.fullmatch(_text(label)) or _signature(label) in excluded:
            continue
        lb = _box(label)
        nearby = [s for s in spans
                  if re.fullmatch(_NUMBER, _text(s))
                  and _signature(s) not in excluded
                  and _signature(s) not in titles
                  and _box(s)[1] <= lb[1] + 2
                  and _distance(_box(s), lb) <= 2 * max(s["size"], label["size"])
                  and min(_box(s)[2], lb[2]) > max(_box(s)[0], lb[0])]
        if nearby:
            number = min(nearby, key=lambda s: _distance(_box(s), lb))
            replacements[_signature(label)] = _text(number) + " " + _text(label)
            excluded.add(_signature(number))

    parts, package_sizes = [], []
    for span in sorted(spans, key=lambda s: (_box(s)[1], _box(s)[0])):
        key = _signature(span)
        if key in excluded:
            continue
        text = replacements.get(key, _text(span))
        sizes = [match[0].strip() for match in _MEASUREMENT.finditer(text)]
        if text.casefold().strip(" .") == "dozen":
            sizes = [text]
        # A blue size can also be selected as a title by upstream style rules;
        # explicit measurement content must survive that overlap.
        if key in titles and not sizes:
            continue
        if (_RAW_NUMBER.fullmatch(text) or text.casefold().strip(" .") == "for"
                or _FOOTER.match(text)
                or text.casefold().strip(" .:") in _ROLE_LABELS
                or re.search(r",\s*(?:MA|NH|ME|RI)\s*\d{0,5}$", text)
                or text.casefold().strip(" .!") == "compare & save"):
            continue
        parts.append(text)
        package_sizes.extend(size for size in sizes if size not in package_sizes)
    return {"details": " ".join(parts), "unit": unit, "savings": savings,
            "package_sizes": package_sizes, "_issues": sorted(set(issues))}
