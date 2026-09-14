#!/usr/bin/env python
"""Validate the fixed September 6–12, 2026 cover-page fixture.

Exit codes: 0 = exact normalized match, 1 = extraction discrepancies,
2 = fixture/configuration/read error. This never uses the mutable root PDF.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import extract_deals as ed
import pymupdf
from extractor_config import load_config
from validation import compare_deals, validate_reference

FIXTURE = ROOT / "tests" / "fixtures" / "2026-09-06"


def load_fixture(directory=FIXTURE):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    pdf = directory / manifest["pdf"]
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if digest != manifest["sha256"]:
        raise ValueError("fixture PDF checksum mismatch; restore the dated PDF")
    reference = json.loads((directory / manifest["reference"]).read_text(encoding="utf-8"))
    validate_reference(reference)
    return pdf, manifest["page"], reference


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE,
                        help="Directory containing a dated fixture manifest and reference")
    parser.add_argument("--config", help="Extractor overrides, as accepted by the extraction CLI")
    args = parser.parse_args(argv)
    previous_config = ed.CONFIG
    try:
        pdf, page, reference = load_fixture(args.fixture)
        ed.CONFIG = load_config(args.config)
        with pymupdf.open(pdf) as doc:
            deals = ed.extract_page(doc[page])
        result = compare_deals(deals, reference)
    except (OSError, ValueError, KeyError, TypeError, IndexError, RuntimeError) as error:
        print(f"Validation error: {error}", file=sys.stderr)
        return 2
    finally:
        ed.CONFIG = previous_config

    print(f"Fixture: {pdf} | page {page + 1}")
    print(f"Expected {len(reference)} offers; extracted {len(deals)}.")
    print(f"Exact normalized matches: {result['passed']}/{len(reference)}; "
          f"name matches: {result['matched']}.")
    for deal in result["missing"]:
        print(f"  MISSING: {deal['item']!r}")
    for deal in result["unexpected"]:
        print(f"  UNEXPECTED: {deal!r}")
    for diff in result["differences"]:
        actual = "<missing field>" if diff["missing_field"] else repr(diff["actual"])
        print(f"  DIFF: {diff['item']!r} {diff['field']}: "
              f"expected {diff['expected']!r}; got {actual}")
    print(f"Missing: {len(result['missing'])}; unexpected: {len(result['unexpected'])}; "
          f"field differences: {len(result['differences'])}.")
    print("PASS" if result["ok"] else "FAIL")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
