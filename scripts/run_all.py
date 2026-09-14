#!/usr/bin/env python
"""Run the extractor across all pages, collect deals, and print a summary."""
import sys
import pymupdf

sys.path.insert(0, ".")
import extract_deals as ed
from json_output import write_json

PDF = "market-basket-weekly-flyer.pdf"
doc = pymupdf.open(PDF)

grand = []
for pno in range(doc.page_count):
    deals = ed.extract_page(doc[pno])
    grand.extend(deals)
    print(f"page {pno}: {len(deals)} deals")

print(f"\nTOTAL deals across {doc.page_count} pages: {len(grand)}")

# breakdown of price types
from collections import Counter
types = Counter()
for d in grand:
    p = d["price"]
    types["2for$X" if (p and "for" in p) else "flat" if p else "none"] += 1
print("price types:", dict(types))

# save consolidated JSON
write_json("/tmp/mb/consolidated.json", grand)
print("saved /tmp/mb/consolidated.json")
