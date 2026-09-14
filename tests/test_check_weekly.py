"""Weekly command integration without network requests or mutable inputs."""
from contextlib import redirect_stderr, redirect_stdout
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_weekly as cli


class WeeklyCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source_dir = self.root / "source"
        self.output = self.root / "weekly.json"
        self.prior = b'{"previous": "valid export"}\n'
        self.output.write_bytes(self.prior)
        self.manifest = {
            "snapshot_id": "offline-snapshot", "changed": True,
            "start_date": "2026-09-13", "end_date": "2026-09-19",
            "pdf": {"path": "objects/offline.pdf", "page_count": 2,
                    "text_page_count": 2, "dates_verified": True},
            "api": {"path": "objects/offline.json"},
        }
        self.document = {"pages": [
            {"page": 0, "deals": [{"item": "Apples", "price": "99¢"}]},
            {"page": 1, "deals": [{"item": "Pasta", "price": "2 for $5"}]},
        ]}
        self.previous_config = cli.ed.CONFIG
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def run_cli(self, *extra, fetch_error=None, extract_error=None, extraction=None):
        arguments = ["--source-dir", str(self.source_dir), "--json-out", str(self.output),
                     *extra]
        with patch.object(cli, "fetch_current", return_value=copy.deepcopy(self.manifest),
                          side_effect=fetch_error) as fetch, \
             patch.object(cli.ed, "extract_document",
                          return_value=copy.deepcopy(self.document),
                          side_effect=extract_error or extraction) as extract, \
             patch.object(cli, 'record_and_render', return_value={'week_count': 1}) as report, \
             patch.object(cli, 'enriched_export', side_effect=lambda value: value), \
             redirect_stdout(self.stdout), redirect_stderr(self.stderr):
            code = cli.main(arguments)
        self.assertIs(cli.ed.CONFIG, self.previous_config)
        self.report_mock = report
        return code, fetch, extract

    def test_export_includes_dates_source_archive_and_effective_config(self):
        config = self.root / "config.json"
        config.write_text(json.dumps({"non_products": ["Test Extra Heading"]}))
        seen_config = []

        def extract(path):
            seen_config.append(copy.deepcopy(cli.ed.CONFIG))
            return copy.deepcopy(self.document)

        code, fetch, extract_mock = self.run_cli("--timeout", "7", "--config", str(config),
                                                 extraction=extract)
        self.assertEqual(code, 0)
        fetch.assert_called_once_with(self.source_dir, timeout=7)
        extract_mock.assert_called_once_with(self.source_dir / "objects/offline.pdf")
        result = json.loads(self.output.read_text())
        self.assertEqual(result["pages"], self.document["pages"])
        self.assertNotIn("changed", result["source"])
        self.assertEqual(result["source"]["archive_root"], str(self.source_dir.resolve()))
        self.assertEqual(result["source"]["start_date"], "2026-09-13")
        self.assertEqual(result["extraction"]["method"], "pdf")
        self.assertEqual(result["extraction"]["config"], seen_config[0])
        self.assertIn("Test Extra Heading", result["extraction"]["config"]["non_products"])
        self.assertIn("Wrote 2 offers", self.stdout.getvalue())
        self.report_mock.assert_called_once()

    def test_fetch_only_does_not_extract_or_replace_existing_export(self):
        self.manifest["pdf"]["text_page_count"] = 0
        self.manifest["changed"] = False
        code, fetch, extract = self.run_cli("--fetch-only")
        self.assertEqual(code, 0)
        fetch.assert_called_once()
        extract.assert_not_called()
        self.assertEqual(self.output.read_bytes(), self.prior)
        self.assertIn("unchanged", self.stdout.getvalue())
        self.assertNotIn("Wrote", self.stdout.getvalue())
        self.report_mock.assert_not_called()

    def test_json_only_mode_does_not_update_history(self):
        code, _, _ = self.run_cli('--no-report')
        self.assertEqual(code, 0)
        self.report_mock.assert_not_called()

    def test_invalid_configuration_fails_before_network(self):
        config = self.root / "bad-config.json"
        for value in ([], {"taglines": "not an array"}, {"non_products": [3]}):
            with self.subTest(value=value):
                config.write_text(json.dumps(value))
                code, fetch, extract = self.run_cli("--config", str(config))
                self.assertEqual(code, 1)
                fetch.assert_not_called()
                extract.assert_not_called()
                self.assertEqual(self.output.read_bytes(), self.prior)

    def test_invalid_timeout_fails_before_network(self):
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value):
                code, fetch, extract = self.run_cli("--timeout", value)
                self.assertEqual(code, 1)
                fetch.assert_not_called()
                extract.assert_not_called()
                self.assertEqual(self.output.read_bytes(), self.prior)

    def test_source_failure_preserves_export_and_reports_failure(self):
        code, _, extract = self.run_cli(fetch_error=cli.SourceError("Official flyer is expired"))
        self.assertEqual(code, 1)
        extract.assert_not_called()
        self.assertEqual(self.output.read_bytes(), self.prior)
        self.assertIn("expired", self.stderr.getvalue())
        self.assertNotIn("Source archived", self.stdout.getvalue())
        self.assertNotIn("Wrote", self.stdout.getvalue())

    def test_extraction_failure_preserves_export(self):
        code, _, _ = self.run_cli(extract_error=RuntimeError("Unable to read page 2"))
        self.assertEqual(code, 1)
        self.assertEqual(self.output.read_bytes(), self.prior)
        self.assertIn("Unable to read page 2", self.stderr.getvalue())
        self.assertNotIn("Wrote", self.stdout.getvalue())

    def test_empty_extraction_and_textless_pages_preserve_export(self):
        code, _, _ = self.run_cli(extraction=lambda path: {"pages": [{"page": 0, "deals": []}]})
        self.assertEqual(code, 1)
        self.assertIn("no offers", self.stderr.getvalue())
        self.assertEqual(self.output.read_bytes(), self.prior)
        self.manifest["pdf"]["text_page_count"] = 1
        code, _, extract = self.run_cli()
        self.assertEqual(code, 1)
        extract.assert_not_called()
        self.assertIn("without selectable text", self.stderr.getvalue())
        self.assertEqual(self.output.read_bytes(), self.prior)

    def test_export_serialization_failure_keeps_previous_export(self):
        self.document["pages"][0]["deals"][0]["price_n"] = float("nan")
        code, _, _ = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(self.output.read_bytes(), self.prior)
        self.assertNotIn("Wrote", self.stdout.getvalue())

    def test_one_empty_page_does_not_publish_a_partially_extracted_flyer(self):
        self.document['pages'][1]['deals'] = []
        code, _, _ = self.run_cli()
        self.assertEqual(code, 1)
        self.assertEqual(self.output.read_bytes(), self.prior)
        self.assertIn('page(s) [2]', self.stderr.getvalue())
        self.assertNotIn('Wrote', self.stdout.getvalue())

    def test_output_cannot_replace_its_source_manifest_or_archive(self):
        for name in ('current.json', 'objects/source.json', 'snapshots/source.json'):
            with self.subTest(name=name):
                code, fetch, extract = self.run_cli('--json-out', str(self.source_dir / name))
                self.assertEqual(code, 1)
                fetch.assert_not_called()
                extract.assert_not_called()
                self.assertIn('outside the source archive', self.stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
