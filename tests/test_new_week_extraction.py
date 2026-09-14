"""Selected visual regressions from the September 13–19 flyer.

This is a second layout fixture, not a complete recall benchmark. In
particular, the image-only wellness-shot banner needs a separate text source.
"""
import hashlib
import json
from pathlib import Path
import unittest

import extract_deals as ed

FIXTURE_DIR = Path(__file__).parent / 'fixtures' / '2026-09-13'


class NewWeekExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages = ed.extract_document(FIXTURE_DIR / 'flyer.pdf')['pages']

    def offer(self, page, title):
        matches = [d for d in self.pages[page]['deals'] if d['item'] == title]
        self.assertEqual(len(matches), 1, (page + 1, title, matches))
        return matches[0]

    def test_fixture_hash_is_the_verified_second_week(self):
        manifest = json.loads((FIXTURE_DIR / 'manifest.json').read_text())
        actual = hashlib.sha256((FIXTURE_DIR / 'flyer.pdf').read_bytes()).hexdigest()
        self.assertEqual(actual, manifest['sha256'])
        self.assertEqual(manifest['sale_start'], '2026-09-13')

    def test_all_eight_pages_have_native_text_offers(self):
        self.assertEqual(len(self.pages), 8)
        for page in self.pages:
            self.assertTrue(page['deals'], f"Empty page {page['page'] + 1}")

    def test_produce_and_flower_titles_with_the_new_color(self):
        expected = {
            'Zespri Sungold Kiwi Fruit': '4.49',
            'Sweet Blackberries': '2 for $5',
            'Golden Berries': '2 for $5',
            'Fresh Express Chopped Kit': '2 for $5',
            'Green Giant Cut Vegetables': '2 for $5',
            'Little Leaf Salads Kits': '3.99',
            'White Potatoes': '2.49',
            'Pero Stringless Sugar Snap Peas': '3.99',
            'Butternut Squash': '79¢',
            'Baby Potatoes': '2 for $5',
            'Stuffed Mushrooms & Jalapeño Peppers': '4.49',
            'Jumbo Pumpkins': '9.99',
            'Fall Heather': '5.99',
            'Fall Lily Bouquet': '15.99',
            'Premium Bromeliad': '15.99',
            'Hardy Mums': '5.99',
        }
        for title, price in expected.items():
            with self.subTest(title=title):
                self.assertEqual(self.offer(1, title)['price'], price)
        self.assertEqual(self.offer(1, 'Butternut Squash')['unit'], 'lb')
        self.assertEqual(self.offer(1, 'Jumbo Pumpkins')['unit'], 'ea')
        self.assertFalse(any('Make Your Own Pizza' in d['item']
                             for d in self.pages[1]['deals']))

    def test_one_span_price_and_savings_belong_to_pizza_cheese(self):
        cheese = self.offer(1, 'Market Basket Pizza Cheese')
        sauce = self.offer(1, 'Sal’s Pizza Sauce')
        self.assertEqual((cheese['price'], cheese['savings']), ('1.99', 'Save 50¢'))
        self.assertEqual(sauce['price'], '4.99')
        self.assertEqual(cheese['package_sizes'], ['8 oz.'])
        self.assertIn('$1.99', cheese['_source_text'])
        self.assertNotIn('$4.99', cheese['_source_text'])
        self.assertEqual(cheese['_issues'], [])

    def test_beer_prices_beside_titles_do_not_take_the_wine_prices_below(self):
        for title, price in [('Long Drink', '19.99'), ('•Modelo •Pacifico', '14.99'),
                             ('Line 39 Wines', '8.99'), ('Casillero del Diablo', '6.99')]:
            with self.subTest(title=title):
                deal = self.offer(5, title)
                self.assertEqual(deal['price'], price)
                self.assertNotIn('shared_price_or_title', deal['_issues'])

    def test_qualifiers_and_small_cap_fragments_do_not_duplicate_offers(self):
        roaster = self.offer(2, 'Oven Ready Roaster')
        self.assertEqual(roaster['price'], '10.99')
        self.assertIn('In Cooking Bag', roaster['details'])
        self.assertEqual(roaster['savings'], 'Save $1.50')
        for title, qualifiers in [("Beck’s Seafood Dips", ['•Jalapeño', '•Lobster', '•Crab']),
                                  ('Imitation Crab', ['•Salad', '•Chunk']),
                                  ('YANKEE TRADER', ['•Crab Cakes', '•Clam Cakes'])]:
            deal = self.offer(3, title)
            self.assertEqual(deal['price'], '2.99')
            for qualifier in qualifiers:
                self.assertIn(qualifier, deal['details'])
        false_titles = {'In Cooking Bag', '•Salad •Chunk', '•Jalapeño •Lobster •Crab',
                        'YANKEE', 'TRADER'}
        self.assertFalse(false_titles & {d['item'] for p in self.pages for d in p['deals']})

    def test_second_week_has_no_shared_principal_price_spans(self):
        shared = [(p['page'] + 1, d['item']) for p in self.pages for d in p['deals']
                  if 'shared_price_or_title' in d['_issues']]
        self.assertEqual(shared, [])


if __name__ == '__main__':
    unittest.main()
