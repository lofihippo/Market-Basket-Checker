"""Build the offline weekly-deals report from captured, dated observations."""
import json
import os
from pathlib import Path
import tempfile


def render_dashboard(data, output_path):
    """Atomically publish a single HTML file, keeping a prior report on failure.

    The JSON is data, never executable JavaScript. Escaping HTML-significant
    characters prevents source text from closing its script element.
    """
    assets = Path(__file__).parent / "web"
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False).replace(
        "&", "\\u0026").replace("<", "\\u003c").replace(
        ">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = (assets / "dashboard.html").read_text(encoding="utf-8")
    # Split once: content injected into one slot cannot create another slot.
    replacements = {
        "/* DASHBOARD_CSS */": (assets / "dashboard.css").read_text(encoding="utf-8"),
        "/* DASHBOARD_JS */": (assets / "dashboard.js").read_text(encoding="utf-8"),
        "DASHBOARD_DATA": payload,
    }
    import re
    html = re.sub(r"/\* DASHBOARD_CSS \*/|/\* DASHBOARD_JS \*/|DASHBOARD_DATA",
                  lambda match: replacements[match.group()], html)
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=destination.parent,
                                         prefix=f".{destination.name}.",
                                         suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(html)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return destination
