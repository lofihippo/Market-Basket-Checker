"""Offer-field integration checks against the archived, visually checked flyer."""
from pathlib import Path
import unittest

import pymupdf

import extract_deals as ed
from offer_fields import extract_fields
from offer_regions import assign_fields, split_cell_regions

FIXTURE = Path(__file__).parent / "fixtures" / "2026-09-06" / "flyer.pdf"


class OfferExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with pymupdf.open(FIXTURE) as doc:
            cls.pages = {i: ed.extract_page(doc[i]) for i in (0, 4, 7)}

    def offer(self, page, name):
        matches = [d for d in self.pages[page] if d['item'] == name]
        self.assertEqual(len(matches), 1, name)
        return matches[0]

    def test_sale_units_savings_basis_and_qualifiers_are_separate(self):
        chicken = self.offer(0, 'Drumsticks or Thighs')
        self.assertEqual((chicken['price'], chicken['unit'], chicken['savings']),
                         ('99¢', 'lb', 'Save 50¢/lb'))
        roast = self.offer(0, 'Bottom Round Roast')
        self.assertEqual((roast['unit'], roast['savings'], roast['details']),
                         ('lb', 'Save $2.00/lb', 'Cut Fresh Daily'))
        self.assertEqual(self.offer(0, 'Teriyaki Chicken Roll')['unit'], 'pkg')
        self.assertEqual(self.offer(0, 'Pizza')['unit'], 'ea')
        roses = self.offer(0, 'One Dozen Roses')
        self.assertIsNone(roses['unit'])
        self.assertEqual(roses['details'], 'Assorted Colors')

    def test_shrimp_package_price_belongs_to_shrimp_not_sauce(self):
        sauce = self.offer(0, 'Gold’s Horseradish or Cocktail Sauce')
        shrimp = self.offer(0, 'Quality Cooked Shrimp')
        self.assertNotIn('2-LB', sauce['details'])
        self.assertEqual(len(sauce['prices']), 1)
        self.assertIn('2-LB. BAG', shrimp['package_sizes'])
        self.assertIn('FROZEN', shrimp['details'])
        self.assertEqual([(p['label'], p['price']) for p in shrimp['prices']],
                         [(None, '10.99'), ('2-LB. BAG', '21.89')])

    def test_bakery_glyphs_do_not_consume_pack_or_variety_counts(self):
        whoopie = self.offer(7, 'Pumpkin Whoopie Pies')
        self.assertEqual(whoopie['price'], '5.49')
        self.assertIn('6 PACK', whoopie['package_sizes'])
        cake = self.offer(7, 'Cake Slices')
        self.assertEqual(cake['price'], '2.49')
        self.assertIn('7 Varieties', cake['details'])
        pie = self.offer(7, 'Blueberry Pie')
        self.assertEqual(pie['price'], '7.79')
        self.assertEqual(pie['prices'][1]['price'], '5.19')
        self.assertEqual(pie['prices'][1]['label'], 'Half Pie 13 oz.')
        self.assertIn('overprinted_price_text', pie['_issues'])
        self.assertEqual(pie['confidence'], 'medium')

    def test_explicit_variants_survive_without_inventing_one_popcorn_price(self):
        popcorn = self.offer(7, 'Freshly Popped Popcorn')
        self.assertIsNone(popcorn['price'])
        self.assertIsNone(popcorn['amount'])
        self.assertEqual([(p['label'], p['price'], p['unit']) for p in popcorn['prices']],
                         [('5 oz.', '1.99', 'ea'), ('14 oz.', '4.99', 'ea')])
        self.assertNotIn('missing_or_unparsed_price', popcorn['_issues'])
        chicken = self.offer(7, 'Fried Chicken')
        self.assertEqual(chicken['price'], '7.99')
        self.assertIn('8 Piece', chicken['package_sizes'])
        self.assertEqual(chicken['prices'][1]['label'], '4 Piece')
        self.assertEqual(chicken['prices'][1]['price'], '4.99')

    def test_multibuy_variants_keep_the_advertised_quantity(self):
        yogurt = self.offer(4, 'Icelandic Provisions Skyr Yogurt')
        self.assertEqual((yogurt['quantity'], yogurt['amount'], yogurt['unit_price']),
                         (5, 5.0, 1.0))
        variant = yogurt['prices'][1]
        self.assertEqual((variant['price'], variant['quantity'], variant['unit_price']),
                         ('2 for $4', 2, 2.0))
        coffee = self.offer(4, 'Coffee-mate Coffee Creamer')
        self.assertEqual(coffee['prices'][1]['price'], '2 for $7')

    def test_table_sizes_and_savings_stay_with_their_product(self):
        eggs = self.offer(4, 'Pete & Gerry’s Pasture Raised Large Eggs')
        self.assertIn('DOZEN', eggs['package_sizes'])
        self.assertNotIn('2-LB', eggs['details'])
        polar = self.offer(4, 'Polar Seltzer')
        self.assertEqual(polar['savings'], 'Save $1.76')
        coke = self.offer(0, 'Coke')
        self.assertIn('1.25', coke['details'])
        self.assertIn('1.25 LTR.', coke['package_sizes'])
        self.assertEqual(len(coke['prices']), 1)
        self.assertNotIn('unassigned_price_region', coke['_issues'])

    def test_every_offer_and_price_has_source_evidence(self):
        for page, offers in self.pages.items():
            for offer in offers:
                with self.subTest(page=page, item=offer['item']):
                    self.assertEqual(offer['page'], page)
                    self.assertEqual(len(offer['_bbox']), 4)
                    self.assertTrue(offer['_source_text'])
                    for price in offer['prices']:
                        self.assertEqual(len(price['_bbox']), 4)
                        self.assertGreater(price['amount'], 0)


def span(text, box):
    return {'text': text, 'bbox': pymupdf.Rect(box), 'size': 12,
            'color': 0x231F20}


def run(s):
    b = s['bbox']
    return {'spans': [s], 'x0': b.x0, 'x1': b.x1,
            'y': (b.y0 + b.y1) / 2, 'size': s['size']}


class OwnershipTests(unittest.TestCase):
    def test_price_attached_units_are_not_discarded_as_price_glyphs(self):
        price = span('4.99', (0, 0, 30, 30))
        unit = span('lb.', (30, 20, 45, 30))
        primary = run(price)
        primary['spans'].append(unit)
        fields = extract_fields([price, unit], price_runs=[primary])
        self.assertEqual(fields['unit'], 'lb')
        self.assertEqual(fields['details'], '')

    def test_adjacent_offers_use_facing_edges_and_keep_exclusive_ownership(self):
        left = span('1.99', (312, 714, 342, 745))
        right = span('10.99', (403, 696, 463, 754))
        bag = span('2-LB. BAG', (356, 708, 396, 718))
        regions = split_cell_regions([left, right, bag], [run(left), run(right)],
                                     pymupdf.Rect(250, 604, 471, 760))
        self.assertNotIn(bag, regions[0][1])
        self.assertIn(bag, regions[1][1])
        assigned = [id(s) for _, group in regions for s in group]
        self.assertEqual(len(assigned), len(set(assigned)))

    def test_ambiguous_detail_ownership_is_flagged_and_never_duplicated(self):
        left, right = span('2.99', (0, 50, 20, 80)), span('3.99', (80, 50, 100, 80))
        detail = span('12 oz.', (45, 50, 55, 60))
        contexts = [{'group': [], 'run': run(s), 'lane': (0, 100),
                     'bbox': pymupdf.Rect(0, 0, 100, 100)} for s in (left, right)]
        owned, issues = assign_fields([left, right, detail], contexts)
        self.assertEqual(sum(detail in group for group in owned), 1)
        self.assertIn('ambiguous_detail_ownership', issues[0])
        self.assertEqual(ed.score_confidence({'item': 'Example', 'price': '2.99',
                                              'price_n': 2.99, '_issues': issues[0]}), 'medium')


if __name__ == '__main__':
    unittest.main()
