"""Unattended retries must preserve outputs and must not hide failed checks."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import fcntl
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from check_state import build_key
from scripts import check_weekly as cli
from scripts import run_scheduled_check as runner


class ScheduledReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / 'weekly.json'
        self.cache = self.root / 'success.json'
        self.args = ['--source-dir', str(self.root / 'source'), '--json-out', str(self.output),
                     '--cache-file', str(self.cache), '--skip-unchanged', '--no-report']
        self.manifest = {'content_id': 'version-one', 'changed': True,
                         'start_date': '2026-09-13', 'end_date': '2026-09-19',
                         'pdf': {'path': 'flyer.pdf', 'page_count': 1, 'text_page_count': 1}}
        self.document = {'pages': [{'page': 0, 'deals': [{'item': 'Apples', 'price': '1.99'}]}]}

    def check(self, *, fetch_error=None, extract_error=None, key_version=1, extra=()):
        key = {'content_id': self.manifest['content_id'], 'code': key_version}
        with patch.object(cli, 'fetch_current', return_value=copy.deepcopy(self.manifest), side_effect=fetch_error) as fetch, \
             patch.object(cli, 'build_key', return_value=key), \
             patch.object(cli.ed, 'extract_document', return_value=copy.deepcopy(self.document), side_effect=extract_error) as extract, \
             patch.object(cli, 'enriched_export', side_effect=lambda value: value), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            result = cli.main([*self.args, *extra])
        return result, fetch, extract

    def test_identical_success_checks_fresh_source_but_does_not_rewrite_outputs(self):
        self.assertEqual(self.check()[0], 0)
        original = self.output.stat().st_mtime_ns
        code, fetch, extract = self.check()
        self.assertEqual(code, 0)
        fetch.assert_called_once()
        extract.assert_not_called()
        self.assertEqual(self.output.stat().st_mtime_ns, original)

    def test_changed_source_or_code_reprocesses_even_when_manifest_changed_is_false(self):
        self.assertEqual(self.check()[0], 0)
        self.manifest.update(content_id='version-two', changed=False)
        self.check()[2].assert_called_once()
        self.check(key_version=2)[2].assert_called_once()

    def test_missing_modified_output_or_broken_receipt_rebuilds(self):
        for mutation in ('missing', 'modified', 'receipt'):
            with self.subTest(mutation=mutation):
                self.check()
                if mutation == 'missing':
                    self.output.unlink()
                elif mutation == 'modified':
                    self.output.write_text('{}')
                else:
                    self.cache.write_text('not json')
                self.check()[2].assert_called_once()

    def test_expired_or_unavailable_source_cannot_reuse_previous_success(self):
        self.check()
        before = self.output.read_bytes()
        code, _, extract = self.check(fetch_error=cli.SourceError('Official flyer is expired'))
        self.assertEqual(code, 1)
        extract.assert_not_called()
        self.assertEqual(self.output.read_bytes(), before)

    def test_failed_new_source_does_not_advance_success_receipt(self):
        self.check()
        before, receipt = self.output.read_bytes(), self.cache.read_bytes()
        self.manifest['content_id'] = 'new'
        self.assertEqual(self.check(extract_error=RuntimeError('bad layout'))[0], 1)
        self.assertEqual(self.cache.read_bytes(), receipt)
        self.assertEqual(self.output.read_bytes(), before)
        self.check()[2].assert_called_once()

    def test_cache_cannot_overwrite_export_or_source_archive(self):
        for path in (self.output, self.root / 'source/current.json'):
            code, fetch, _ = self.check(extra=['--cache-file', str(path)])
            self.assertEqual(code, 1)
            fetch.assert_not_called()

    def test_fingerprint_uses_code_assets_and_config_but_not_mtime(self):
        (self.root / 'web').mkdir()
        (self.root / 'scripts').mkdir()
        for name in ('module.py', 'requirements.txt', 'web/dashboard.css', 'scripts/check_weekly.py'):
            (self.root / name).write_text('one')
        first = build_key(self.root, self.manifest, {})
        (self.root / 'module.py').touch()
        self.assertEqual(build_key(self.root, self.manifest, {}), first)
        self.assertNotEqual(build_key(self.root, self.manifest, {'setting': 1}), first)
        (self.root / 'web/dashboard.css').write_text('two')
        self.assertNotEqual(build_key(self.root, self.manifest, {}), first)
        assets = self.root / 'web/assets'
        assets.mkdir()
        logo = assets / 'logo.png'
        logo.write_bytes(b'original image bytes')
        with_logo = build_key(self.root, self.manifest, {})
        logo.write_bytes(b'updated image bytes')
        self.assertNotEqual(build_key(self.root, self.manifest, {}), with_logo)


class ScheduledRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / 'output/automation'
        self.status = self.directory / 'status.json'

    def invoke(self, code=0, output='Wrote offers.', error=None):
        with patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], code, output, ''),
                          side_effect=error) as child, redirect_stdout(io.StringIO()):
            result = runner.run(self.root)
        return result, child

    def test_success_and_unchanged_runs_save_status_and_bounded_subprocess_configuration(self):
        for output, state in [('Wrote offers.', 'updated'), ('Unchanged: verified source', 'unchanged')]:
            result, child = self.invoke(output=output)
            status = json.loads(self.status.read_text())
            self.assertEqual((result, status['state']), (0, state))
            self.assertEqual(status['last_success_at'], status['finished_at'])
            self.assertEqual(child.call_args.kwargs['cwd'], self.root.resolve())
            self.assertEqual(child.call_args.kwargs['timeout'], 300)
            self.assertIn('--skip-unchanged', child.call_args.args[0])
        self.assertIn('Starting weekly check', (self.directory / 'check.log').read_text())

    def test_failures_and_timeout_retain_last_success_and_release_lock(self):
        self.invoke()
        last_success = json.loads(self.status.read_text())['last_success_at']
        for error in (None, subprocess.TimeoutExpired(['checker'], 300), OSError('cannot start')):
            with self.subTest(error=error):
                self.assertEqual(self.invoke(code=1, output='Expired flyer', error=error)[0], 1)
                status = json.loads(self.status.read_text())
                self.assertEqual(status['state'], 'failed')
                self.assertEqual(status['last_success_at'], last_success)
        self.assertEqual(self.invoke()[0], 0)

    def test_concurrent_invocation_skips_without_touching_active_status(self):
        self.directory.mkdir(parents=True)
        self.status.write_text('{"state":"running"}')
        before = self.status.read_bytes()
        with (self.directory / 'check.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            code, child = self.invoke()
            self.assertEqual(code, 0)
            child.assert_not_called()
            self.assertEqual(self.status.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
