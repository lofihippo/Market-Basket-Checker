# Market Basket Weekly Checker

Extract the weekly deals from the Market Basket grocery flyer PDF into
structured, machine-readable data.

The flyer is published weekly at `https://www.shopmarketbasket.com/weekly-flyer/`
(the "view classic flyer" link downloads a PDF). This project parses that PDF
and outputs one JSON record per deal, with the item name, details (size/flavor),
price, savings, and a numeric price value.

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

This writes `output/weekly-deals.json`, containing `pages`, source dates and
hashes in `source`, and the extraction method/configuration in `extraction`.
The PDF remains the source of the extracted offers. The official website's
JSON products are archived for comparison; they are not substituted for PDF
results or used as an accuracy denominator.

Download and verify the source without running extraction:

```bash
python scripts/check_weekly.py --fetch-only
```

Use `--source-dir DIR`, `--json-out FILE`, `--timeout SECONDS`, and
`--config FILE` to override the archive, export, request timeout, or extractor
settings. Defaults are `output/source`, `output/weekly-deals.json`, and a
30-second socket timeout. A normal check runs extraction even when source
bytes are unchanged, so extractor improvements are reflected in the export.

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

Live verification on September 13, 2026 successfully acquired the September
13–19 eight-page flyer and matched its printed effective dates. Extraction of
that new flyer exposed a coverage gap: page 2 contains produce specials but
currently yields no offers. The weekly command therefore exits with a review
error and preserves the previous deal export. `--fetch-only` succeeds; support
for the new page layout needs correction before relying on a complete report.

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

Each `prices` entry retains `label`, `price`, `price_n`, `unit`, `_bbox`, and
the same `quantity`/`amount`/`unit_price` terms. For `2 for $5`, those terms
are `2`, `5.00`, and `2.50`. The arithmetic `unit_price` does not establish
whether buying just one item qualifies for that rate. A null primary price
does not mean the offer has no prices: inspect `prices` for explicit variants.

## Files

- `extract_deals.py` — the extractor (entry point).
- `flyer_source.py` — official-source discovery, validation, and hashed archives.
- `scripts/check_weekly.py` — acquire the current PDF and export its offers.
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
