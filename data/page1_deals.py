#!/usr/bin/env python
"""Compatibility import for the dated September 6–12, 2026 reference.

The canonical annotations live alongside their checksum-verified PDF fixture.
"""
import json
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "2026-09-06" / "page1.json"
PAGE_1_DEALS = json.loads(REFERENCE.read_text(encoding="utf-8"))

if __name__ == "__main__":
    for deal in PAGE_1_DEALS:
        print(deal)
