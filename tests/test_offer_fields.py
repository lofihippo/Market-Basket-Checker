"""Field ownership tests use controlled spans with archived flyer geometry."""
import unittest

from offer_fields import extract_fields


def span(text, box, size=12, color=0x231F20):
    return {"text": text, "bbox": box, "size": size, "color": color}


def run(*spans):
    return {"x0": min(s["bbox"][0] for s in spans),
            "x1": max(s["bbox"][2] for s in spans),
            "y": sum((s["bbox"][1] + s["bbox"][3]) / 2 for s in spans) / len(spans),
            "size": max(s["size"] for s in spans), "spans": spans}


class OfferFieldTests(unittest.TestCase):
    def test_roast_separates_saving_basis_and_sale_unit(self):
        title = span("Bottom Round Roast", (516, 327, 686, 381), 25, 0x1B4491)
        price = span("4.99", (583, 393, 684, 475), 82, 0xED2925)
        saving = span("Save $2.00", (599, 381, 666, 395), 14)
        save_unit = span("lb.", (666, 383, 679, 394), 11, 0xED1C2B)
        sale_unit = span("lb.", (650, 441, 677, 459), 18)
        fields = extract_fields([title, price, saving, save_unit, sale_unit],
                                [title], [run(price)])
        self.assertEqual(fields, {"details": "", "unit": "lb", "savings": "Save $2.00/lb",
                                  "package_sizes": [], "_issues": []})

    def test_chicken_cents_saving_unit_does_not_invent_sale_unit(self):
        price = span("99¢", (586, 250, 675, 328), 78, 0xED1C2B)
        saving = span("Save 50¢", (593, 235, 651, 249), 14)
        label = span("lb.", (651, 237, 664, 247), 10, 0xED1C2B)
        fields = extract_fields([price, saving, label], price_runs=[run(price)])
        self.assertEqual(fields["savings"], "Save 50¢/lb")
        self.assertIsNone(fields["unit"])

    def test_sushi_package_unit_is_not_package_size(self):
        price = span("6.99", (100, 100, 145, 140), 40)
        fields = extract_fields([price, span("PKG.", (130, 135, 155, 146))],
                                price_runs=[run(price)])
        self.assertEqual(fields["unit"], "pkg")
        self.assertEqual(fields["package_sizes"], [])

    def test_flowers_preserve_red_qualifier_without_invented_unit(self):
        title = span("One Dozen Roses", (106, 773, 246, 825), 27)
        price = span("6.99", (169, 839, 241, 909), 70)
        spans = [title, price, span("Assorted", (36, 775, 94, 792), color=0xED1C2B),
                 span("Colors", (45, 787, 87, 803), color=0xED1C2B)]
        fields = extract_fields(spans, [title], [run(price)])
        self.assertEqual(fields["details"], "Assorted Colors")
        self.assertIsNone(fields["unit"])

    def test_bakery_measurements_keep_every_color_and_white_savings(self):
        blue_size = span("12 oz.", (443, 171, 475, 183), color=0x1B4491)
        spans = [span("4 PACK", (441, 160, 481, 172), color=0xED2925), blue_size,
                 span("Save 50¢", (346, 143, 394, 156), color=0xFFFFFF)]
        fields = extract_fields(spans, title_spans=[blue_size])
        self.assertEqual(fields["package_sizes"], ["4 PACK", "12 oz."])
        self.assertEqual(fields["savings"], "Save 50¢")
        self.assertIsNone(fields["unit"])

    def test_split_count_labels_survive_bare_price_removal(self):
        spans = [span("6", (145, 497, 153, 506), 9),
                 span("PACK", (137, 505, 159, 514), 9),
                 span("7", (628, 275, 636, 283), 8),
                 span("Varieties", (614, 282, 648, 290), 8),
                 span("99", (50, 100, 80, 140), 40)]
        fields = extract_fields(spans)
        self.assertEqual(fields["details"], "7 Varieties 6 PACK")
        self.assertEqual(fields["package_sizes"], ["6 PACK"])

    def test_measurement_ranges_never_supply_pricing_unit(self):
        fields = extract_fields([span("2-LB. BAG; 8-10 oz.; 4 - 5 oz.", (0, 0, 100, 10))])
        self.assertEqual(fields["package_sizes"], ["2-LB. BAG", "8-10 oz.", "4 - 5 oz."])
        self.assertIsNone(fields["unit"])

    def test_dozen_and_piece_sizes_do_not_reintroduce_flower_title(self):
        flower = span("One Dozen Roses", (0, 0, 150, 20))
        piece = span("8 Piece", (0, 40, 70, 50), color=0x1B4491)
        fields = extract_fields([flower, span("DOZEN", (0, 25, 70, 35)), piece],
                                title_spans=[flower, piece])
        self.assertEqual(fields["package_sizes"], ["DOZEN", "8 Piece"])
        self.assertEqual(fields["details"], "DOZEN 8 Piece")
        self.assertIsNone(fields["unit"])

    def test_nearest_saving_keeps_up_to_and_per_basis(self):
        price = span("4.99", (100, 100, 150, 150), 40)
        spans = [price, span("Save Up To $1.00 per lb.", (90, 80, 160, 95)),
                 span("Save 50¢", (300, 80, 360, 95))]
        fields = extract_fields(spans, primary_run=run(price))
        self.assertEqual(fields["savings"], "Save Up To $1.00/lb")
        self.assertIn("multiple_savings", fields["_issues"])
        self.assertEqual(fields["details"], "")

    def test_cleanup_removes_price_for_and_store_metadata(self):
        texts = ["for", "$", "99", "Store Hours 8 AM - 9 PM", "Hanover, MA",
                 "12 Main Street", "Sale Starts September 6", "Effective 9-6 thru 9-12",
                 "Effective9-6 thru 9-12", "MEAT SPECIALS", "Frozen", "Honey, Smoked"]
        fields = extract_fields([span(text, (0, i * 20, 120, i * 20 + 10))
                                 for i, text in enumerate(texts)])
        self.assertEqual(fields["details"], "Frozen Honey, Smoked")

    def test_conflicting_units_are_visible_and_inputs_unchanged(self):
        price = span("4.99", (0, 0, 40, 40), 40)
        spans = [price, span("ea.", (35, 35, 55, 45)), span("lb.", (200, 35, 220, 45))]
        original = [dict(s) for s in spans]
        fields = extract_fields(spans, price_runs=[run(price)])
        self.assertEqual(fields["unit"], "ea")
        self.assertIn("conflicting_sale_units", fields["_issues"])
        self.assertEqual(spans, original)


if __name__ == "__main__":
    unittest.main()
