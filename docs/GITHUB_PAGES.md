# GitHub Pages and weekly updates

This edition targets the personal repository
[`lofihippo/Market-Basket-Checker`](https://github.com/lofihippo/Market-Basket-Checker).
The live site is [Market Basket Weekly Specials](https://lofihippo.github.io/Market-Basket-Checker/).
For local installation, start with the [README](../README.md).

## One-time setup

1. Keep the repository under the **personal `lofihippo` account** and make it
   **public**. Free-account Pages hosting requires a public repository.
2. In this repository's Settings → Pages, choose **GitHub Actions** as the source.
3. Enable GitHub Actions for this repository, allowing the official `actions/*`
   actions used by `.github/workflows/weekly-specials.yml`.
4. Open Actions → **Update weekly specials** → **Run workflow**, using `main`.
5. Confirm both Build and Deploy succeed, then open the website address above.

The workflow runs on pushes to `main`, manual runs, **Sunday at 5 PM Eastern**,
and a **Monday 9:15 AM Eastern** follow-up. The explicit `America/New_York`
time zone follows daylight saving time. Each run retries a failed flyer check
up to three times before stopping. GitHub may delay or drop scheduled jobs under
load and disables public-repository schedules after 60 days without activity.
The manual workflow remains the recovery path.
[GitHub scheduling documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).

## Free-account and organization boundaries

- Both jobs require the exact repository name above and `private == false`
  **before a runner starts**. Organization copies, other forks, and private
  copies do not run this workflow automatically.
- Only standard `ubuntu-latest` GitHub-hosted runners are used. No larger
  runners, self-hosted runners, organization runner groups, packages, paid
  hosting, AI APIs, or organization secrets are configured.
- Dependencies are installed without a persistent Actions cache. The site is
  limited to 25 MiB before upload. Deployment artifacts expire after one day
  and are deleted immediately after the deployment attempt when cleanup runs.
- Only the automatic repository-scoped `GITHUB_TOKEN` is used. Build can write
  the history branch; Deploy can publish Pages and delete its own temporary
  artifact. No personal access token must be stored in the repository.
- The source archive stops growing automatically at 800 MiB. Reaching either
  size limit fails the run and preserves the live site; it never upgrades a
  plan or enables paid capacity. Git history can occupy more than the current
  archive, so review repository size as years of flyers accumulate.

Public-repository standard runners and public Pages are available free. Storage
allowances still apply across the account; this project does not change any
account billing, spending limits, or organization settings.
[GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits),
[Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions).

## What the workflow preserves

The `weekly-history` branch contains `archive/archive.json`, one verified JSON
export per flyer date range, and content-addressed source PDFs/API responses.
Corrections are versioned by Git commits. It contains only public flyer data;
the exporter removes machine-specific source paths. SQLite is a local working
database rebuilt from that archive on each run. Failed imports cannot replace
an existing database, and failed source checks never deploy a replacement site.

The website is a self-contained `index.html`; its PDF links point to hashed
files on the data branch. Price history and category filters work entirely in
the browser. The build saves history before deploying, so a failed Pages step
can be recovered by running the workflow again. If the PDF layout changes and
extraction fails, fix the extractor before retrying; the previous site survives.

The two dated fixtures can seed the initial archive from the existing local
database. Later runs preserve those weeks and add real observations. A fresh
fork without a history branch starts with its first successfully captured week.

## Clone, export, and self-host

The normal local flow remains:

```bash
python scripts/check_weekly.py
python scripts/publish_site.py site --directory output/site
python -m http.server 8766 --bind 127.0.0.1 --directory output/site
```

Open `http://127.0.0.1:8766/`. This export includes the PDFs for offline use and
can be copied as a folder to any static web server. Repeat the first two commands
to update it, using a scheduler on that machine. `check_weekly.py` still generates
the original `output/report.html` as well. An already-open browser tab needs a
reload to display the rebuilt file. The [local Mac schedule](REFERENCE.md#scheduled-checks-on-macos) is configured
separately; enabling GitHub does not change it.

To restore the hosted archive into a separate local database:

```bash
git clone --branch weekly-history --single-branch https://github.com/lofihippo/Market-Basket-Checker.git output/history-store
python scripts/publish_site.py restore --directory output/history-store/archive --history-db output/hosted-history.sqlite3
python scripts/publish_site.py site --history-db output/hosted-history.sqlite3 --directory output/hosted-site
```

To keep a portable backup of a local archive:

```bash
python scripts/publish_site.py archive --directory output/history-backup
```

Do not delete the hosted history branch as a way to clear a failed build.

## Personal forks

Fork to a **personal public repository**, then deliberately replace the exact
repository guard in both workflow jobs and in the artifact cleanup step with
your own `username/repository`. Enable Pages and run the workflow as above.
Keep the public-repository check, standard runner, size limits, and artifact
cleanup. Copying the code into an organization does not silently enable jobs.
