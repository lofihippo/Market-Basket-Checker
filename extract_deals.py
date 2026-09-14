#!/usr/bin/env python
"""
Market Basket weekly flyer extractor.

This module extracts structured deal records from the flyer PDF. It is built
incrementally (hill-climbed) against human-confirmed data.

The flyer uses two main layout families:
  1. Rounded single-product "cells" (cover page and many interior pages).
  2. Dense multi-product tables (e.g. DAIRY / FROZEN FOOD / SNACKS) plus
     mixed banner+grid pages.

Product cells and column dividers are detected from vector drawings. Text
styles and local geometry group titles without crossing product boundaries.

Usage:
    python extract_deals.py [pdf] [--page N ...] [--json-out FILE]
"""
from __future__ import annotations

import argparse
import json
import re
import sys

import pymupdf

from extractor_config import load_config
from json_output import write_json
from layout import changes_divider_row, column_bounds, crosses_divider, vertical_dividers
from name_styles import product_name_spans
from offer_fields import extract_fields
from offer_regions import assign_fields, span_box, split_cell_regions
from pricing import inline_offers, offer_terms, price_runs as _price_runs, price_string as _price_str, price_to_number

# ---- tunable configuration (override with --config <json>) ---------------
CONFIG = load_config()


# ---- color constants (packed RGB ints as pymupdf span["color"]) -----------
BLUE = 0x1B4491        # product names
RED = 0xED1C2B         # prices, savings, badges
DARKRED = 0xED2925
BLACK = 0x231F20       # detail / size text
BROWN = 0x8F5500       # "Back For The Season"


def _near(color, target, tol=30):
    c = ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)
    t = ((target >> 16) & 0xFF, (target >> 8) & 0xFF, target & 0xFF)
    return all(abs(a - b) <= tol for a, b in zip(c, t))


def is_blue(c):
    return _near(c, BLUE, 25)


def is_red(c):
    # Prices appear in several red shades across the flyer's layout families
    # (0xed1c2b / 0xed2925 on rounded cells, 0xff0000 on table pages, plus a
    # few variants). Treat a saturated red-ish color as "red".
    r, g, b = (c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF
    if r >= 180 and g <= 90 and b <= 90:
        return True
    return _near(c, RED, 35) or _near(c, DARKRED, 35)


def is_black(c):
    return _near(c, BLACK, 30)


def is_white(c):
    return (((c >> 16) & 0xFF) > 240 and ((c >> 8) & 0xFF) > 240 and (c & 0xFF) > 240)


SAVE_RE = re.compile(r"^Save")


def detect_cells(page):
    """Find bounded product cells and undivided banners from vector drawings.

    Returns a list of maximal pymupdf.Rect that fall in the expected
    product-cell size band. Duplicate inner/outer borders are collapsed.
    """
    rects, banners = [], []
    for d in page.get_drawings():
        r = d.get("rect")
        if r is None:
            continue
        w, h = r.width, r.height
        # Deal cells vary in width: standard ~221, wide ~332, tall banner
        # ~334, and narrow deli ~144. Cover that range. The height band keeps
        # us to product cells (excludes page frames / large banners).
        if 135 <= w <= 360 and 85 <= h <= 300:
            rects.append(pymupdf.Rect(r))
        elif 360 < w < page.rect.width and 85 <= h <= 180:
            banners.append(pymupdf.Rect(r))

    def area(r):
        return r.width * r.height

    def contains(outer, inner):
        return (outer.x0 <= inner.x0 + 1 and outer.y0 <= inner.y0 + 1 and
                outer.x1 >= inner.x1 - 1 and outer.y1 >= inner.y1 - 1)

    # Wide single-offer banners (e.g. bakery muffins) have no inner product
    # cells or column rules. Do not swallow an entire multi-product section.
    dividers = vertical_dividers(page)
    for banner in banners:
        if any(contains(banner, r) for r in rects):
            continue
        if any(banner.x0 + 10 < r.x0 < banner.x1 - 10
               and min(banner.y1, r.y1) - max(banner.y0, r.y0) >= 35
               for r in dividers):
            continue
        rects.append(banner)

    dedup = []
    for r in sorted(rects, key=area, reverse=True):
        if any(contains(o, r) for o in dedup):
            continue
        dedup.append(r)
    return dedup


def collect_spans(page):
    """Return all text spans on the page as dicts with bbox/size/color/text."""
    spans = []
    data = page.get_text("rawdict")
    for b in data["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            for s in line["spans"]:
                chars = s["chars"]
                text = "".join(char["c"] for char in chars)
                # Some layouts put the price and savings in one native span.
                # Split only this explicit syntax, using the glyph boxes so
                # ownership and source coordinates remain exact.
                combined = re.fullmatch(r"\s*(\$\d+(?:\.\d{2})?)\s+(Save\b.*?)\s*", text, re.I)
                segments = [chars[a:b] for a, b in
                            (combined.span(1), combined.span(2))] if combined else [chars]
                for segment in segments:
                    txt = "".join(char["c"] for char in segment).strip()
                    if not txt:
                        continue
                    box = pymupdf.Rect(segment[0]["bbox"])
                    for char in segment[1:]:
                        box |= pymupdf.Rect(char["bbox"])
                    spans.append({
                        "text": txt, "bbox": box, "size": s["size"],
                        "color": s["color"], "font": s["font"],
                    })
    return spans


def assign_to_cell(sp, cells):
    """Return index of the cell containing the span's center, else None."""
    cx = (sp["bbox"].x0 + sp["bbox"].x1) / 2
    cy = (sp["bbox"].y0 + sp["bbox"].y1) / 2
    for i, r in enumerate(cells):
        if r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1:
            return i
    return None


def collect_cell_spans(spans, cells):
    grouped = [[] for _ in cells]
    for sp in spans:
        idx = assign_to_cell(sp, cells)
        if idx is not None:
            grouped[idx].append(sp)
    return grouped


def parse_price(cell_spans):
    """Parse the price for a single-product group of spans.

    Returns (price_str, unit_str). Delegates to the robust run detection so
    single-product cells and multi-product splits use identical logic.
    """
    runs = _price_runs(cell_spans)
    if not runs:
        return None, None
    # For a single product there is exactly one price run.
    run = max(runs, key=lambda r: r["size"])
    return _price_str(run["spans"])


def _is_brand_fragment(prev_text, span):
    """Decide whether a blue span joins onto the previous word (no space).

    Letter-spaced brand names are rendered as single-character (or short caps)
    spans that sit directly beside the previous span with only a small gap,
    e.g. "P" + "EPPERIDGE" + "F" + "ARM". We join those into one word.
    """
    txt = span["text"]
    short_caps = re.fullmatch(r"[A-Z]+", txt.strip())
    if not short_caps:
        return False
    # The previous accumulated word should also be caps-ish brand material.
    base = re.sub(r"\s+", "", prev_text)
    if not base or not base.isupper():
        return False
    return True


def parse_name(cell_spans):
    """Assemble a title from product styles within an enclosed offer region."""
    blues = product_name_spans(cell_spans, allow_white=True)
    if not blues:
        return None
    # Sort top-to-bottom then left-to-right; simple line grouping by bbox y.
    blues.sort(key=lambda s: (round(s["bbox"].y1), s["bbox"].x0))
    lines, cur = [], []
    last_y = None
    for s in blues:
        y = round(s["bbox"].y1)
        if last_y is None or abs(y - last_y) <= 4:
            cur.append(s)
        else:
            lines.append(cur)
            cur = [s]
        last_y = y
    if cur:
        lines.append(cur)
    out = []
    for line in lines:
        line.sort(key=lambda s: s["bbox"].x0)
        words = []
        for index, s in enumerate(line):
            txt = s["text"]
            # Letter-spaced brand spans: a single character (or short caps
            # fragment) that sits immediately after the previous span is part
            # of the same visual word, so join without a space.
            if (words and _is_brand_fragment(words[-1], s)
                    and s["bbox"].x0 - line[index - 1]["bbox"].x1 <= s["size"] * 0.12
                    and s["size"] <= line[index - 1]["size"] * 1.1):
                words[-1] = words[-1] + txt
            else:
                words.append(txt)
        out.append(" ".join(words))
    return " ".join(out)


def parse_savings(cell_spans):
    """Return savings using the same field rules as complete offers."""
    runs = _price_runs(cell_spans)
    primary = max(runs, key=lambda run: run['size']) if runs else None
    return extract_fields(cell_spans, price_runs=runs, primary_run=primary)['savings']


def parse_details(cell_spans, name=None):
    """Return descriptive fields without price glyphs or savings badges."""
    return extract_fields(cell_spans, product_name_spans(cell_spans, allow_white=True),
                          _price_runs(cell_spans))['details']


def _clean_name(name):
    """Clean a parsed product name for readability.

    Normalises whitespace and joins letter-spaced artifacts (e.g. the
    "P EPPERIDGE F ARM" brand, which is rendered with letter-spacing so the
    spans come through as single characters). Also drops common promotional
    taglines that appear as cell headers rather than part of a product name.
    """
    if not name:
        return name
    s = re.sub(r"[\u2008\u2009\u00a0]+", " ", name)   # narrow/odd spaces
    s = re.sub(r"\s+", " ", s).strip()

    # Drop known promotional taglines (cell titles, not product names).
    for t in CONFIG.get("taglines", []):
        s = re.sub(r"\s*".join(re.escape(word) for word in t.split()), " ", s)

    # Letter-spaced brand names: a run of single capital letters each followed
    # by a space are actually one word, e.g. "P EPPERIDGE F ARM". Collapse a
    # sequence of single-letter tokens into one.
    s = re.sub(r"\b([A-Z])(?: \1)+\b", lambda m: m.group(1), s)

    s = re.sub(r"\s+", " ", s).strip()
    # Remove leading/trailing separators.
    s = re.sub(r"^[\s|,;:.—-]+|[\s|,;:.—-]+$", "", s)
    return re.sub(r"\s+", " ", s)


def _split_name_flavors(name):
    """Split a product name into (primary_title, flavor_suffix).

    Some product names carry a trailing bullet-prefixed flavor list, e.g.
    "More Please •Shrimp In Pesto •Clam Linguine ..." or "Protein Salads
    •Tuna•Seafood •Cranberry Chicken". We move that flavor list into the
    details so the item name stays short and readable. Multi-brand deals like
    "•7Up •A&W •Sunkist" are left intact (they are the product, not a suffix).
    """
    if not name:
        return name, ""
    # A leading bullet on a single product name (e.g. "•Pacific Smelts", which
    # has no further bullets) is a stray bullet -> strip it. A multi-brand deal
    # ("•7Up •A&W •Sunkist") has further bullets and is kept intact.
    if name.startswith("•") and any(ch.isalpha() for ch in name):
        remainder = name[1:].strip()
        if "•" not in remainder:
            name = remainder
    m = re.match(r"^(.*?)\s*(•.*)$", name)
    if not m:
        return name, ""
    title = m.group(1).strip()
    flavors = m.group(2).strip()
    # If the title part has no real word (i.e. the name is entirely bullets,
    # a multi-brand deal), keep it all as the name.
    if not any(ch.isalpha() for ch in title) or len(title.split()) < 2:
        return name, ""
    return title, flavors


def _parse_single(cell_spans, bbox=None, primary_run=None, title_spans=None):
    """Build a readable offer while retaining explicit price alternatives."""
    selected_titles = (list(title_spans) if title_spans is not None
                       else product_name_spans(cell_spans, allow_white=True))
    name = _clean_name(parse_name(selected_titles))
    name, _ = _split_name_flavors(name)
    # Exclude only the final title from details. Blue flavor lists and removed
    # qualifiers such as Wild/All Natural remain descriptive source text.
    name_key = re.sub(r"\W+", "", (name or "").casefold())
    titles = [s for s in selected_titles
              if re.sub(r"\W+", "", s['text'].casefold()) in name_key]
    runs = _price_runs(cell_spans)
    if primary_run is None and runs:
        primary_run = max(runs, key=lambda r: r['size'])
    fields = extract_fields(cell_spans, titles, runs, primary_run)
    price, _ = _price_str(primary_run['spans']) if primary_run else (None, None)
    choices = []
    if primary_run and price_to_number(price) is not None:
        choices.append({'label': None, 'price': price, 'price_n': price_to_number(price),
                        'unit': fields['unit'],
                        '_bbox': [round(v, 1) for v in span_box(primary_run['spans'])]})
    for choice in inline_offers(cell_spans):
        choice = dict(choice)
        # A price printed in one span can appear in both detection paths.
        duplicate = any(c['price_n'] == choice['price_n']
                        and pymupdf.Rect(c['_bbox']).intersects(pymupdf.Rect(choice['_bbox']))
                        for c in choices)
        if not duplicate:
            choices.append(choice)
    for choice in choices:
        choice.update(offer_terms(choice['price']))
    if price is None and len(choices) == 1:
        price = choices[0]['price']
    if fields['unit'] is None and choices:
        units = {c.get('unit') for c in choices}
        if len(units) == 1:
            fields['unit'] = next(iter(units))
    issues = list(fields.pop('_issues'))
    for run in runs:
        issues.extend(run.get('_issues', []))
    if not choices:
        issues.append('missing_or_unparsed_price')
    if len(runs) > 1:
        issues.append('multiple_primary_price_runs')
    deal = {'item': name, **fields, 'price': price, 'price_n': price_to_number(price),
            **offer_terms(price), 'prices': choices, '_issues': sorted(set(issues)),
            '_source_text': '\n'.join(s['text'] for s in sorted(cell_spans,
                                     key=lambda s: (s['bbox'].y0, s['bbox'].x0)))}
    if bbox is not None:
        deal['_bbox'] = [round(v, 1) for v in bbox]
    return deal


def parse_cell(cell_spans, bbox=None):
    """Separate adjacent offers using price edges, retaining variant text."""
    runs = _price_runs(cell_spans)
    if len(runs) >= 2:
        regions = split_cell_regions(cell_spans, runs, bbox or span_box(cell_spans))
        deals = []
        for run, (region, sub) in zip(runs, regions):
            if sub:
                deal = _parse_single(sub, region, primary_run=run)
                if deal['item']:
                    deals.append(deal)
        if deals:
            if len(deals) != len(runs):
                for deal in deals:
                    deal['_issues'].append('unassigned_price_region')
            return deals
    return [_parse_single(cell_spans, bbox)]


def _is_store_meta(text):
    """Return True for store-location metadata spans (not product names)."""
    t = text.strip()
    if not t:
        return False
    if t.startswith("Store Hours"):
        return True
    if re.search(r",\s*MA\s*$", t):                 # "Hanover, MA"
        return True
    streets = "|".join(re.escape(x) for x in CONFIG.get("store_streets", []))
    if streets and re.search(r"\b\d+\s+(%s)\b" % streets, t):
        return True                                 # street addresses
    if re.search(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b.*\b(AM|PM)\b", t):
        return True                                 # store hours text
    if "am -" in t and "pm" in t.lower():
        return True                                 # "8am - 9pm"
    return False


def _name_groups(spans, dividers=()):
    """Cluster supported title styles into per-product, multi-line groups.

    A product name is a set of spans that share a column (x overlap) and
    are vertically close. Returns a list of span-lists, each a product name.
    Store-location metadata (town + street address + store hours) is skipped.
    """
    blues = [s for s in product_name_spans(spans)
             if s["size"] >= 9
             and not _is_store_meta(s["text"])]
    blues.sort(key=lambda s: (s["bbox"].y0, s["bbox"].x0))
    groups = []
    for s in blues:
        placed = False
        for g in groups:
            gx0 = min(sp["bbox"].x0 for sp in g)
            gx1 = max(sp["bbox"].x1 for sp in g)
            gy1 = max(sp["bbox"].y1 for sp in g)
            gb = pymupdf.Rect(gx0, min(sp["bbox"].y0 for sp in g), gx1, gy1)
            size = min(s["size"], max(sp["size"] for sp in g))
            overlap = min(s["bbox"].x1, gx1) - max(s["bbox"].x0, gx0)
            same_line = abs(s["bbox"].y1 - gy1) <= 2
            # Allow adjacent glyph fragments, not neighboring titles
            # separated by the old 12pt allowance. Stacked products must not
            # join across the 17pt gap between beer and wine names.
            adjacent = same_line and 0 <= s["bbox"].x0 - gx1 <= 2
            if (overlap > 0 or adjacent) and s["bbox"].y0 - gy1 <= max(3, size * 0.45):
                if (not crosses_divider(gb, s["bbox"], dividers)
                        and not changes_divider_row(gb, s["bbox"], dividers)):
                    g.append(s)
                    placed = True
                    break
        if not placed:
            groups.append([s])
    # Small-cap brand fragments can arrive in PDF order as large initials
    # followed by both smaller word endings. Join adjacent brand words after
    # clustering, without crossing a rule or joining separate product rows.
    for group in groups[:]:
        if group not in groups:
            continue
        for other in groups[:]:
            if other is group:
                continue
            a, b = _group_bbox(group), _group_bbox(other)
            size = max(s['size'] for s in group + other)
            brand = all(s['text'].isupper() for s in group + other)
            initial = any(len(s['text']) == 1 for s in group + other)
            if (brand and initial and -1 <= b.x0 - a.x1 <= 2
                    and max(a.height, b.height) <= size * 1.5
                    and abs(a.y0 - b.y0) <= size * 0.4
                    and not crosses_divider(a, b, dividers)):
                group.extend(other)
                groups.remove(other)
    return groups


def _group_bbox(group):
    x0 = min(s["bbox"].x0 for s in group)
    x1 = max(s["bbox"].x1 for s in group)
    y0 = min(s["bbox"].y0 for s in group)
    y1 = max(s["bbox"].y1 for s in group)
    return pymupdf.Rect(x0, y0, x1, y1)


def extract_table_page(page, exclude_cells=None):
    """Extract deals from a dense table-layout page (DAIRY/FROZEN/SNACKS).

    Products are column-grid cells: each has a blue name group, a red price,
    a 'Save' badge, and small black detail text. We detect name groups and
    the global set of price runs, then match each name to the price run in
    the same column directly below it.

    If exclude_cells (rounded-cell boxes) is given, name groups that fall
    inside those boxes are skipped so a page mixing both layouts isn't
    double-counted.
    """
    spans = collect_spans(page)
    dividers = vertical_dividers(page)
    name_spans = [s for s in spans if not exclude_cells
                  or assign_to_cell(s, exclude_cells) is None]
    groups = _name_groups(name_spans, dividers)
    if not groups:
        return []

    # Global price runs across the whole page (not just one cell).
    table_spans = [s for s in spans if not exclude_cells
                   or assign_to_cell(s, exclude_cells) is None]
    global_runs = _price_runs(table_spans)

    contexts = []
    for g in groups:
        if exclude_cells and _group_in_cells(g, exclude_cells):
            continue
        gb = _group_bbox(g)
        left, right = column_bounds(gb, dividers, page.rect)
        # A neighboring title is another boundary when the PDF has no rule.
        # Only use titles in the same row; beer/wine rows have different lanes.
        for other in groups:
            if other is g:
                continue
            ob = _group_bbox(other)
            if min(gb.y1, ob.y1) > max(gb.y0, ob.y0):
                if ob.x1 <= gb.x0 and left < ob.x1:
                    left = max(left, (ob.x1 + gb.x0) / 2)
                elif ob.x0 >= gb.x1 and right > ob.x0:
                    right = min(right, (gb.x1 + ob.x0) / 2)
        # Without a drawn lane, retain a local window instead of allowing a
        # title to claim any price across the full page.
        left = max(left, gb.x0 - 30)
        if right == page.rect.x1:
            right = min(right, gb.x1 + 95)
        context = _table_cell_deal(g, table_spans, global_runs,
                                   lane=(left, right), return_context=True)
        if context:
            # Some table titles sit below product photos. Their column rules
            # retain size labels printed above the title (e.g. beer 24 PACKS).
            cy = (gb.y0 + gb.y1) / 2
            rules = [r for r in dividers if r.y0 - 8 <= cy <= r.y1 + 8
                     and min(abs(r.x0 - left), abs(r.x0 - right)) <= 3]
            if rules:
                context['bbox'].y0 = min(context['bbox'].y0, min(r.y0 for r in rules) - 5)
            contexts.append(context)
    # A smaller bullet list sharing the title's price and column is a flavor
    # qualifier (e.g. seafood dip varieties), not another priced product.
    for variant in contexts[:]:
        if variant not in contexts or not all(
                s['text'].strip().startswith('•') for s in variant['group']):
            continue
        vb = _group_bbox(variant['group'])
        for parent in contexts:
            if parent is variant or parent['run'] is not variant['run']:
                continue
            pb = _group_bbox(parent['group'])
            if (not parent['group'][0]['text'].strip().startswith('•')
                    and vb.y0 >= pb.y0
                    and min(vb.x1, pb.x1) > max(vb.x0, pb.x0)
                    and max(s['size'] for s in variant['group'])
                    <= max(s['size'] for s in parent['group']) * .85):
                parent['group'].extend(variant['group'])
                parent['bbox'] |= variant['bbox']
                contexts.remove(variant)
                break
    for context in contexts:
        box = context['bbox']
        center = (context['lane'][0] + context['lane'][1]) / 2
        top = _group_bbox(context['group']).y0
        for other in contexts:
            next_top = _group_bbox(other['group']).y0
            if next_top > top + 5 and other['lane'][0] <= center <= other['lane'][1]:
                box.y1 = min(box.y1, next_top - 2)
    owned, issues = assign_fields(table_spans, contexts)
    deals = []
    for context, selected, warnings in zip(contexts, owned, issues):
        deal = _parse_single(selected, context['bbox'], context['run'], context['group'])
        deal['_issues'] = sorted(set(deal['_issues'] + warnings))
        deals.append(deal)
    return deals


def _group_in_cells(group, cells):
    """Return True if the group's name falls inside any rounded-cell box."""
    gb = _group_bbox(group)
    cx = (gb.x0 + gb.x1) / 2
    cy = (gb.y0 + gb.y1) / 2
    for r in cells:
        if r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1:
            return True
    return False


def _table_cell_deal(group, spans, global_runs, lane=None, return_context=False):
    """Extract one product from its name group + the price run below it.

    The price run is chosen from the global runs: it must fall in the name
    group's column (x-overlap with the name range) and sit just below the
    name group's bottom (nearest y, within a reasonable vertical gap).
    """
    gb = _group_bbox(group)
    # Column window: the name's x-range, widened a little. A product's price
    # may be left- or right-aligned relative to its name, so we require the
    # price run's x-center to fall inside this window rather than being close
    # to the name's center.
    lo_x, hi_x = lane if lane else (gb.x0 - 20, gb.x1 + 20)

    # Match a nearby price beside or below the title within the established
    # lane. Horizontal distance breaks ties against neighboring prices.
    candidates = [r for r in global_runs
                  if lo_x <= ((r["x0"] + r["x1"]) / 2) <= hi_x
                  and r["y"] >= gb.y0 - min(10, max(s["size"] for s in group) * 0.5)
                  and (r["y"] - gb.y1) <= 130]
    if not candidates:
        return None
    run = min(candidates, key=lambda r:
              max(0, r["y"] - gb.y1)
              + 0.5 * max(gb.x0 - r["x1"], r["x0"] - gb.x1, 0))
    box = pymupdf.Rect(lo_x, gb.y0 - 5, hi_x,
                      max(gb.y1, span_box(run['spans']).y1 + 10))
    context = {'group': group, 'run': run, 'lane': (lo_x, hi_x), 'bbox': box}
    if return_context:
        return context
    owned, warnings = assign_fields(spans, [context])
    deal = _parse_single(owned[0], box, run, group)
    deal['_issues'] = sorted(set(deal['_issues'] + warnings[0]))
    return deal


def score_confidence(deal):
    """Assign a confidence score (high/medium/low) to an extracted deal.

    A plausible price and name start high. Ambiguous ownership, conflicting
    fields, or overprinted prices lower the label; missing prices or lost
    price regions lower it further. This is not a measured accuracy score.
    """
    name = (deal.get("item") or "").strip()
    price = deal.get("price")
    n = deal.get("price_n")
    score = 1.0

    has_variant_price = any(p.get('price_n') is not None for p in deal.get('prices', []))
    if price is None and not has_variant_price:
        score -= 0.6
    elif price is not None and n is None:
        score -= 0.15                # got a price string but not numeric
    if not name:
        score -= 0.5
    stripped = name.lstrip("•").strip()
    if "•" in stripped:
        score -= 0.2                 # multi-brand name (expected, but noisy)
    elif name.startswith("•"):
        score -= 0.3
    if len(name.split()) > 10:
        score -= 0.25                # unusually long name (possible merge)

    if deal.get('_issues'):
        score = min(score, 0.7)
        if any(issue in deal['_issues'] for issue in
               ('missing_or_unparsed_price', 'unassigned_price_region', 'shared_price_or_title')):
            score = min(score, 0.4)

    if score >= 0.8:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def extract_page(page):
    """Extract deals from a page using the appropriate layout family.

    The flyer mixes layouts within a single page: rounded product cells
    (banners) coexist with table-grid sections (e.g. page 2's MEAT SPECIALS).
    We run both extract paths and collapse repeated detections per region.
    """
    cells = detect_cells(page)
    spans = collect_spans(page)

    deals = []
    grouped = collect_cell_spans(spans, cells)
    for i, cell_spans in enumerate(grouped):
        if not cell_spans:
            continue
        deals.extend(parse_cell(cell_spans, cells[i]))

    # Table-grid products in the regions not covered by rounded cells.
    table_deals = extract_table_page(page, exclude_cells=cells)
    deals.extend(table_deals)

    # Collapse duplicate detections within the same region. Distinct regions
    # may legitimately advertise the same generic title at different prices.
    non_products = set(CONFIG.get("non_products", []))
    seen = set()
    dedup = []
    for d in deals:
        name = (d.get("item") or "").strip().lower()
        key = (name, tuple(d.get("_bbox", ())))
        if not name or key in seen or name in non_products:
            continue
        seen.add(key)
        d['page'] = page.number
        d["confidence"] = score_confidence(d)
        dedup.append(d)
    return dedup


def extract_document(pdf, pages=None):
    """Shared complete-document result for local and acquired flyer inputs."""
    with pymupdf.open(pdf) as doc:
        selected = pages if pages is not None else range(doc.page_count)
        return {'pages': [{'page': pno, 'deals': extract_page(doc[pno])}
                          for pno in selected]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf", nargs="?", default="market-basket-weekly-flyer.pdf")
    ap.add_argument("--page", action="append", type=int)
    ap.add_argument("--json-out", help="Replace this file with one JSON document containing the selected pages")
    ap.add_argument("--config", help="Optional JSON config to override defaults")
    args = ap.parse_args()

    if args.config:
        global CONFIG
        CONFIG = load_config(args.config)

    result = extract_document(args.pdf, args.page)
    for page in result['pages']:
        print(f"\n===== PAGE {page['page']}: {len(page['deals'])} deals =====")
        for deal in page['deals']:
            print(json.dumps(deal, ensure_ascii=False))
    if args.json_out:
        write_json(args.json_out, result)


if __name__ == "__main__":
    main()
