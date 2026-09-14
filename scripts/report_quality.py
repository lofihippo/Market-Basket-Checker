#!/usr/bin/env python
"""Generate a quality report for the full extractor run.

Reports page counts, confidence distribution, low/medium-confidence items
(likely need human review), price outliers, and the extracted totals. Useful
for spotting regressions when a new weekly PDF is processed.

Usage: .venv/bin/python scripts/report_quality.py [pdf]
"""
import math
import sys
from collections import Counter

import pymupdf

sys.path.insert(0, ".")
import extract_deals as ed
from json_output import write_json

PDF = sys.argv[1] if len(sys.argv) > 1 else "market-basket-weekly-flyer.pdf"
doc = pymupdf.open(PDF)

grand = []
per_page = {}
for pno in range(doc.page_count):
    deals = ed.extract_page(doc[pno])
    grand.extend(deals)
    per_page[pno] = len(deals)

def numeric_prices(deal):
    """A variant-only offer still has a numeric price."""
    values = [deal.get("price_n")] + [p.get("price_n") for p in deal.get("prices", [])]
    return [value for value in values
            if isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value)]


def review_reasons(deal):
    reasons = list(deal.get("_issues", []))
    if deal.get("confidence") in ("low", "medium"):
        reasons.append(f"{deal['confidence']}_confidence")
    prices = numeric_prices(deal)
    if not prices:
        reasons.append("missing_numeric_price")
    if any(price > 40 for price in prices):
        reasons.append("price_above_40")
    return sorted(set(reasons))


# Counts and heuristic confidence are review signals, not measured accuracy.
conf = Counter(d.get("confidence") for d in grand)
review = [(d, review_reasons(d)) for d in grand if review_reasons(d)]
no_price = [d for d in grand if not numeric_prices(d)]
outliers = [d for d in grand if any(price > 40 for price in numeric_prices(d))]

print(f"PDF: {PDF}  |  {doc.page_count} pages")
print(f"TOTAL deals: {len(grand)}")
print("Per page:", ", ".join(f"p{p}={n}" for p, n in per_page.items()))
print(f"Confidence: {dict(conf)}")
print(f"Items lacking a numeric price: {len(no_price)}")
print(f"Price outliers (>$40): {len(outliers)}")
print("Counts and confidence are diagnostic signals; they do not measure accuracy or completeness.")

if review:
    print(f"\nItems flagged for review ({len(review)}; page numbers are zero-based):")
    for d, reasons in review:
        variants = [f"{p.get('label') or 'primary'}: {p.get('price')}"
                    for p in d.get("prices", [])]
        print(f"  page={d.get('page', '?')} [{d.get('confidence')}] {d.get('item')!r} "
              f"price={d.get('price')!r} variants={variants!r} "
              f"reasons={', '.join(reasons)}")
else:
    print("\nNo items flagged for review.")

# Save consolidated JSON
out = "/tmp/mb/consolidated.json"
write_json(out, grand)
print(f"\nSaved consolidated output to {out}")
