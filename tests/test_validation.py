"""Regression checks for the validator itself; extraction accuracy is separate."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import validate_page1 as cli
from validation import compare_deals, norm_price


def offer(**changes):
    result = {"item": "Example Apples", "price": "99¢", "unit": "lb",
              "details": "3 varieties", "savings": "Save 50¢/lb", "price_n": 0.99}
    result.update(changes)
    return result


class ComparisonTests(unittest.TestCase):
    def test_complete_reference_passes(self):
        _, _, reference = cli.load_fixture()
        result = compare_deals(deepcopy(reference), reference)
        self.assertTrue(result["ok"])
        self.assertEqual(result["passed"], len(reference))

    def test_empty_and_missing_extractions_fail(self):
        reference = [offer(), offer(item="Example Pears")]
        for actual, missing in (([], 2), ([reference[0]], 1)):
            with self.subTest(missing=missing):
                result = compare_deals(actual, reference)
                self.assertFalse(result["ok"])
                self.assertEqual(len(result["missing"]), missing)

    def test_extra_and_duplicate_records_fail(self):
        for extra in (offer(item="Unexpected Fruit"), offer()):
            with self.subTest(item=extra["item"]):
                result = compare_deals([offer(), extra], [offer()])
                self.assertFalse(result["ok"])
                self.assertEqual(result["matched"], 1)
                self.assertEqual(len(result["unexpected"]), 1)

    def test_truncated_name_cannot_match(self):
        result = compare_deals([offer(item="Apples")], [offer()])
        self.assertFalse(result["ok"])
        self.assertEqual(result["matched"], 0)
        self.assertEqual(len(result["missing"]), 1)

    def test_harmless_formatting_and_currency_equivalents_pass(self):
        reference = [offer(item="Peet's Coffee")]
        actual = [offer(item="  PEET’S   COFFEE ", price="$0.99", unit="lb.",
                        details="3  VARIETIES", savings="Save $0.50 lb.")]
        self.assertTrue(compare_deals(actual, reference)["ok"])

    def test_each_incorrect_field_fails(self):
        changes = {"price": "$99", "unit": "ea", "details": "64 oz from a neighbor",
                   "savings": "Save $2.00/lb", "price_n": 99}
        for field, value in changes.items():
            with self.subTest(field=field):
                result = compare_deals([offer(**{field: value})], [offer()])
                self.assertFalse(result["ok"])
                self.assertIn(field, [diff["field"] for diff in result["differences"]])

    def test_corrupting_every_price_cannot_report_pass(self):
        _, _, reference = cli.load_fixture()
        actual = [dict(deal, price="999.00") for deal in reference]
        result = compare_deals(actual, reference)
        self.assertFalse(result["ok"])
        self.assertEqual(result["matched"], len(reference))
        self.assertEqual(result["passed"], 0)

    def test_offer_quantity_and_up_to_qualifier_are_significant(self):
        for price in ("3 for $5", "$5", "$2.50"):
            with self.subTest(price=price):
                ref = offer(price="2 for $5", price_n=5)
                self.assertFalse(compare_deals([dict(ref, price=price)], [ref])["ok"])
        self.assertFalse(compare_deals([offer(savings="Save Up To 50¢/lb")], [offer()])["ok"])

    def test_invalid_prices_and_nonfinite_numbers_fail(self):
        for price in (None, "garbage", "$NaN", "$0.99¢"):
            with self.subTest(price=price):
                with self.assertRaises(ValueError):
                    norm_price(price)
                self.assertFalse(compare_deals([offer(price=price)], [offer()])["ok"])
        for value in (None, float("nan"), float("inf"), True):
            self.assertFalse(compare_deals([offer(price_n=value)], [offer()])["ok"])

    def test_missing_required_fields_fail_even_if_reference_value_is_empty(self):
        ref = offer(unit="", savings=None, details="")
        for field in ref:
            actual = dict(ref)
            del actual[field]
            with self.subTest(field=field):
                self.assertFalse(compare_deals([actual], [ref])["ok"])

    def test_empty_ambiguous_or_inconsistent_reference_is_rejected(self):
        for reference in ([], [offer(), offer()], [offer(price_n=99)]):
            with self.assertRaises(ValueError):
                compare_deals([], reference)


class ValidatorCommandTests(unittest.TestCase):
    def run_main(self, args, **patches):
        with patch.object(cli.ed, "extract_page", **patches), \
             redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return cli.main(args)

    def test_success_and_discrepancies_have_distinct_exit_codes(self):
        _, _, reference = cli.load_fixture()
        self.assertEqual(self.run_main([], return_value=reference), 0)
        self.assertEqual(self.run_main([], return_value=[]), 1)
        actual = [dict(deal, price="999.00") for deal in reference]
        self.assertEqual(self.run_main([], return_value=actual), 1)

    def test_missing_or_modified_fixture_fails_before_extraction(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td)
            for modified in (False, True):
                if modified:
                    manifest = json.loads((cli.FIXTURE / "manifest.json").read_text())
                    (directory / "manifest.json").write_text(json.dumps(manifest))
                    (directory / "flyer.pdf").write_bytes(b"different weekly PDF")
                with patch.object(cli.ed, "extract_page") as extract, \
                     redirect_stderr(io.StringIO()):
                    self.assertEqual(cli.main(["--fixture", td]), 2)
                    extract.assert_not_called()

    def test_extraction_error_returns_error_status(self):
        self.assertEqual(self.run_main([], side_effect=RuntimeError("page failed")), 2)


if __name__ == "__main__":
    unittest.main()
