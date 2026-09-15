# How it works

[Back to the README](../README.md) · [Command reference](REFERENCE.md) ·
[GitHub deployment](GITHUB_PAGES.md)

Python downloads and parses the official Market Basket flyer, records dated
observations, and generates a static HTML report. The browser displays that
report; downloading and extraction happen on your computer or a GitHub Actions
runner.

## Pipeline

1. **Acquire:** discover the current PDF from the official weekly-flyer endpoint,
   validate it, and archive the original PDF and metadata by content hash.
2. **Extract:** identify offer regions, product names, prices, and package details
   from the PDF's text and drawings. Attach review flags to uncertain results.
3. **Organize:** match official website departments where possible and label
   estimated categories. Store dated offers and comparable price observations.
4. **Report:** generate the category cards, price history, and seasonal calendar
   as a self-contained HTML file.
5. **Publish:** optionally export a portable static site. GitHub Actions preserves
   the archive on the `weekly-history` branch and deploys the report to Pages.

## The report

After `python scripts/check_weekly.py` finishes, open `output/report.html`. It includes
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

## Flyer layouts

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

## Source acquisition and archives

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

## Code map

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

## Accuracy and limitations

Extraction uses layout and text heuristics. Image-only brands or offers can be
missed, and new flyer layouts can require code or configuration changes. Review
flagged offers and confirm purchases against the original flyer.

The strict annotated cover-page comparison currently reports discrepancies,
even though the unit tests pass. Offer counts and confidence labels do not prove
complete extraction. See [validation and known discrepancies](REFERENCE.md#developing-and-testing)
for the fixtures, checks, and current limitations.
