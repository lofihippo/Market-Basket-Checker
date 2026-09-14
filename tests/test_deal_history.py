"""Price history correctness without network requests or current flyer state."""
import copy
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from deal_history import build_history, record_week


def payload(start="2026-09-06", end="2026-09-12", price="2 for $5", **changes):
    deal = {"item": "Example Yogurt", "price": price, "unit": "ea",
            "package_sizes": ["6 oz."], "details": "6 oz. Assorted flavors",
            "confidence": "high", "_issues": [], "category": "Dairy & Eggs",
            "category_source": "official department", "_source_text": "Example Yogurt",
            "_bbox": [1, 2, 30, 40]}
    deal.update(changes)
    return {"source": {"start_date": start, "end_date": end,
                       "pdf": {"sha256": "a" * 64, "url": "https://example.org/flyer.pdf"},
                       "fetched_at": "2026-09-06T01:00:00Z", "checked_at": "2026-09-06T02:00:00Z"},
            "pages": [{"page": 0, "deals": [deal]}]}


class DealHistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "history.sqlite"

    def test_missing_database_is_empty_and_not_created_by_report(self):
        self.assertEqual(build_history(self.path), {"weeks": [], "series": [], "week_count": 0})
        self.assertFalse(self.path.exists())

    def test_retry_ignores_fetch_times_preserves_original_payload_and_ids(self):
        original = payload()
        before = copy.deepcopy(original)
        first = record_week(self.path, original)
        snapshot = build_history(self.path)
        later = copy.deepcopy(original)
        later["source"].update(fetched_at="2026-09-07T12:00:00Z", checked_at="2026-09-07T12:00:00Z", changed=False)
        second = record_week(self.path, later)
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(build_history(self.path), snapshot)
        self.assertEqual(original, before)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM history_runs").fetchone()[0], 1)
            self.assertEqual(json.loads(connection.execute("SELECT payload_json FROM history_runs").fetchone()[0]), original)

    def test_corrected_week_keeps_raw_revision_but_contributes_once(self):
        first = record_week(self.path, payload(price="2 for $5"))
        second = record_week(self.path, payload(price="2 for $4"))
        history = build_history(self.path)
        self.assertTrue(second["changed"])
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(history["week_count"], 1)
        self.assertEqual(history["series"][0]["observations"][0]["amount"], 4)
        self.assertEqual(len(history["series"][0]["observations"]), 1)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM history_runs").fetchone()[0], 2)
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE history_runs SET payload_json = '{}' WHERE run_id = ?", (first["run_id"],))

    def test_transport_refresh_does_not_duplicate_semantically_identical_source(self):
        original = payload()
        original["source"].update(content_id="stable-content", title="Weekly Flyer", issues=[],
                                  snapshot_id="old-snapshot", snapshot_path="snapshots/old.json",
                                  api={"sha256": "b" * 64, "path": "objects/old.json"})
        original["source"]["pdf"].update(url="https://example.org/flyer.pdf?tmstv=1", path="old.pdf")
        first = record_week(self.path, original)
        refreshed = copy.deepcopy(original)
        refreshed["source"].update(snapshot_id="new-snapshot", snapshot_path="snapshots/new.json",
                                   api={"sha256": "c" * 64, "path": "objects/new.json"})
        refreshed["source"]["pdf"].update(url="https://example.org/flyer.pdf?tmstv=2", path="new.pdf")
        second = record_week(self.path, refreshed)
        self.assertFalse(second["changed"])
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(build_history(self.path)["weeks"][0]["source"], original["source"])
        refreshed["pages"][0]["deals"][0]["price"] = "2 for $4"
        self.assertTrue(record_week(self.path, refreshed)["changed"])
        self.assertEqual(build_history(self.path)["series"][0]["observations"][0]["amount"], 4)
        with closing(sqlite3.connect(self.path)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM history_runs").fetchone()[0], 2)

    def test_semantic_source_identity_preserves_content_dates_and_quality_changes(self):
        original = payload()
        original["source"].update(content_id="stable-content", title="Weekly Flyer", issues=[])
        first = record_week(self.path, original)
        changes = [
            {"content_id": "different-content"},
            {"start_date": "2026-09-07"},
            {"end_date": "2026-09-13"},
            {"issues": ["pdf_dates_unverified"]},
            {"title": "Corrected Weekly Flyer"},
            {"pdf": {"sha256": "d" * 64}},
            {"pdf": {"sha256": "a" * 64, "dates_verified": False}},
        ]
        for change in changes:
            data = copy.deepcopy(original)
            data["source"].update(change)
            with self.subTest(change=change):
                result = record_week(self.path, data)
                self.assertTrue(result["changed"])
                self.assertNotEqual(result["run_id"], first["run_id"])

    def test_chronology_is_flyer_order_and_multibuy_price_is_arithmetic(self):
        record_week(self.path, payload("2026-09-13", "2026-09-19", "2 for $4"))
        record_week(self.path, payload(price="2 for $5"))
        history = build_history(self.path)
        self.assertEqual([week["start_date"] for week in history["weeks"]], ["2026-09-06", "2026-09-13"])
        self.assertEqual(history["week_count"], 2)
        self.assertEqual(len(history["series"]), 1)
        series = history["series"][0]
        self.assertEqual(series["quantity"], 2)
        self.assertEqual([point["unit_price"] for point in series["observations"]], [2.5, 2.0])
        self.assertEqual([point["amount"] for point in series["observations"]], [5.0, 4.0])
        self.assertEqual(series["observations"][0]["offer_id"], history["weeks"][0]["offers"][0]["id"])

    def test_distinct_sizes_details_sale_bases_and_quantities_never_merge(self):
        initial = payload()
        base = initial["pages"][0]["deals"][0]
        initial["pages"][0]["deals"].extend([
            {**base, "package_sizes": ["12 oz."]},
            {**base, "details": "6 oz. Plain only"},
            {**base, "unit": "lb"},
            {**base, "price": "3 for $5"},
            {**base, "item": "Example Greek Yogurt"},
        ])
        record_week(self.path, initial)
        history = build_history(self.path)
        self.assertEqual(len(history["series"]), 6)
        self.assertEqual(len({row["product_key"] for row in history["series"]}), 6)

    def test_typographic_case_and_whitespace_normalization_is_conservative(self):
        record_week(self.path, payload(item="Pete’s Yogurt", details="6 oz.  Assorted flavors"))
        record_week(self.path, payload("2026-09-13", "2026-09-19", item=" PETE'S YOGURT ", details="6 oz. Assorted flavors"))
        self.assertEqual(len(build_history(self.path)["series"]), 1)

    def test_review_candidates_remain_visible_but_never_enter_price_series(self):
        data = payload()
        base = data["pages"][0]["deals"][0]
        cases = [
            {"item": "Flagged", "_issues": ["overprinted_price_text"]},
            {"item": "Low confidence", "confidence": "low"},
            {"item": "Medium confidence", "confidence": "medium"},
            {"item": "No confidence", "confidence": None},
            {"item": "Variants", "prices": [{"price": "2.99"}, {"price": "4.99"}]},
            {"item": "Unscoped", "package_sizes": [], "unit": None},
            {"item": "No price", "price": None},
            {"item": "Mismatched terms", "amount": 999},
        ]
        data["pages"][0]["deals"] = [{**base, **changes} for changes in cases]
        record_week(self.path, data)
        history = build_history(self.path)
        self.assertEqual(history["series"], [])
        offers = history["weeks"][0]["offers"]
        self.assertEqual(len(offers), len(cases))
        self.assertTrue(all(not offer["history_eligible"] and offer["history_reason"] for offer in offers))
        self.assertTrue(all(offer["category"] == "Dairy & Eggs" and offer["_source_text"] for offer in offers))

    def test_duplicate_same_week_offers_cannot_bias_a_series(self):
        data = payload()
        data["pages"][0]["deals"] *= 2
        record_week(self.path, data)
        history = build_history(self.path)
        offers = history["weeks"][0]["offers"]
        self.assertEqual(history["series"], [])
        self.assertEqual(len({offer["id"] for offer in offers}), 2)
        self.assertTrue(all("same week" in offer["history_reason"] for offer in offers))

    def test_failure_after_revision_insert_rolls_back_revision_and_activation(self):
        record_week(self.path, payload())
        before = build_history(self.path)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("CREATE TRIGGER fail_activation BEFORE UPDATE ON history_active "
                               "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            record_week(self.path, payload(price="2 for $4"))
        self.assertEqual(build_history(self.path), before)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM history_runs").fetchone()[0], 1)

    def test_bad_source_or_nan_never_changes_existing_history(self):
        record_week(self.path, payload())
        before = build_history(self.path)
        bad_date, bad_hash, empty_page, nan_price = [payload() for _ in range(4)]
        bad_date["source"]["end_date"] = "2026-09-01"
        bad_hash["source"]["pdf"]["sha256"] = "unverified"
        empty_page["pages"][0]["deals"] = []
        nan_price["pages"][0]["deals"][0]["amount"] = float("nan")
        for data in (bad_date, bad_hash, empty_page, nan_price):
            with self.subTest(data=data), self.assertRaises(ValueError):
                record_week(self.path, data)
        self.assertEqual(build_history(self.path), before)

    def test_missing_or_out_of_range_pages_are_not_imported_as_complete_weeks(self):
        valid = payload()
        valid["source"]["pdf"]["page_count"] = 1
        record_week(self.path, valid)
        before = build_history(self.path)
        partial = copy.deepcopy(valid)
        partial["source"]["pdf"]["page_count"] = 2
        out_of_range = copy.deepcopy(valid)
        out_of_range["pages"][0]["page"] = 1
        for data in (partial, out_of_range):
            with self.subTest(data=data), self.assertRaisesRegex(ValueError, "every source PDF page"):
                record_week(self.path, data)
        self.assertEqual(build_history(self.path), before)


if __name__ == "__main__":
    unittest.main()
