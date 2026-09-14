"""Report pipeline checks use synthetic prices only inside isolated tests."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from deal_history import record_week
from reporting import dashboard_data, enriched_export, read_catalog


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'history.sqlite3'
        self.pdf = self.root / 'flyer.pdf'
        self.pdf.write_bytes(b'source link fixture')
        self.payload = {
            'source': {'start_date': '2026-09-06', 'end_date': '2026-09-12',
                       'archive_root': str(self.root),
                       'pdf': {'path': 'flyer.pdf', 'sha256': 'a' * 64, 'page_count': 1}},
            'pages': [{'page': 0, 'deals': [{'item': 'Test Apples', 'price': '2.99',
                       'unit': 'lb', 'details': 'Fresh', 'package_sizes': [],
                       'confidence': 'high', '_issues': []}]}],
        }

    def test_real_history_assembly_preserves_dates_comparable_prices_and_pdf_link(self):
        record_week(self.db, enriched_export(self.payload))
        second = copy.deepcopy(self.payload)
        second['source'].update(start_date='2026-09-13', end_date='2026-09-19')
        second['pages'][0]['deals'][0]['price'] = '2.49'
        record_week(self.db, enriched_export(second))
        data = dashboard_data(self.db, self.root / 'reports' / 'report.html')
        self.assertEqual(data['week_count'], 2)
        self.assertEqual(data['weeks'][0]['source']['pdf_href'], '../flyer.pdf')
        self.assertEqual([p['amount'] for p in data['series'][0]['observations']], [2.99, 2.49])
        self.assertEqual(data['weeks'][1]['offers'][0]['category'], 'Produce')
        self.assertEqual(len(data['seasonality']['months']), 12)

    def test_catalog_must_match_archived_checksum(self):
        raw = json.dumps({'products': [{'name': 'Test Apples', 'departments': [{'slug': 'produce'}]}]}).encode()
        (self.root / 'api.json').write_bytes(raw)
        self.payload['source']['api'] = {'path': 'api.json', 'sha256': hashlib.sha256(raw).hexdigest()}
        self.assertEqual(len(read_catalog(self.payload)), 1)
        (self.root / 'api.json').write_text('{"products": []}')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            read_catalog(self.payload)

    def test_missing_source_files_do_not_create_unsafe_links(self):
        self.pdf.unlink()
        self.payload['source']['pdf']['url'] = 'javascript:alert(1)'
        record_week(self.db, self.payload)
        data = dashboard_data(self.db, self.root / 'report.html')
        self.assertIsNone(data['weeks'][0]['source']['pdf_href'])


if __name__ == '__main__':
    unittest.main()
