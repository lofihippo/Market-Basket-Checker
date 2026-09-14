"""Report publication and untrusted flyer text boundary checks."""
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from dashboard import render_dashboard


class ReportParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.active_script = None
        self.external_assets = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.active_script = {"attrs": attrs, "text": ""}
            self.scripts.append(self.active_script)
        if tag in {"script", "img", "link"} and (attrs.get("src") or attrs.get("href")):
            self.external_assets.append(attrs)

    def handle_data(self, text):
        if self.active_script is not None:
            self.active_script["text"] += text

    def handle_endtag(self, tag):
        if tag == "script":
            self.active_script = None


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "nested" / "index.html"

    def test_report_is_self_contained_and_data_round_trips(self):
        data = {"weeks": [], "series": [], "notes": ["Peet’s Coffee 99¢"]}
        self.assertEqual(render_dashboard(data, self.path), self.path)
        parser = ReportParser()
        parser.feed(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(parser.scripts), 2)
        self.assertEqual(parser.scripts[0]["attrs"]["type"], "application/json")
        self.assertEqual(json.loads(parser.scripts[0]["text"]), data)
        self.assertEqual(parser.external_assets, [])

    def test_flyer_text_cannot_escape_json_element_or_replace_asset_slots(self):
        item = '</script><script>alert("flyer")</script><!-- & > \u2028 /* DASHBOARD_JS */ DASHBOARD_DATA'
        data = {"weeks": [{"offers": [{"item": item}]}]}
        render_dashboard(data, self.path)
        parser = ReportParser()
        parser.feed(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(parser.scripts), 2)
        self.assertEqual(json.loads(parser.scripts[0]["text"]), data)
        self.assertNotIn('</script><script>alert("flyer")', self.path.read_text())

    def test_invalid_payload_preserves_previous_report(self):
        render_dashboard({"weeks": []}, self.path)
        before = self.path.read_bytes()
        for invalid in (float("nan"), object()):
            with self.subTest(invalid=type(invalid).__name__):
                with self.assertRaises((TypeError, ValueError)):
                    render_dashboard({"invalid": invalid}, self.path)
                self.assertEqual(self.path.read_bytes(), before)
                self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_failed_replace_preserves_previous_report_and_removes_temporary(self):
        render_dashboard({"weeks": []}, self.path)
        before = self.path.read_bytes()
        with patch("dashboard.os.replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                render_dashboard({"weeks": ["replacement"]}, self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])


if __name__ == "__main__":
    unittest.main()
