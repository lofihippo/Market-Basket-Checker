"""The October 11 flyer includes two non-product coloring-contest pages."""
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import pymupdf

import extract_deals as ed

FIXTURE = Path(__file__).parent / 'fixtures' / '2026-10-11'


class ContestInsertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = ed.extract_document(FIXTURE / 'flyer.pdf')['pages']

    def test_fixture_matches_verified_source(self):
        manifest = json.loads((FIXTURE / 'manifest.json').read_text())
        self.assertEqual(hashlib.sha256((FIXTURE / 'flyer.pdf').read_bytes()).hexdigest(),
                         manifest['sha256'])

    def test_only_the_contest_insert_is_exempt_from_offer_requirement(self):
        self.assertEqual(len(self.pages), 10)
        for page in self.pages:
            if page['page'] in (4, 5):
                self.assertEqual(page['deals'], [])
                self.assertEqual(page['non_offer_reason'],
                                 'coloring_contest_instructions' if page['page'] == 4
                                 else 'coloring_contest_drawing')
            else:
                self.assertTrue(page['deals'], page['page'] + 1)
                self.assertNotIn('non_offer_reason', page)

    def test_single_page_selection_retains_document_context(self):
        self.assertEqual(ed.extract_document(FIXTURE / 'flyer.pdf', pages=[5])['pages'],
                         [self.pages[5]])

    def test_unknown_pages_and_mixed_product_pages_are_not_exempt(self):
        with pymupdf.open(FIXTURE / 'flyer.pdf') as doc:
            instructions, drawing = doc[4].get_text(), doc[5].get_text()
        cases = [
            ('', drawing, []),  # Drawing without its identifying contest page.
            (instructions, 'An unfamiliar page layout', []),
            (instructions, drawing + '\nApples $1.99', []),
            (instructions, drawing + '\nSave 50 cents', []),
            ('', instructions + '\nSave $1.00', []),
            ('', instructions, [{'text': 'Apples', 'size': 18, 'color': ed.BLUE}]),
        ]
        for previous, current, spans in cases:
            with self.subTest(current=current[-80:], spans=spans):
                pages = [Mock(), Mock()]
                pages[0].get_text.return_value = previous
                pages[1].get_text.return_value = current
                with patch.object(ed, 'collect_spans', return_value=spans):
                    self.assertIsNone(ed._non_offer_reason(pages, 1))


if __name__ == '__main__':
    unittest.main()
