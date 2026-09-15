"""History survives fresh runners; portable output contains no local paths."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from deal_history import build_history, record_week
from portable_site import build_site, export_archive, restore_archive


class PortableSiteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'local.sqlite3'
        self.archive = self.root / 'archive'
        self.site = self.root / 'site'
        pdf = b'Archived PDF test bytes'
        (self.root / 'flyer.pdf').write_bytes(pdf)
        self.payload = {
            'extraction': {'method': 'pdf'},
            'source': {'start_date': '2026-09-06', 'end_date': '2026-09-12',
                       'archive_root': str(self.root), 'snapshot_path': '/private/machine/snapshot.json',
                       'pdf': {'path': 'flyer.pdf', 'sha256': hashlib.sha256(pdf).hexdigest(), 'page_count': 1}},
            'pages': [{'page': 0, 'deals': [{'item': 'Apples', 'price': '2.99', 'unit': 'lb',
                       'details': 'Fresh', 'category': 'Produce', 'confidence': 'high', '_issues': []}]}],
        }
        record_week(self.db, self.payload)

    def test_round_trip_two_weeks_preserves_prices_categories_and_sources(self):
        second = copy.deepcopy(self.payload)
        second['source'].update(start_date='2026-09-13', end_date='2026-09-19')
        second['pages'][0]['deals'][0]['price'] = '2.49'
        record_week(self.db, second)
        self.assertEqual(export_archive(self.db, self.archive), 2)
        moved = self.root / 'fresh-runner' / 'archive'
        shutil.copytree(self.archive, moved)
        restored = self.root / 'fresh-runner' / 'history.sqlite3'
        self.assertEqual(restore_archive(moved, restored), 2)
        history = build_history(restored)
        self.assertEqual([week['extraction'] for week in history['weeks']],
                         [{'method': 'pdf', 'page_count': 1}] * 2)
        self.assertEqual([o['unit_price'] for o in history['series'][0]['observations']], [2.99, 2.49])
        self.assertEqual(history['series'][0]['category'], 'Produce')
        for p in moved.rglob('*.json'):
            self.assertNotIn(str(self.root), p.read_text())
            self.assertNotIn('/private/machine', p.read_text())
        build_site(restored, self.site)
        html = (self.site / 'index.html').read_text()
        self.assertNotIn(str(self.root), html)
        self.assertEqual(len(list((self.site / 'objects').glob('*.pdf'))), 1)
        self.assertIn('objects/' + self.payload['source']['pdf']['sha256'] + '.pdf', html)

    def test_reexport_is_stable_and_corrections_replace_only_the_active_week(self):
        export_archive(self.db, self.archive)
        before = {p.relative_to(self.archive): p.read_bytes() for p in self.archive.rglob('*') if p.is_file()}
        restored = self.root / 'restored.sqlite3'
        restore_archive(self.archive, restored)
        export_archive(restored, self.archive)
        self.assertEqual(before, {p.relative_to(self.archive): p.read_bytes() for p in self.archive.rglob('*') if p.is_file()})
        corrected = copy.deepcopy(self.payload)
        corrected['pages'][0]['deals'][0]['price'] = '1.99'
        record_week(self.db, corrected)
        export_archive(self.db, self.archive)
        restore_archive(self.archive, restored)
        self.assertEqual(build_history(restored)['series'][0]['observations'][0]['unit_price'], 1.99)
        self.assertEqual(build_history(restored)['week_count'], 1)

    def test_corrupt_archive_does_not_replace_a_good_database(self):
        export_archive(self.db, self.archive)
        before = self.db.read_bytes()
        next((self.archive / 'objects').glob('*.pdf')).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            restore_archive(self.archive, self.db)
        self.assertEqual(self.db.read_bytes(), before)

    def test_traversal_and_duplicate_weeks_are_rejected(self):
        export_archive(self.db, self.archive)
        index = json.loads((self.archive / 'archive.json').read_text())
        original = copy.deepcopy(index)
        index['weeks'][0]['path'] = '../local.sqlite3'
        (self.archive / 'archive.json').write_text(json.dumps(index))
        with self.assertRaisesRegex(ValueError, 'inside'):
            restore_archive(self.archive, self.root / 'restored.sqlite3')
        original['weeks'] *= 2
        (self.archive / 'archive.json').write_text(json.dumps(original))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            restore_archive(self.archive, self.root / 'restored.sqlite3')

    def test_hosted_site_uses_archive_urls_and_small_artifacts(self):
        result = build_site(self.db, self.site, 'https://raw.githubusercontent.com/example/repo/weekly-history/archive/')
        html = (self.site / 'index.html').read_text()
        self.assertEqual(result['weeks'], 1)
        self.assertIn('https://raw.githubusercontent.com/example/repo/weekly-history/archive/objects/', html)
        self.assertNotIn(str(self.root), html)
        self.assertEqual(list(self.site.rglob('*.pdf')), [])
        with self.assertRaisesRegex(ValueError, 'HTTPS'):
            build_site(self.db, self.site, 'javascript:alert(1)')

    def test_failed_export_or_budget_limit_preserves_previous_publication(self):
        export_archive(self.db, self.archive)
        build_site(self.db, self.site, 'https://example.org/archive/')
        archive_before = (self.archive / 'archive.json').read_bytes()
        site_before = (self.site / 'index.html').read_bytes()
        with patch('portable_site.MAX_ARCHIVE_BYTES', 1), self.assertRaisesRegex(ValueError, 'storage budget'):
            export_archive(self.db, self.archive)
        with patch('portable_site.MAX_SITE_BYTES', 1), self.assertRaisesRegex(ValueError, 'deployment budget'):
            build_site(self.db, self.site, 'https://example.org/archive/')
        self.assertEqual((self.archive / 'archive.json').read_bytes(), archive_before)
        self.assertEqual((self.site / 'index.html').read_bytes(), site_before)
        (self.root / 'flyer.pdf').write_bytes(b'bad PDF')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            export_archive(self.db, self.archive)
        self.assertEqual((self.archive / 'archive.json').read_bytes(), archive_before)

    def test_unrelated_output_directory_is_never_replaced(self):
        self.site.mkdir()
        (self.site / 'keep.txt').write_text('User data')
        with self.assertRaisesRegex(ValueError, 'unrelated'):
            build_site(self.db, self.site)
        self.assertEqual((self.site / 'keep.txt').read_text(), 'User data')


if __name__ == '__main__':
    unittest.main()
