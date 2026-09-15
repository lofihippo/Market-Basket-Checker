# Command reference

[Back to the README](../README.md) · [How it works](HOW_IT_WORKS.md) ·
[GitHub deployment](GITHUB_PAGES.md)

Run these commands from the repository root after activating the virtual
environment described in the [installation instructions](../README.md#install).
Paths below are relative to the repository root unless otherwise shown.

## Download and extract

For the normal download, extraction, history update, and report build:

```bash
python scripts/check_weekly.py
```

The checker downloads the official PDF automatically. For manual or offline
extraction, place a PDF at `market-basket-weekly-flyer.pdf`, or pass another path
to `extract_deals.py`.

Download and verify the source without running extraction:

```bash
python scripts/check_weekly.py --fetch-only
```

Use `--source-dir DIR`, `--json-out FILE`, `--history-db FILE`,
`--html-out FILE`, `--timeout SECONDS`, and
`--config FILE` to override the archive, export, request timeout, or extractor
settings. Defaults are `output/source`, `output/weekly-deals.json`,
`output/history.sqlite3`, `output/report.html`, and a 30-second socket timeout.
Use `--no-report` to export JSON without updating history or HTML.
A normal check runs extraction even when source bytes are unchanged.
`--skip-unchanged` instead verifies the current source, then reuses a successful
build only when sale content, configuration, Python/PyMuPDF versions, code,
report assets, and all output file hashes match its saved receipt. Missing or
edited outputs trigger a rebuild. Failed checks never advance this receipt.

Extract and print all deals:

```bash
python extract_deals.py market-basket-weekly-flyer.pdf
```

Extract a specific page:

```bash
python extract_deals.py market-basket-weekly-flyer.pdf --page 0
```

Generate a consolidated JSON quality report (counts, confidence breakdown,
flagged items) and write `/tmp/mb/consolidated.json`:

```bash
python scripts/report_quality.py
```

Run the full extractor and save JSON via the CLI:

```bash
python extract_deals.py market-basket-weekly-flyer.pdf --json-out output/flyer.json
```

The output is one JSON document with a `pages` array. Each entry contains a
zero-based `page` number and its `deals` array, for example
`{"pages": [{"page": 0, "deals": []}]}`. This structure is the same for one or
multiple selected pages. Parent directories are created automatically, and
each successful run replaces the previous export instead of appending to it.
If extraction or writing fails, an existing export is preserved.

The consolidated scripts retain their flat array of deal records at
`/tmp/mb/consolidated.json`; they also create missing directories and replace
the output atomically.

## Rebuild, import, and back up history

Rebuild the report from stored history without downloading or extracting:

```bash
python scripts/build_report.py
```

Import existing dated exports with `source.start_date`, `source.end_date`, and
`source.pdf.sha256` (plain local extractor output alone lacks this metadata):

```bash
python scripts/build_report.py output/history-imports/2026-09-06.json output/history-imports/2026-09-13.json
```

Each history update is transactional, and JSON and HTML files are replaced
atomically individually. The complete command is not a transaction spanning
all three outputs: if report rendering fails after extraction, JSON and history
may already be updated while the previous HTML survives. Rebuild the report
after fixing the error. Multi-file imports likewise commit one week at a time.

Back up `output/history.sqlite3` while no checker is running, along with
`output/source/` and any imported PDFs/JSON. The generated `output/` directory
is ignored by Git. Keep the dated test fixtures with the project for the seeded
older week's source link.

## Scheduled checks on macOS

The local schedule runs the Python checker directly, without AI calls or AI
usage credits. It checks **Sunday and Monday at 9 a.m. in the Mac's local time
zone**, plus at login. Monday provides a second chance if Sunday's source is
late or unavailable. Flyer effective dates are always validated in New York
time, even if the Mac's scheduling time zone changes.

Prepare and inspect the job without enabling it:

```bash
python scripts/manage_schedule.py prepare
```

Install it for the current macOS user (also starts an immediate check):

```bash
python scripts/manage_schedule.py install
```

The installed LaunchAgent is
`~/Library/LaunchAgents/org.reasonix.market-basket-weekly-checker.plist`.
It points at this checkout and its `.venv/bin/python`; Codex does not need to
be open. Keep the checkout and virtual environment in place. To change the time,
rerun installation with `--hour 10 --minute 30`; the previous configuration is
backed up. Reinstalling also re-enables a disabled schedule.

Inspect the schedule, check now, or read the last check result:

```bash
python scripts/manage_schedule.py status
python scripts/run_scheduled_check.py
python scripts/run_scheduled_check.py --status
```

The runner sets its working directory automatically, prevents overlapping
scheduled runs with a process lock, and limits each check to five minutes.
It saves `output/automation/status.json` with start/end times, `updated`,
`unchanged`, or `failed`, the exit code, and the last successful check time.
`output/automation/check.log` rotates at 1 MB with three backups. Separate
`launchd.stdout.log` and `launchd.stderr.log` capture startup output/errors.
Failures remain visible in status and logs; there are no email or push alerts.
Avoid running manual extraction or history imports concurrently with a check.

The successful-build receipt is `output/automation/success.json`. An unchanged
check refreshes source verification and run status while preserving JSON,
history, and HTML bytes. The report's generation date therefore means the last
build, not the last source check. An expired or inaccessible source still fails;
an old report is never treated as evidence that this week's source is valid.

Disable future runs while retaining all data:

```bash
python scripts/manage_schedule.py disable
```

This is a user LaunchAgent and requires the user to be logged in. macOS runs a
missed calendar check after waking from sleep; a powered-off Mac cannot run it.
The extra login check helps after restarting. See [Apple's scheduling guide](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/ScheduledJobs.html).
This setup does not run a hosted service or wake the Mac on a timer.

The hosted schedule is separate: see [GitHub Pages and weekly updates](GITHUB_PAGES.md).

## Extractor configuration and visual inspection

Override heuristics for a new flyer (e.g. a new section header) without editing
code:

```bash
python extract_deals.py market-basket-weekly-flyer.pdf --config config.example.json
```

Visual inspection tools (render a page or a region to PNG):

```bash
python scripts/render_page.py market-basket-weekly-flyer.pdf 0 /tmp/page0.png 110
python scripts/crop_page.py market-basket-weekly-flyer.pdf 0 /tmp/region.png 25 172 359 461 200
```

## Developing and testing

Run the export, validator, layout, pricing, and offline acquisition checks:

```bash
python -m unittest discover -s tests -v
```

When you change the extractor, re-check for regressions:

```bash
python scripts/validate_page1.py   # fixed September 6–12, 2026 cover-page reference
python scripts/report_quality.py   # overall counts / confidence / outliers
```

The validator uses the dated PDF under `tests/fixtures/2026-09-06/`, checks its
SHA-256 before extraction, and compares all 25 annotated cover-page offer
groups. Replacing the root weekly PDF does not change this regression input.
The archived fixture is explicitly allowed through `.gitignore`.

Validation requires one-to-one, complete item names and compares displayed
price (including multibuy quantity), numeric price, unit, savings, and details.
It normalizes case, whitespace, typographic quotes/dashes, equivalent dollar
and cent amounts, and common unit spellings. Details otherwise remain a strict
text comparison, including word order; formatting differences can therefore
be reported alongside factual errors. Reference names must uniquely identify
offers. Missing, unexpected, or duplicate output records fail validation.

Exit status is **0** for a complete match, **1** for extraction discrepancies,
and **2** for a fixture, configuration, or extraction error. Use `--config FILE`
to validate the same overrides as the extraction CLI, or `--fixture DIRECTORY`
for another annotated fixture with its own manifest. Do not overwrite the
dated baseline when downloading a new week.

The current extractor still fails this strict cover-page check because some
brands appear only in image logos and descriptive prose differs from the
annotated reference. These discrepancies remain visible; do not treat a
passing unit-test suite as a passing cover-page comparison.
Boundary tests additionally cover all 15 page-2 meat offers, all 13 page-8
bakery names, separated beer/wine and household offers, and distinct products
with matching generic titles. Pricing regressions cover Pumpkin Whoopie Pies
at $5.49, Cake Slices at $2.49, and Blueberry Pie at $7.79, plus explicit
package variants and savings/unit separation.

Passing these tests establishes the selected regression cases, not complete
all-page or multiweek accuracy. Image-only branding and other promotional
banner styles also remain limitations. The quality report checks primary and
variant prices and prints source pages and reasons for review. Its counts and
heuristic confidence labels do not establish completeness or accuracy.

Where the PDF contains overlapping old and replacement price text, the parser
uses the later glyphs and adds `overprinted_price_text` for review. The archived
Blueberry Pie price is visually confirmed as `$7.79`; retaining the flag makes
this source ambiguity visible when processing another flyer.
