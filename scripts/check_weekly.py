#!/usr/bin/env python
"""Acquire the current official flyer and export offers extracted from its PDF."""
import argparse
import json
import math
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import extract_deals as ed
from check_state import build_key, reusable, save_success
from extractor_config import DEFAULT_CONFIG, load_config
from flyer_source import SourceError, fetch_current
from json_output import write_json
from reporting import enriched_export, record_and_render


def _validated_config(path):
    if path:
        with open(path, encoding="utf-8") as stream:
            overrides = json.load(stream)
        if not isinstance(overrides, dict):
            raise ValueError("Extractor config must be a JSON object")
        for key, default in DEFAULT_CONFIG.items():
            if key in overrides and isinstance(default, list):
                value = overrides[key]
                if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
                    raise ValueError(f"Extractor config {key!r} must be an array of strings")
    return load_config(path)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=Path("output/source"),
                        help="Directory for archived sources and current.json")
    parser.add_argument("--json-out", type=Path, default=Path("output/weekly-deals.json"),
                        help="Replace this export only after successful extraction")
    parser.add_argument("--timeout", type=float, default=30,
                        help="Network request timeout in seconds (default: 30)")
    parser.add_argument("--config", type=Path, help="Optional extractor JSON overrides")
    parser.add_argument("--fetch-only", action="store_true",
                        help="Archive and validate the source without extracting offers")
    parser.add_argument('--history-db', type=Path, default=Path('output/history.sqlite3'))
    parser.add_argument('--html-out', type=Path, default=Path('output/report.html'))
    parser.add_argument('--no-report', action='store_true',
                        help='Export JSON only, without updating history or HTML')
    parser.add_argument('--skip-unchanged', action='store_true',
                        help='Reuse a successful build when source, code and outputs match')
    parser.add_argument('--cache-file', type=Path, default=Path('output/automation/success.json'),
                        help='Successful-build receipt used by --skip-unchanged')
    args = parser.parse_args(argv)
    previous_config = ed.CONFIG
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise ValueError("Timeout must be a finite positive number")
        # A deal export must never replace its own source history.
        outputs = [args.json_out] + ([] if args.no_report else [args.history_db, args.html_out])
        destinations = outputs + ([args.cache_file] if args.skip_unchanged else [])
        if not args.fetch_only:
            if any(path.resolve().is_relative_to(args.source_dir.resolve()) for path in destinations):
                raise ValueError("Outputs must be outside the source archive directory")
            if len({path.resolve() for path in destinations}) != len(destinations):
                raise ValueError('JSON, history database, HTML and cache output paths must be distinct')
        ed.CONFIG = _validated_config(args.config)
        manifest = fetch_current(args.source_dir, timeout=args.timeout)
        pdf_path = args.source_dir / manifest["pdf"]["path"]
        state = "changed" if manifest["changed"] else "unchanged"
        print(f"Source archived: {manifest['start_date']} through {manifest['end_date']} "
              f"({state}).")
        print(f"PDF: {pdf_path.resolve()}")
        if args.fetch_only:
            return 0
        if manifest["pdf"]["text_page_count"] != manifest["pdf"]["page_count"]:
            raise SourceError("PDF contains pages without selectable text; "
                              "OCR or visual extraction is required before exporting offers")
        key = build_key(ROOT, manifest, ed.CONFIG) if args.skip_unchanged else None
        if key and reusable(args.cache_file, key, outputs):
            print('Unchanged: verified source and previous successful outputs; extraction skipped.')
            return 0
        result = ed.extract_document(pdf_path)
        count = sum(len(page["deals"]) for page in result["pages"])
        if count == 0:
            raise SourceError("PDF extraction produced no offers; the previous export was retained")
        empty_pages = [page['page'] + 1 for page in result['pages'] if not page['deals']]
        if empty_pages:
            raise SourceError(f"No offers extracted from PDF page(s) {empty_pages}; "
                              "review the layout before publishing. Previous export retained")
        result["source"] = {key: value for key, value in manifest.items() if key != "changed"}
        result["source"]["archive_root"] = str(args.source_dir.resolve())
        result["extraction"] = {"method": "pdf", "config": ed.CONFIG}
        result = enriched_export(result)
        write_json(args.json_out, result)
        if not args.no_report:
            report = record_and_render(result, args.history_db, args.html_out)
            print(f"History: {report['week_count']} weeks. Report: {args.html_out.resolve()}")
        if key:
            save_success(args.cache_file, key, outputs)
        print(f"Wrote {count} offers across {len(result['pages'])} pages to {args.json_out}.")
        return 0
    except (SourceError, OSError, ValueError, RuntimeError, sqlite3.Error) as error:
        print(f"Weekly check failed: {error}", file=sys.stderr)
        return 1
    finally:
        ed.CONFIG = previous_config


if __name__ == "__main__":
    sys.exit(main())
