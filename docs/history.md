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
