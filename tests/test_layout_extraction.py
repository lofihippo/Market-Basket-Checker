"""Product-boundary regressions checked against the dated flyer pages.

These check title coverage and association, not complete field accuracy.
Small bakery price typography, units, and detail normalization are separate.
"""
from pathlib import Path
import unittest

import pymupdf

import extract_deals as ed
from layout import column_bounds, crosses_divider

FIXTURE = Path(__file__).parent / "fixtures" / "2026-09-06" / "flyer.pdf"


class FlyerBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with pymupdf.open(FIXTURE) as doc:
            cls.pages = {i: ed.extract_page(doc[i]) for i in (0, 1, 2, 3, 4, 5, 6, 7)}

    def assert_offer(self, page, item, price):
        matches = [d for d in self.pages[page] if d["item"] == item and d["price"] == price]
        self.assertEqual(len(matches), 1, (page + 1, item, price, matches))
        self.assertIn("_bbox", matches[0])

    def test_all_fifteen_meat_specials_survive_with_their_prices(self):
        expected = [
            ("SLICED PEPPERONI", "1.99"), ("BONELESS SPIRAL HAM", "4.49"),
            ("ALL BEEF FRANKS", "11.49"), ("ALL BEEF FRANKS", "4.99"),
            ("HICKORY SMOKED BACON", "4.99"), ("POLSKA KIELBASA", "8.99"),
            ("BABY BACK PORK RIBS", "14.99"), ("BABY BACK PORK RIBS", "7.99"),
            ("LI’L SMOKIES COCKTAIL SAUSAGE", "2 for $7"),
            ("BREAKFAST SAUSAGE", "4.49"), ("PULLED CHICKEN OR PULLED PORK", "4.99"),
            ("GENOA SALAMI OR PEPPERONI", "4.99"), ("BONELESS HAM STEAKS", "2 for $5"),
            ("HAM PORTIONS", "1.69"), ("LUNCHMAKERS", "1.19"),
        ]
        for item, price in expected:
            with self.subTest(item=item, price=price):
                self.assert_offer(1, item, price)

    def test_all_thirteen_bakery_titles_survive(self):
        expected = {
            "Delicious Pumpkin Muffins", "Pumpkin Whoopie Pies", "“Not Just Oatmeal” Cookies",
            "Cake Slices", "Bundt Cakes", "Delicious Dinner Cakes", "Blueberry Pie",
            "Blueberry Muffins", "Chocolate Croissants", "Delicious Fudge", "Saloio Bread",
            "Honey Sunflower Tuscan Bread", "5 Seed Tuscan Bread",
        }
        bakery = [d for d in self.pages[7] if d.get("_bbox", [0, 1000])[1] < 630]
        self.assertEqual({d["item"] for d in bakery}, expected)
        self.assertEqual(len(bakery), 13)
        self.assert_offer(7, "Delicious Pumpkin Muffins", "3.99")
        self.assert_offer(7, "Chocolate Croissants", "4.99")

    def test_beer_and_wine_rows_do_not_merge(self):
        expected = [
            ("Michelob Ultra", "19.99"), ("Line 39 Wines", "8.99"),
            ("•Budweiser •Bud Light •Miller Lite •Coors Light", "19.99"),
            ("•Miller Lite •Coors Light", "14.99"),
            ("•Sun Cruiser •Nutrl •High Noon", "22.99"),
            ("Coppola Diamond Series", "11.99"), ("Cavit Wines", "9.99"),
            ("Wente Wines", "11.99"), ("Casillero del Diablo", "6.99"),
        ]
        for item, price in expected:
            with self.subTest(item=item):
                self.assert_offer(5, item, price)
        self.assertFalse(any("Michelob" in d["item"] and "Wines" in d["item"]
                             for d in self.pages[5]))

    def test_dixie_and_dog_food_stay_in_their_columns(self):
        self.assert_offer(6, "Dixie Plates", "2 for $5")
        self.assert_offer(6, "Kibbles ’n Bits Dog Food", "5.99")
        self.assertFalse(any("Dixie" in d["item"] and "Dog Food" in d["item"]
                             for d in self.pages[6]))

    def test_stacked_seafood_products_are_separate(self):
        self.assert_offer(3, "Pacific Smelts", "4.99")
        self.assert_offer(3, "Halal Quail", "14.99")
        self.assert_offer(3, "More Please", "5.59")
        self.assert_offer(3, "White Fish Salad", "4.99")
        self.assert_offer(3, "•Herring in Wine •Herring Cream •Herring In Dill", "4.99")

    def test_distinct_regions_keep_same_generic_title(self):
        self.assert_offer(2, "Boneless Chicken Breast", "3.99")
        self.assert_offer(2, "Boneless Chicken Breast", "6.99")
        self.assert_offer(2, "Turkey Burgers", "8.49")
        self.assert_offer(2, "Turkey Burgers", "9.49")

    def test_cover_does_not_gain_header_offers(self):
        self.assertEqual(len(self.pages[0]), 25)
        self.assertFalse(any("your Dollar" in d["item"] for d in self.pages[0]))
        self.assert_offer(0, "Drumsticks or Thighs", "99¢")
        self.assert_offer(0, "Bottom Round Roast", "4.99")
        self.assert_offer(0, "Teriyaki Chicken Roll", "6.99")
        self.assert_offer(0, "Salmon & Tuna Nigiri Combo Roll", "12.99")

    def test_blue_pack_labels_remain_in_product_titles(self):
        self.assert_offer(4, "Pepsi 12 Pack", "2 for $14")
        self.assert_offer(4, "Pure Life Water 24 Pack", "3 for $10")
        self.assert_offer(7, "Bud Light 30 Pack", "25.99")


class DividerTests(unittest.TestCase):
    def test_column_coordinates_are_derived_from_rules(self):
        page = pymupdf.Rect(0, 0, 720, 1512)
        rules = [pymupdf.Rect(118, 880, 119, 971), pymupdf.Rect(213, 880, 214, 971)]
        dixie = pymupdf.Rect(70, 882, 118, 910)
        dog_food = pymupdf.Rect(127, 883, 215, 910)
        self.assertTrue(crosses_divider(dixie, dog_food, rules))
        self.assertEqual(column_bounds(dixie, rules, page), (0, 118))
        self.assertEqual(column_bounds(dog_food, rules, page), (119, 213))


if __name__ == "__main__":
    unittest.main()
