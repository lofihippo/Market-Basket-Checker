"""Title-style regressions grounded in the archived weekly flyer."""
from pathlib import Path
import unittest

import pymupdf

from name_styles import product_name_spans


FIXTURE = Path(__file__).parent / "fixtures" / "2026-09-06" / "flyer.pdf"


def page_spans(page):
    return [span for block in page.get_text("dict")["blocks"]
            if block.get("type") == 0
            for line in block["lines"] for span in line["spans"]
            if span["text"].strip()]


def region(spans, bounds):
    x0, y0, x1, y1 = bounds
    return [span for span in spans
            if x0 <= (span["bbox"][0] + span["bbox"][2]) / 2 <= x1
            and y0 <= (span["bbox"][1] + span["bbox"][3]) / 2 <= y1]


class NameStyleFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with pymupdf.open(FIXTURE) as document:
            cls.pages = [page_spans(page) for page in document]

    def test_white_meat_titles_exclude_large_package_sizes(self):
        cases = [
            ((24, 867, 357, 990), {"SLICED", "PEPPERONI"}),
            ((361, 867, 695, 990), {"BONELESS", "SPIRAL HAM"}),
            ((529, 1344, 695, 1460), {"LUNCHMAKERS"}),
            ((24, 1107, 246, 1223), {"POLSKA", "KIELBASA"}),
            ((474, 1107, 695, 1223), {"BABY", "BACK", "PORK", "RIBS"}),
            ((24, 1226, 246, 1342), {"LI’L", "SMOKIES", "COCKTAIL", "SAUSAGE"}),
            ((474, 1226, 695, 1342), {"PULLED CHICKEN", "OR PULLED PORK"}),
            ((24, 1345, 188, 1460), {"GENOA", "SALAMI", "OR", "PEPPERONI"}),
        ]
        for bounds, expected in cases:
            spans = region(self.pages[1], bounds)
            with self.subTest(expected=expected):
                selected = product_name_spans(spans, allow_white=True)
                self.assertEqual({s["text"].strip() for s in selected}, expected)
                self.assertFalse(product_name_spans(spans))
                self.assertTrue(all(any(s is original for original in spans)
                                    for s in selected))

    def test_navy_meat_titles_exclude_small_labels_and_frozen_badge(self):
        cases = [
            ((24, 993, 245, 1105), {"ALL", "BEEF", "FRANKS"}),
            ((249, 993, 470, 1105), {"ALL", "BEEF", "FRANKS"}),
            ((474, 993, 695, 1105), {"HICKORY", "SMOKED", "BACON"}),
            ((249, 1107, 470, 1223), {"BABY", "BACK", "PORK", "RIBS"}),
            ((249, 1225, 470, 1342), {"BREAKFAST", "SAUSAGE"}),
            ((192, 1344, 358, 1460), {"BONELESS", "HAM", "STEAKS"}),
            ((361, 1344, 527, 1460), {"HAM", "PORTIONS"}),
        ]
        for bounds, expected in cases:
            with self.subTest(expected=expected):
                selected = product_name_spans(region(self.pages[1], bounds), True)
                self.assertEqual({s["text"].strip() for s in selected}, expected)

    def test_all_thirteen_bakery_offers_have_selected_name_text(self):
        selected = {s["text"].strip() for s in product_name_spans(self.pages[7])}
        expected = {
            "Pumpkin Muffins", "Pumpkin Whoopie Pies", "Bundt Cakes",
            "Blueberry Muffins", "Saloio Bread", "Cookies", "Dinner Cakes",
            "Croissants", "Tuscan Bread", "Cake Slices", "Blueberry Pie",
            "Delicious Fudge", "5 Seed Tuscan Bread",
        }
        self.assertTrue(expected <= selected, expected - selected)

    def test_cover_blue_titles_do_not_gain_white_badge_labels(self):
        spans = region(self.pages[0], (28, 462, 249, 604))
        selected = product_name_spans(spans, True)
        self.assertEqual([s["text"].strip() for s in selected], ["Turkey", "Breast"])

    def test_white_headers_prices_and_badges_are_not_titles(self):
        bad_text = {"PRODUCE", "MEAT SPECIALS", "BOUQUETS & POTTED PLANTS",
                    "Save 50¢", "7 oz. PKG.", "2-3.1 oz. PKG.", "9", "$", "for"}
        for spans in self.pages:
            for span in spans:
                if span["color"] == 0xFFFFFF and span["text"].strip() in bad_text:
                    with self.subTest(text=span["text"]):
                        self.assertEqual(product_name_spans([span], True), [])

    def test_white_meat_selection_also_works_without_optional_font(self):
        spans = region(self.pages[1], (24, 867, 357, 990))
        spans = [{k: v for k, v in s.items() if k != "font"} for s in spans]
        self.assertEqual({s["text"].strip() for s in product_name_spans(spans, True)},
                         {"SLICED", "PEPPERONI"})


if __name__ == "__main__":
    unittest.main()
