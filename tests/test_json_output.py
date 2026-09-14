"""Export contract checks, independent of weekly flyer content."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import extract_deals
from json_output import write_json


class JsonWriterTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "nested" / "flyer.json"

    def test_creates_directories_and_preserves_unicode(self):
        data = {"price": "99¢", "item": "Peet’s Coffee"}
        write_json(self.path, data)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), data)

    def test_replaces_previous_export(self):
        write_json(self.path, {"old": [1, 2, 3]})
        write_json(self.path, {"new": []})
        self.assertEqual(json.loads(self.path.read_text()), {"new": []})

    def test_invalid_data_preserves_previous_export_and_cleans_up(self):
        write_json(self.path, {"previous": True})
        before = self.path.read_bytes()
        for invalid in (object(), float("nan")):
            with self.subTest(invalid=type(invalid).__name__):
                with self.assertRaises((TypeError, ValueError)):
                    write_json(self.path, {"invalid": invalid})
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_replace_failure_preserves_previous_export_and_cleans_up(self):
        write_json(self.path, {"previous": True})
        before = self.path.read_bytes()
        with patch("json_output.os.replace", side_effect=OSError("write failed")):
            with self.assertRaises(OSError):
                write_json(self.path, {"new": True})
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


class CliExportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "output" / "flyer.json"
        self.deals = [[{"item": "Apples", "price": "99¢"}],
                      [{"item": "Pasta", "price": "2 for $5"}]]

    def run_cli(self, *args, extraction=None):
        doc = MagicMock()
        doc.__enter__.return_value = doc
        doc.page_count = len(self.deals)
        doc.__getitem__.side_effect = lambda page: page
        argv = ["extract_deals.py", "unused.pdf", "--json-out", str(self.path), *args]
        with patch("sys.argv", argv), \
             patch("extract_deals.pymupdf.open", return_value=doc), \
             patch("extract_deals.extract_page", side_effect=extraction or self.deals.__getitem__), \
             redirect_stdout(io.StringIO()):
            extract_deals.main()

    def test_single_page_is_one_document_with_selected_page(self):
        self.run_cli("--page", "1")
        self.assertEqual(json.loads(self.path.read_text()),
                         {"pages": [{"page": 1, "deals": self.deals[1]}]})

    def test_all_pages_and_repeat_export_are_identical(self):
        self.run_cli()
        expected = {"pages": [{"page": p, "deals": deals}
                              for p, deals in enumerate(self.deals)]}
        self.assertEqual(json.loads(self.path.read_text()), expected)
        before = self.path.read_bytes()
        self.run_cli()
        self.assertEqual(self.path.read_bytes(), before)

    def test_extraction_failure_keeps_previous_export(self):
        self.run_cli()
        before = self.path.read_bytes()
        with self.assertRaises(RuntimeError):
            self.run_cli(extraction=[self.deals[0], RuntimeError("page failed")])
        self.assertEqual(self.path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
