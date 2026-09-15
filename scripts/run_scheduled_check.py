#!/usr/bin/env python
"""Run the weekly CLI with a process lock, bounded runtime, log and status."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from json_output import write_json


def now():
    return datetime.now(timezone.utc).isoformat()


def read_status(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def run(root=ROOT, *, timeout=300):
    root = Path(root).resolve()
    directory = root / 'output/automation'
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / 'check.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Another scheduled check is running; this invocation was skipped.')
            return 0
        status_path = directory / 'status.json'
        prior = read_status(status_path)
        status = {'started_at': now(), 'state': 'running',
                  'last_success_at': prior.get('last_success_at')}
        write_json(status_path, status)
        logger = logging.getLogger('market_basket_schedule')
        logger.setLevel(logging.INFO)
        logger.propagate = False
        handler = RotatingFileHandler(directory / 'check.log', maxBytes=1_000_000,
                                      backupCount=3, encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
        logger.addHandler(handler)
        code = 1
        try:
            logger.info('Starting weekly check')
            completed = subprocess.run(
                [sys.executable, '-u', str(root / 'scripts/check_weekly.py'), '--skip-unchanged'],
                cwd=root, capture_output=True, text=True, timeout=timeout, check=False)
            output = (completed.stdout + completed.stderr).strip()
            code = completed.returncode
            status.update(state=('unchanged' if 'Unchanged: verified source' in completed.stdout
                                 else 'updated') if code == 0 else 'failed',
                          exit_code=code, message=output[-12000:])
            (logger.info if code == 0 else logger.error)(output)
        except (OSError, subprocess.TimeoutExpired) as exc:
            status.update(state='failed', exit_code=1, message=str(exc))
            logger.error('Check failed: %s', exc)
        finally:
            status['finished_at'] = now()
            if code == 0:
                status['last_success_at'] = status['finished_at']
            try:
                write_json(status_path, status)
            finally:
                logger.removeHandler(handler)
                handler.close()
        print(json.dumps(status, indent=2))
        return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--status', action='store_true', help='Show the latest run without checking the website')
    args = parser.parse_args(argv)
    try:
        if args.status:
            status = read_status(ROOT / 'output/automation/status.json')
            print(json.dumps(status or {'state': 'never_run'}, indent=2))
            return 0
        return run()
    except (OSError, ValueError) as exc:
        print(f'Scheduled check failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
