# History

## 2026-05-08

- Initialized the ETF Pullback Alert System as a Python 3.11 Cloud Run service.
- Added FastAPI endpoints `/healthz` and `/run`, KIS market data client, signal engine, Telegram notification, SQLite/Firestore duplicate suppression, Dockerfile, Cloud Build config, `.env.example`, `.gitignore`, README, and unit tests.
- Verified strategy and market-window tests with `C:\Users\yeong\AppData\Local\Programs\Python\Python311\python.exe -m unittest discover -s tests`.
- Initialized a local git repository on branch `main` and prepared the first commit for GitHub publishing.
- Connected `origin` to `https://github.com/younghak9905/etf.git` and pushed `main` to GitHub.
- Updated Docker packaging for Cloud Run continuous deployment: `Dockerfile` now listens on `${PORT:-8080}` and `.dockerignore` excludes local-only files from the Cloud Build context.
- Replaced Telegram notification settings with Discord Webhook notification via `DISCORD_WEBHOOK_URL`.
- Created local ignored `.env` with non-secret Cloud Run runtime defaults for production testing.
- Added a generated local `SCHEDULER_TOKEN` to the ignored `.env` file for Cloud Scheduler authentication.
- Added a simple `/` HTML smoke-test page for Cloud Run browser verification.
- Added `/health` as the Cloud Run-compatible health endpoint and kept `/healthz` only for local compatibility because Cloud Run can reserve paths ending in `z`.
- Hardened KIS overseas quote parsing so QLD can fall back from missing `last` to alternate price fields and report available fields on normalization errors.
- Added SQLite/Firestore KIS access token caching and 403 response body logging to reduce repeated `/oauth2/tokenP` calls across Cloud Run cold starts and revisions.
- Documented that Firestore uses the Cloud Run service account and default project database through `google.cloud.firestore.AsyncClient()`.
- Added a per-client token acquisition lock and overseas quote fallback to the latest daily candle when KIS returns empty `last`/`base` values.
- Added Firestore configuration and connectivity status to the `/` smoke-test page.
- Made KIS overseas daily parsing accept `output` as well as `output2` and report payload keys when daily rows are empty.
- Set KIS overseas daily `BYMD` explicitly and expanded empty-row diagnostics with payload shapes.
- Changed QLD's KIS exchange code from `NAS` to `AMS` because QLD is listed on NYSE Arca rather than Nasdaq.
- Established the workflow that future development should be verified with Docker Desktop first, then pushed to GitHub after completion.
- Added `POST /test-notification` to send a Discord webhook test message using the existing scheduler token authentication.
- Added SOXX as a watched US ETF using KIS exchange code `NAS`.
- Improved Discord signal messages with change, gap, volume ratio, and quote-source details; corrected overseas intraday quote fallback to preserve live price fields; added structured per-instrument and per-run summary logs.
- Added latest `/run` summary persistence with `/last-run` JSON output and root-page display of active symbols, signal counts, sent/suppressed counts, errors, and no-alert reason.
