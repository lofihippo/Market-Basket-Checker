# Market Basket Weekly Specials

[View weekly specials](https://lofihippo.github.io/Market-Basket-Checker/) ·
[Automatic update status](https://github.com/lofihippo/Market-Basket-Checker/actions/workflows/weekly-specials.yml)

Extract the weekly deals from the Market Basket grocery flyer PDF into
searchable offers, a dated price archive, and a local HTML report.

The flyer is published weekly at `https://www.shopmarketbasket.com/weekly-flyer/`
(the "view classic flyer" link downloads a PDF). This project parses that PDF
and outputs one JSON record per deal, with the item name, details (size/flavor),
price, savings, and a numeric price value.

For the Sunday 5 PM Eastern GitHub Actions schedule, Pages setup, and local
self-hosting, see [GitHub Pages and weekly updates](docs/GITHUB_PAGES.md).
The browser UI is a report viewer; Python runs the downloads and extraction
locally or on the scheduled GitHub runner. See also
[running options](docs/RUNNING_OPTIONS.md).

## Layout families handled

The flyer uses two page layouts, both auto-detected per page:

1. **Product cells and banners** — bounded boxes and wide single-offer banners
   detected from the PDF's vector drawings.
2. **Table grids** — dense multi-product columns (DAIRY, FROZEN, SNACKS,
   MEAT SPECIALS). Column rules and nearby titles establish lanes before
   product names are matched to red price runs, including side-aligned prices.

Names support the reference flyer's blue, navy, purple, and enclosed white
meat-title styles. White price digits, package labels, and badges are excluded.
Pages can mix both layouts; the extractor runs both paths and removes duplicate
detections within the same region. Distinct regions with the same generic
product name remain separate offers.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

The weekly checker downloads the official PDF automatically. For manual or
offline extraction, place a PDF in the repo root as
`market-basket-weekly-flyer.pdf`, or pass its path to the local extractor.

## Usage

Discover, archive, and extract the current weekly flyer:

```bash
python scripts/check_weekly.py
```

Open `output/report.html` in a browser after the command finishes. It includes
a colorful overview of nine broad shopping categories, with offer counts,
shares of the flyer, illustrations, and representative prices. Select a category
to see all its offers as cards, without pagination, or search across the flyer.
Original departments, review flags, and PDF page links remain in offer details.
Separate Price history and In season views contain comparable observations,
monthly category counts, and the seasonal produce calendar. The report has responsive layouts and works offline without external
fonts, scripts, or a web server. Original PDF links require the archive files
to remain in their relative locations.

The command also writes `output/weekly-deals.json`, containing `pages`, source dates and
hashes in `source`, and the extraction method/configuration in `extraction`.
The PDF remains the source of the extracted offers. The official website's
JSON products supply departments for matching item names; they are not
substituted for PDF results or used as an accuracy denominator. Other category
assignments are labeled estimates, and ambiguous names remain uncategorized.

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

## Source acquisition and history

`flyer_source.py` reads the official weekly-flyer JSON endpoint, validates its
schema and inclusive effective dates using the `America/New_York` calendar,
and resolves its embedded PDF link. Only HTTPS requests and redirects to the
official Market Basket hosts are accepted. Downloads are bounded to 5 MB for
metadata and 50 MB for PDFs; PDF content must open without repair or encryption.
Recognized printed PDF dates must agree with the endpoint. An unrecognized
date format is retained as `pdf_dates_unverified` in source issues.

Raw JSON and PDF bytes are stored separately under `output/source/objects/`
using SHA-256 filenames. Snapshot manifests retain dates, URLs, hashes,
retrieval time, and PDF page counts. `output/source/current.json` is replaced
only after the source has passed validation and the archives are complete.
Repeated identical snapshots reuse the archives; metadata changes count as a
new snapshot even when the PDF is unchanged. A separate `content_id` ignores
only the observed `tmstv` cache-busting parameter in PDF URLs, so that routine
URL refresh does not report changed sale content. Raw responses and URLs are
still preserved in distinct snapshots. All archive paths in manifests
are relative to the source directory; deal exports include its absolute path
as `source.archive_root`.

An inactive, upcoming, or expired flyer fails the check. Network, schema, PDF,
and archive-write failures preserve the previous source manifest; extraction
failures preserve the previous deal export. The command exits **1** on failure
and does not silently use stale data. Freshness in a manifest describes its
`checked_at` time: always check the effective dates when reading an old export.
PDFs with textless pages, no offers, or any page with no extracted offers
require review and are not published as successful deal exports. Even a page
that intentionally contains no specials requires review under this conservative
check. `--json-out` must be outside the source archive directory.

The mutable root PDF and `tests/fixtures/2026-09-06/` are never overwritten by
acquisition. The public endpoint is an undocumented website dependency. If it
changes or is unavailable, the existing local-PDF commands remain available.

The September 13–19 eight-page fixture now yields 353 advertised offer groups,
including 23 on its previously unsupported produce page. Its image-only Organic
Wellness Shots banner on page 2 remains omitted; this known coverage warning is
tied to the PDF hash and retained in subsequent reports. The September 6–12
fixture yields 362 offer groups. Counts are regression checks, not proof of
complete extraction. The two actual flyer weeks seed the local history; no
historical prices are fabricated.

## Deal history and seasonal reporting

`deal_history.py` uses SQLite with immutable extraction revisions and one active
revision per flyer date range. Repeating the same content does not add a week;
an extraction correction preserves the previous revision and updates the active
view. Each revision retains its source metadata and full extracted offer fields.
Invalid dates, missing PDF hashes, and non-finite JSON numbers are rejected
before committing a revision. When source page counts are supplied, partial
page sets are rejected as well.

Price comparisons require the same normalized printed name, details, package,
sale unit, and multibuy quantity. Flagged offers, ambiguous variants, duplicate
identities within a week, and unclear package or price terms remain browsable
but are excluded from comparable series. This conservative matching is not a
UPC catalog: wording changes can split a product's history. Charts plot actual
observations and never fill missing weeks. Two captured September weeks do not
establish annual price patterns.

Category charts measure extracted offer groups and their share of a flyer,
not the largest percentage discounts. Monthly values divide category counts by
captured weeks; months without observations are missing data. Weeks belong to
the month of their start date.

The seasonal calendar uses the [USDA SNAP-Ed seasonal produce guide](https://snaped.fns.usda.gov/seasonal-produce-guide)
for a U.S. overview, with selected New England harvest notes based on the
[Massachusetts picking guide](https://www.mass.gov/guides/pick-your-own-farms).
National seasons are displayed as three-month calendar blocks; local partial
months are shown as whole months. Weather and location affect actual timing.
An empty regional row means this guide supplies no local window.
These are availability references, not mandatory grocery pricing standards or
predictions of discounts. The report links the [USDA AMS advertised produce survey](https://mymarketnews.ams.usda.gov/viewReport/3324)
as a future benchmark source; it does not import national prices or claim
comparisons against a national average.

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

## Output fields

Each deal is a JSON object:

| Field      | Description                                        |
|------------|----------------------------------------------------|
| `item`     | Product name (clean, flavor list moved to details)|
| `details`  | Size, flavors, and other qualifiers                |
| `page`     | Zero-based source page, also retained in flat exports |
| `price`    | Primary displayed price, e.g. `4.99`, `99¢`, `2 for $5`; may be null for multiple inline variants |
| `price_n`  | Primary offer amount in dollars; a multibuy stores the total |
| `unit`     | Printed sale unit, such as `lb`, `ea`, or `pkg`; null when absent |
| `savings`  | Printed `Save ...` text, including a printed `/lb` basis |
| `package_sizes` | Printed sizes/counts, separate from the sale unit |
| `quantity`, `amount`, `unit_price` | Offer quantity, total dollars, and arithmetic dollars per item |
| `prices`   | Primary price and explicit package/size alternatives |
| `confidence` | `high` / `medium` / `low` — heuristic review signal |
| `_issues`  | Reasons an offer needs review |
| `_source_text`, `_bbox` | Assigned PDF text and page coordinates for inspection |
| `category`, `category_source` | Reporting category and its official match or estimate basis |

Each `prices` entry retains `label`, `price`, `price_n`, `unit`, `_bbox`, and
the same `quantity`/`amount`/`unit_price` terms. For `2 for $5`, those terms
are `2`, `5.00`, and `2.50`. The arithmetic `unit_price` does not establish
whether buying just one item qualifies for that rate. A null primary price
does not mean the offer has no prices: inspect `prices` for explicit variants.

## Files

- `extract_deals.py` — the extractor (entry point).
- `flyer_source.py` — official-source discovery, validation, and hashed archives.
- `scripts/check_weekly.py` — acquire the current PDF and export its offers.
- `deal_history.py` — immutable weekly revisions and conservative product observations.
- `deal_categories.py` — department matches and labeled category estimates.
- `seasonality.py` — cited U.S. seasonal context and New England harvest notes.
- `reporting.py` — connect dated exports, archived category data, history, and report.
- `dashboard.py`, `web/dashboard.*` — atomic, self-contained HTML report and responsive UI.
- `scripts/build_report.py` — import dated exports or rebuild the report offline.
- `portable_site.py`, `scripts/publish_site.py` — verified portable history and static website export.
- `.github/workflows/weekly-specials.yml` — personal public repository schedule and Pages publication.
- `check_state.py` — successful-build receipts and unchanged-output verification.
- `scripts/run_scheduled_check.py` — bounded scheduled run, overlap lock, logs and status.
- `scripts/manage_schedule.py` — prepare, install, inspect or disable the macOS LaunchAgent.
- `extractor_config.py` — centralized tunable heuristics.
- `layout.py` — vector column boundaries and row separation.
- `name_styles.py` — product-title color/font selection.
- `offer_regions.py` — assign source spans to neighboring offers.
- `pricing.py` — price glyphs, multibuy arithmetic, and explicit variants.
- `offer_fields.py` — details, savings, sale units, and package sizes.
- `json_output.py` — shared atomic JSON writer.
- `config.example.json` — example override config for `--config`.
- `data/page1_deals.py` — compatibility import for the dated page 1 reference.
- `validation.py` — strict offer and field comparisons.
- `tests/fixtures/2026-09-06/` — archived PDF, checksum, and page 1 annotations.
- `tests/fixtures/2026-09-13/` — second-week PDF and targeted layout regressions.
- `scripts/report_quality.py` — full-PDF quality report + consolidated JSON.
- `scripts/run_all.py` — run the extractor across all pages.
- `scripts/validate_page1.py` — validate page 1 against the reference.
- `scripts/render_page.py`, `scripts/crop_page.py` — visual inspection helpers.

## Developing / testing

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
