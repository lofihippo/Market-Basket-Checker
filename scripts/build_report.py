#!/usr/bin/env python
"""Import dated extraction exports into history and build the offline report."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deal_history import record_week
from reporting import enriched_export, render_history


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('exports', nargs='*', type=Path,
                        help='Dated JSON exports with source metadata; omit to rebuild stored history')
    parser.add_argument('--history-db', type=Path, default=Path('output/history.sqlite3'))
    parser.add_argument('--html-out', type=Path, default=Path('output/report.html'))
    args = parser.parse_args(argv)
    try:
        protected = [args.history_db.resolve(), *(p.resolve() for p in args.exports)]
        if args.html_out.resolve() in protected or args.history_db.resolve() in [p.resolve() for p in args.exports]:
            raise ValueError('Report, history database, and source exports must have distinct paths')
        # Parse and enrich inputs first; record_week validates each transaction.
        payloads = [enriched_export(json.loads(path.read_text(encoding='utf-8'))) for path in args.exports]
        for payload in payloads:
            record_week(args.history_db, payload)
        data = render_history(args.history_db, args.html_out)
        print(f"Report saved: {args.html_out.resolve()} ({data['week_count']} recorded weeks)")
        return 0
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        print(f'Report build failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
