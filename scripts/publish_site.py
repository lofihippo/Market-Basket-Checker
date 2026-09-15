#!/usr/bin/env python
"""Restore/export durable weekly history or build a portable static website."""
import argparse
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portable_site import build_site, export_archive, restore_archive


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['restore', 'archive', 'site'])
    parser.add_argument('--history-db', type=Path, default=Path('output/history.sqlite3'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--source-base-url', help='HTTPS archive directory; omit to package PDFs for local hosting')
    args = parser.parse_args(argv)
    try:
        if args.action == 'restore':
            result = restore_archive(args.directory, args.history_db)
        elif args.action == 'archive':
            result = export_archive(args.history_db, args.directory)
        else:
            result = build_site(args.history_db, args.directory, args.source_base_url)
        print(f'{args.action}: {result}')
        return 0
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        print(f'Publication failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
