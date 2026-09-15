#!/usr/bin/env python
"""Prepare, install, inspect or disable this project's macOS weekly job."""
import argparse
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
LABEL = 'org.reasonix.market-basket-weekly-checker'


def configuration(root=ROOT, *, hour=9, minute=0):
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError('Hour must be 0–23 and minute must be 0–59')
    root = Path(root).resolve()
    # Keep the virtualenv path: resolving this symlink would bypass the venv.
    python = root / '.venv/bin/python'
    script = root / 'scripts/run_scheduled_check.py'
    if not python.is_file() or not script.is_file():
        raise ValueError('Create the project .venv and install requirements first')
    return {
        'Label': LABEL,
        'ProgramArguments': [str(python), '-u', str(script)],
        'WorkingDirectory': str(root),
        'StartCalendarInterval': [{'Weekday': day, 'Hour': hour, 'Minute': minute} for day in (0, 1)],
        'RunAtLoad': True,
        'ProcessType': 'Background',
        'LowPriorityIO': True,
        'EnvironmentVariables': {'PYTHONUNBUFFERED': '1', 'PYTHONIOENCODING': 'utf-8'},
        'StandardOutPath': str(root / 'output/automation/launchd.stdout.log'),
        'StandardErrorPath': str(root / 'output/automation/launchd.stderr.log'),
    }


def write_plist(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.name, delete=False) as stream:
            temporary = Path(stream.name)
            plistlib.dump(data, stream)
        temporary.chmod(0o644)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def launchctl(*args, check=True):
    result = subprocess.run(['/bin/launchctl', *args], capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise RuntimeError(result.stderr.strip() or f'launchctl failed with exit {result.returncode}')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'install', 'status', 'disable'])
    parser.add_argument('--hour', type=int, default=9, help='Mac local hour for Sunday and Monday checks')
    parser.add_argument('--minute', type=int, default=0)
    args = parser.parse_args(argv)
    prepared = ROOT / 'output/automation' / (LABEL + '.plist')
    installed = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    domain = f'gui/{os.getuid()}'
    service = f'{domain}/{LABEL}'
    try:
        if args.action == 'prepare':
            write_plist(prepared, configuration(hour=args.hour, minute=args.minute))
            print(f'Prepared (not installed): {prepared}')
            return 0
        if sys.platform != 'darwin':
            raise ValueError('Installing this schedule requires macOS')
        if args.action == 'status':
            print(f'Installed configuration: {installed if installed.exists() else "not installed"}')
            result = launchctl('print', service, check=False)
            print(result.stdout.strip() or result.stderr.strip())
            return 0 if result.returncode == 0 else 1
        if args.action == 'disable':
            launchctl('disable', service)
            if launchctl('print', service, check=False).returncode == 0:
                launchctl('bootout', service)
            print('Schedule disabled. Archived data and reports are retained.')
            return 0
        data = configuration(hour=args.hour, minute=args.minute)
        # Do not replace a same-label job belonging to a different checkout.
        if installed.exists():
            previous = plistlib.loads(installed.read_bytes())
            if previous.get('WorkingDirectory') != str(ROOT):
                raise ValueError(f'Existing job belongs to another project: {installed}')
            write_plist(installed.with_suffix('.plist.backup'), previous)
        write_plist(prepared, data)
        if launchctl('print', service, check=False).returncode == 0:
            launchctl('bootout', service)
        write_plist(installed, data)
        launchctl('enable', service)
        launchctl('bootstrap', domain, str(installed))
        print(f'Installed: {installed}')
        print(f'Sunday and Monday at {args.hour:02d}:{args.minute:02d} Mac local time, plus login.')
        print('RunAtLoad starts a verification now. Use run_scheduled_check.py --status for its result.')
        return 0
    except (OSError, ValueError, RuntimeError, plistlib.InvalidFileException) as exc:
        print(f'Schedule setup failed: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
