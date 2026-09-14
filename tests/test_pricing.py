"""Price regressions include native small glyphs and explicit offer variants."""
from pathlib import Path
import unittest

import pymupdf

from pricing import inline_offers, offer_terms, price_runs, price_string, price_to_number


FIXTURE = Path(__file__).parent / "fixtures" / "2026-09-06" / "flyer.pdf"


def glyph(text, x=0, size=30, y=0):
    return {"text": text, "bbox": (x, y, x + max(5, len(text)*size/2), y+size),
            "size": size, "color": 0xED2925, "font": "PriceFont"}


def region(page, bounds):
    x0, y0, x1, y1 = bounds
    return [s for b in page.get_text("dict")["blocks"] if b.get("type") == 0
            for line in b["lines"] for s in line["spans"]
            if s["text"].strip()
            and x0 <= (s["bbox"][0]+s["bbox"][2])/2 <= x1
            and y0 <= (s["bbox"][1]+s["bbox"][3])/2 <= y1]


class PriceInterpretationTests(unittest.TestCase):
    def test_currency_and_multibuy_are_distinct(self):
        cases = [([glyph("$4.99")], "4.99"),
                 ([glyph("$"), glyph("4", 10), glyph("99", 25, 15)], "4.99"),
                 ([glyph("2$5")], "2 for $5"),
                 ([glyph("2"), glyph("$", 15, 15), glyph("5", 25)], "2 for $5"),
                 ([glyph("2 for $5.50")], "2 for $5.50"),
                 ([glyph("99¢")], "99¢")]
        for spans, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(price_string(spans)[0], expected)

    def test_raised_zero_cents_and_separate_dollar_digits(self):
        self.assertEqual(price_string([glyph("4"), glyph("00", 16, 15)])[0], "4.00")
        self.assertEqual(price_string([glyph("1"), glyph("2", 16),
                                      glyph("99", 32, 15)])[0], "12.99")

    def test_offer_terms_preserve_total_quantity_and_arithmetic_rate(self):
        self.assertEqual(offer_terms("2 for $5"),
                         {"quantity": 2, "amount": 5.0, "unit_price": 2.5})
        self.assertEqual(price_to_number("2 for $5"), 5.0)
        self.assertEqual(offer_terms("99¢"),
                         {"quantity": 1, "amount": .99, "unit_price": .99})
        self.assertAlmostEqual(offer_terms("3 for $10")["unit_price"], 10/3)
        for value in (None, "", "invalid", "$NaN", "0 for $5", "2 for $5..0"):
            with self.subTest(value=value):
                self.assertEqual(offer_terms(value),
                                 {"quantity": None, "amount": None, "unit_price": None})

    def test_unit_normalization_and_stacked_runs(self):
        spans = [glyph("4"), glyph("99", 15, 15),
                 glyph("lb.", 20, 9, 28), glyph("2", 0, 30, 80),
                 glyph("49", 15, 15, 80)]
        runs = price_runs(spans)
        self.assertEqual([price_string(run["spans"]) for run in runs],
                         [("4.99", "lb"), ("2.49", None)])
        self.assertTrue(all(any(s is original for original in spans)
                            for run in runs for s in run["spans"]))

    def test_inline_savings_and_coupons_are_not_sale_offers(self):
        spans = [glyph("Save $1.00"), glyph("Instant Coupon $2.00"),
                 glyph("Sale Price $9.99"), glyph("•Half Pie 13 oz. $5.19 Save $0.50")]
        offers = inline_offers(spans)
        self.assertEqual([(o["label"], o["price"]) for o in offers],
                         [("Half Pie 13 oz.", "5.19")])

    def test_inline_multibuy_variants_preserve_required_quantity(self):
        spans = [glyph("•Dairy Free 2 for $4"), glyph("50 oz. 2 for $7"),
                 glyph("*2 for $3 plant-based, 5.3 oz.")]
        offers = inline_offers(spans)
        self.assertEqual([(o["label"], o["price"]) for o in offers],
                         [("Dairy Free", "2 for $4"), ("50 oz.", "2 for $7"),
                          ("plant-based, 5.3 oz.", "2 for $3")])
        self.assertTrue(all(offer_terms(o["price"])["quantity"] == 2 for o in offers))


class PriceFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = pymupdf.open(FIXTURE)

    @classmethod
    def tearDownClass(cls):
        cls.document.close()

    def test_small_bakery_prices_and_overprinted_blueberry_price(self):
        cases = [((20, 230, 190, 312), "5.49"),
                 ((525, 230, 700, 312), "2.49"),
                 ((525, 344, 700, 414), "7.79")]
        for bounds, expected in cases:
            with self.subTest(expected=expected):
                spans = region(self.document[7], bounds)
                self.assertEqual([price_string(r["spans"])[0] for r in price_runs(spans)],
                                 [expected])

    def test_representative_existing_cover_prices_and_units(self):
        cases = [((360, 172, 692, 315), "99¢", "lb"),
                 ((360, 319, 692, 460), "4.99", "lb"),
                 ((28, 900, 359, 1029), "2 for $3", None)]
        for bounds, expected, unit in cases:
            with self.subTest(expected=expected):
                runs = price_runs(region(self.document[0], bounds))
                self.assertEqual([price_string(r["spans"]) for r in runs], [(expected, unit)])

    def test_coke_bottle_volume_is_not_a_second_price(self):
        spans = region(self.document[0], (359, 900, 692, 1029))
        runs = price_runs(spans)
        self.assertEqual([price_string(r["spans"])[0] for r in runs], ["99¢"])
        self.assertNotIn("1.25", [s["text"].strip() for r in runs for s in r["spans"]])

    def test_popcorn_and_chicken_explicit_variant_prices(self):
        offers = inline_offers(region(self.document[7], (245, 864, 697, 982)))
        self.assertEqual({(o["label"], o["price"], o["unit"]) for o in offers},
                         {("5 oz.", "1.99", "ea"), ("14 oz.", "4.99", "ea"),
                          ("4 Piece", "4.99", None)})
        self.assertTrue(all(o["price_n"] is not None and len(o["_bbox"]) == 4 for o in offers))

    def test_half_pie_and_shrimp_package_offers(self):
        pie = inline_offers(region(self.document[7], (525, 344, 700, 414)))
        self.assertEqual([(o["label"], o["price"]) for o in pie], [("Half Pie 13 oz.", "5.19")])
        spans = region(self.document[0], (250, 604, 470, 747))
        shrimp = inline_offers(spans)
        self.assertEqual([(o["label"], o["price"]) for o in shrimp], [("2-LB. BAG", "21.89")])
        self.assertNotIn("21.89", [price_string(r["spans"])[0] for r in price_runs(spans)])

    def test_wrapped_variant_labels_stay_with_their_inline_price(self):
        coffee = inline_offers(region(self.document[4], (318, 530, 363, 549)))
        butter = inline_offers(region(self.document[4], (336, 440, 379, 459)))
        self.assertEqual([(o["label"], o["price"]) for o in coffee],
                         [("Iced Coffee 50 oz.", "2 for $7")])
        self.assertEqual([(o["label"], o["price"]) for o in butter],
                         [("Quarters & Spray", "1.99")])


if __name__ == "__main__":
    unittest.main()
