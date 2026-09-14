"""Offline source acquisition checks; no mutable weekly input or network needed."""
from datetime import date
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

import flyer_source as source


TODAY = date(2026, 9, 13)
PDF_URL = "https://www.shopmarketbasket.com/download/123/"


def payload():
    return {
        "dates": {
            "start_date": "September 13, 2026",
            "end_date": "September 19, 2026",
        },
        "pdf": "/embedded-pdf?id=%2Fdownload%2F123%2F",
        "active": True,
        "title": "Weekly Flyer",
        "products": [],
        "departments": [],
    }


class SourceMetadataTests(unittest.TestCase):
    def test_decodes_embedded_pdf_and_accepts_official_direct_url(self):
        self.assertEqual(source.resolve_pdf_url(payload()["pdf"]), PDF_URL)
        self.assertEqual(source.resolve_pdf_url(PDF_URL), PDF_URL)
        naked_host = "https://shopmarketbasket.com/download/123/"
        self.assertIn(source.resolve_pdf_url(naked_host), (naked_host, PDF_URL))

    def test_rejects_invalid_or_untrusted_pdf_urls(self):
        for value in (None, "", "http://www.shopmarketbasket.com/download/123/",
                      "https://example.com/flyer.pdf",
                      "https://www.shopmarketbasket.com.example.com/flyer.pdf",
                      "https://www.shopmarketbasket.com@evil.example/flyer.pdf",
                      "/embedded-pdf?id=https%3A%2F%2Fevil.example%2Fflyer.pdf",
                      "/embedded-pdf"):
            with self.subTest(value=value), self.assertRaises(source.SourceError):
                source.resolve_pdf_url(value)

    def test_dates_are_inclusive_and_inactive_is_explicit(self):
        for day, expected in ((date(2026, 9, 12), "upcoming"),
                              (TODAY, "current"),
                              (date(2026, 9, 19), "current"),
                              (date(2026, 9, 20), "expired")):
            with self.subTest(day=day):
                parsed = source.parse_metadata(payload(), today=day)
                self.assertEqual(parsed["freshness"], expected)
                self.assertEqual(parsed["start_date"], "2026-09-13")
                self.assertEqual(parsed["end_date"], "2026-09-19")
                self.assertEqual(parsed["pdf_url"], PDF_URL)
        inactive = payload()
        inactive["active"] = False
        self.assertEqual(source.parse_metadata(inactive, today=TODAY)["freshness"],
                         "inactive")

    def test_rejects_missing_or_malformed_required_schema(self):
        cases = [None, [], {}]
        for key, value in (("dates", None), ("products", {}),
                           ("departments", "Dairy"), ("active", "false"),
                           ("pdf", None)):
            case = payload()
            case[key] = value
            cases.append(case)
        for key in ("dates", "pdf", "active", "products", "departments"):
            case = payload()
            del case[key]
            cases.append(case)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(source.SourceError):
                source.parse_metadata(case, today=TODAY)

    def test_rejects_invalid_or_reversed_date_ranges(self):
        for start, end in (("September 31, 2026", "October 1, 2026"),
                           ("not a date", "September 19, 2026"),
                           ("September 20, 2026", "September 19, 2026"),
                           (None, "September 19, 2026")):
            case = payload()
            case["dates"] = {"start_date": start, "end_date": end}
            with self.subTest(start=start, end=end), self.assertRaises(source.SourceError):
                source.parse_metadata(case, today=TODAY)


class SourceAcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "source"
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((72, 72), "Offline flyer acquisition fixture")
            self.pdf = doc.tobytes()
        self.data = payload()
        self.calls = []
        self.api_error = None
        self.pdf_error = None
        self.api_body = None
        self.pdf_body = None

    def fetcher(self, url, *, limit, timeout):
        self.calls.append(url)
        self.assertGreater(limit, 0)
        self.assertGreater(timeout, 0)
        if url == source.API_URL:
            if self.api_error:
                raise self.api_error
            raw = self.api_body if self.api_body is not None else self.raw_api()
            return source.Download(body=raw, url=url, content_type="application/json")
        self.assertEqual(url, PDF_URL)
        if self.pdf_error:
            raise self.pdf_error
        raw = self.pdf_body if self.pdf_body is not None else self.pdf
        return source.Download(body=raw, url=url, content_type="application/pdf")

    def raw_api(self):
        return json.dumps(self.data, ensure_ascii=False).encode("utf-8")

    def fetch(self, **kwargs):
        return source.fetch_current(self.root, today=TODAY, fetcher=self.fetcher,
                                    **kwargs)

    def assert_prior_preserved(self, before, prior):
        self.assertEqual((self.root / "current.json").read_bytes(), before)
        for kind, raw in (("pdf", self.pdf), ("api", self.original_api)):
            self.assertEqual((self.root / prior[kind]["path"]).read_bytes(), raw)

    def establish_prior(self):
        self.original_api = self.raw_api()
        prior = self.fetch()
        return (self.root / "current.json").read_bytes(), prior

    def test_valid_source_archives_exact_bytes_and_publishes_provenance(self):
        result = self.fetch(timeout=7)
        self.assertTrue(result["changed"])
        self.assertEqual(result["start_date"], "2026-09-13")
        self.assertEqual(result["end_date"], "2026-09-19")
        self.assertEqual(result["pdf"]["page_count"], 1)
        self.assertEqual(result["pdf"]["size_bytes"], len(self.pdf))
        self.assertEqual(result["pdf"]["url"], PDF_URL)
        self.assertEqual(result["pdf"]["download_url"], PDF_URL)
        self.assertEqual(result["api"]["url"], source.API_URL)
        self.assertEqual(self.calls, [source.API_URL, PDF_URL])
        for kind, raw in (("api", self.raw_api()), ("pdf", self.pdf)):
            entry = result[kind]
            self.assertEqual(entry["sha256"], hashlib.sha256(raw).hexdigest())
            relative = Path(entry["path"])
            self.assertFalse(relative.is_absolute())
            self.assertNotIn("..", relative.parts)
            self.assertEqual((self.root / relative).read_bytes(), raw)
        current = json.loads((self.root / "current.json").read_text())
        self.assertEqual(current["snapshot_id"], result["snapshot_id"])
        self.assertNotIn("changed", current)
        self.assertTrue(any((self.root / "snapshots").iterdir()))

    def test_repeat_is_unchanged_and_reuses_archived_content(self):
        first = self.fetch()
        archived = {p.relative_to(self.root): p.read_bytes()
                    for p in (self.root / "objects").rglob("*") if p.is_file()}
        second = self.fetch()
        self.assertFalse(second["changed"])
        self.assertEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertEqual(first["api"]["path"], second["api"]["path"])
        self.assertEqual(first["pdf"]["path"], second["pdf"]["path"])
        self.assertEqual(archived, {p.relative_to(self.root): p.read_bytes()
                                  for p in (self.root / "objects").rglob("*")
                                  if p.is_file()})

    def test_changed_metadata_creates_snapshot_even_when_pdf_is_identical(self):
        first = self.fetch()
        old_api = (self.root / first["api"]["path"]).read_bytes()
        self.data["title"] = "Updated Weekly Flyer"
        second = self.fetch()
        self.assertTrue(second["changed"])
        self.assertNotEqual(first["snapshot_id"], second["snapshot_id"])
        self.assertNotEqual(first["api"]["sha256"], second["api"]["sha256"])
        self.assertEqual(first["pdf"]["sha256"], second["pdf"]["sha256"])
        self.assertEqual((self.root / first["api"]["path"]).read_bytes(), old_api)

    def test_cache_timestamp_changes_are_archived_but_not_new_flyer_content(self):
        def fetch(url, *, limit, timeout):
            if url == source.API_URL:
                return source.Download(self.raw_api(), url, 'application/json')
            return source.Download(self.pdf, url, 'application/pdf')

        self.data['pdf'] = '/embedded-pdf?id=%2Fdownload%2F123%2F%3Ftmstv%3D100'
        first = source.fetch_current(self.root, today=TODAY, fetcher=fetch)
        self.data['pdf'] = '/embedded-pdf?id=%2Fdownload%2F123%2F%3Ftmstv%3D200'
        second = source.fetch_current(self.root, today=TODAY, fetcher=fetch)
        self.assertFalse(second['changed'])
        self.assertEqual(first['content_id'], second['content_id'])
        self.assertNotEqual(first['snapshot_id'], second['snapshot_id'])
        self.assertNotEqual(first['api']['sha256'], second['api']['sha256'])
        self.data['title'] = 'Revised sale title'
        self.assertTrue(source.fetch_current(self.root, today=TODAY, fetcher=fetch)['changed'])

    def test_noncurrent_source_fails_before_pdf_and_preserves_prior(self):
        before, prior = self.establish_prior()
        cases = []
        inactive = payload()
        inactive["active"] = False
        cases.append(inactive)
        for start, end in (("September 6, 2026", "September 12, 2026"),
                           ("September 20, 2026", "September 26, 2026")):
            case = payload()
            case["dates"] = {"start_date": start, "end_date": end}
            cases.append(case)
        for case in cases:
            with self.subTest(dates=case["dates"], active=case["active"]):
                self.data = case
                self.calls.clear()
                with self.assertRaises(source.SourceError):
                    self.fetch()
                self.assertEqual(self.calls, [source.API_URL])
                self.assert_prior_preserved(before, prior)

    def test_invalid_api_body_preserves_prior_and_does_not_fetch_pdf(self):
        before, prior = self.establish_prior()
        for raw in (b"<html>Temporarily unavailable</html>", b"{truncated", b"[]"):
            with self.subTest(raw=raw):
                self.api_body = raw
                self.calls.clear()
                with self.assertRaises(source.SourceError):
                    self.fetch()
                self.assertEqual(self.calls, [source.API_URL])
                self.assert_prior_preserved(before, prior)

    def test_invalid_or_truncated_pdf_never_replaces_prior(self):
        before, prior = self.establish_prior()
        for raw in (b"<html>Download unavailable</html>",
                    b"%PDF-1.7\n1 0 obj\n", self.pdf[:-40]):
            with self.subTest(length=len(raw)):
                self.pdf_body = raw
                with self.assertRaises(source.SourceError):
                    self.fetch()
                self.assert_prior_preserved(before, prior)

    def test_request_errors_preserve_prior(self):
        before, prior = self.establish_prior()
        for stage in ("api_error", "pdf_error"):
            with self.subTest(stage=stage):
                setattr(self, stage, TimeoutError("test request timed out"))
                with self.assertRaises(source.SourceError):
                    self.fetch()
                self.assert_prior_preserved(before, prior)
                setattr(self, stage, None)

    def test_printed_pdf_dates_are_verified_and_conflicts_preserve_prior(self):
        before, prior = self.establish_prior()
        for footer, expected in [('Effective 9-6-26 to 9-12-26', False),
                                 ('Effective 9-13-26 to 9-19-26', True)]:
            with self.subTest(footer=footer), pymupdf.open() as doc:
                doc.new_page().insert_text((50, 50), footer)
                self.pdf_body = doc.tobytes()
                if expected:
                    result = self.fetch()
                    self.assertTrue(result['pdf']['dates_verified'])
                    self.assertNotIn('pdf_dates_unverified', result['issues'])
                else:
                    with self.assertRaises(source.SourceError):
                        self.fetch()
                    self.assert_prior_preserved(before, prior)

    def test_oversized_downloads_are_rejected_without_publishing(self):
        before, prior = self.establish_prior()
        with patch('flyer_source.JSON_LIMIT', 10):
            with self.assertRaises(source.SourceError):
                self.fetch()
        with patch('flyer_source.PDF_LIMIT', 10):
            with self.assertRaises(source.SourceError):
                self.fetch()
        self.assert_prior_preserved(before, prior)

    def test_archive_write_failure_leaves_previous_manifest_and_objects_intact(self):
        before, prior = self.establish_prior()
        self.data["title"] = "A changed source before a failed write"
        original_write = source._write_archive
        writes = []

        def fail_second_write(path, body):
            writes.append(path)
            if len(writes) == 2:
                raise OSError("test archive storage failure")
            return original_write(path, body)

        with patch("flyer_source._write_archive", side_effect=fail_second_write):
            with self.assertRaises(source.SourceError):
                self.fetch()
        self.assertEqual(len(writes), 2)
        self.assert_prior_preserved(before, prior)

    def test_failed_initial_download_does_not_create_current_manifest(self):
        self.pdf_error = OSError("test server disconnected")
        with self.assertRaises(source.SourceError):
            self.fetch()
        self.assertFalse((self.root / "current.json").exists())


if __name__ == "__main__":
    unittest.main()
