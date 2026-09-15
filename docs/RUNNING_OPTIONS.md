# How people can use Market Basket Weekly Specials

One Python collector and one HTML renderer support a shared website, a personal
GitHub copy, and a local installation. The browser shows the last generated
report; Python fetches the flyer and updates the archive.

| Option | User experience | Setup |
|---|---|---|
| Shared website | Open a link on a phone or computer; no account needed. | The owner enables Pages and the included Actions workflow. |
| Personal GitHub copy | Own a separate site and weekly archive. | Fork to a personal public repository, adjust the explicit repository guards, and enable Pages. |
| Local or self-hosted | Keep the database on your own machine and serve the same interface. | Install Python dependencies, run the checker, and export the portable site. |
| Local GUI updater | Click an Update button inside a local app. | Future enhancement: a local service and launcher are needed. |

See [GitHub Pages and weekly updates](GITHUB_PAGES.md) for the implemented
workflow, Sunday 5 PM Eastern schedule, free-account limits, and exact commands.
Hosting still requires a public repository, Pages configuration, and a successful
first deployment. Organization copies and private copies are blocked before a
workflow runner starts.

## How updates work

The hosted workflow restores the dedicated `weekly-history` branch, verifies
and extracts the official PDF, records the week, builds the report, saves history,
and deploys Pages. It keeps the prior live report if extraction fails. The
history branch holds public source PDFs and portable weekly JSON; Git versions
corrections and SQLite is rebuilt for each runner. Deployment artifacts are
short-lived and are not used as the archive.

Locally, `python scripts/check_weekly.py` generates `output/report.html` and
updates `output/history.sqlite3`. `python scripts/publish_site.py site
--directory output/site` creates an `index.html` with packaged PDF sources for
hosting or offline use. The installed Mac LaunchAgent remains a separate local
scheduler. The browser does not need to stay open for either scheduler.

The extractor and renderer do not call AI APIs or consume AI usage credits.
A localhost address is reachable only on the computer serving it. Shared access
requires publishing the portable folder with a web server or using Pages.

## A future local GUI

A launcher could start a Python service on `127.0.0.1`, open the browser, and
provide an Update weekly flyer button with progress and error states. It would
reuse the collector and overlap lock, accept only a fixed update operation,
validate request origins, and preserve the last successful report during a run.
This service and a packaged installer are not implemented. Windows packaging
would also need a compatible scheduler/process lock and IANA time-zone data.
A static Pages site cannot run the Python collector when a shopper clicks it.
