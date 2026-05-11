# ETF Pullback Alert System

QLD, TIGER 미국나스닥100(133690), KODEX 미국S&P500(379800)의 저점/눌림목 구간을 KIS Open API로 감시하고 Discord로 알림을 보내는 Cloud Run 서비스입니다. 목표는 자동매매가 아니라 장기 적립식 투자에서 상대적으로 유리한 매수 후보 구간을 알려주는 것입니다.

## Architecture

```text
Cloud Scheduler
  -> Cloud Run /run
  -> KIS Open API
  -> Signal Engine
  -> SQLite or Firestore duplicate gate
  -> Discord Webhook
```

Cloud Scheduler는 1분마다 하나의 `/run` 엔드포인트만 호출합니다. 서비스 내부에서 한국/미국 감시 시간대를 검사하므로 Scheduler Job 수를 줄일 수 있습니다.

## Signals

| Signal | Condition |
| --- | --- |
| `PULLBACK_BUY_SIGNAL` | `MA20 > MA60`, current price near MA20, RSI 40~50, volume below volume MA |
| `BUY_CANDIDATE` | current price within 0.5% of weekly low |
| `SIDEWAYS_RANGE_BUY` | sideways market and current price within 0.2% of range low |
| `CAUTION` | price down 3% from previous close and volume above 1.5x volume MA |

Market state is classified as `CRASH`, `SIDEWAYS`, `UPTREND`, `DOWNTREND`, or `UNKNOWN`.

Discord signal messages include previous-close change, MA20 gap, weekly-low gap,
range-low gap, volume ratio, and the KIS quote source used for the calculation.
Each `/run` also emits structured `instrument_cycle_completed` and
`run_cycle_completed` logs with active symbol, signal, sent, suppressed, error,
and duration counts.

## Environment

Copy `.env.example` and set secrets:

```text
KIS_APP_KEY=
KIS_APP_SECRET=
SCHEDULER_TOKEN=
DISCORD_WEBHOOK_URL=
```

Important options:

| Variable | Default | Description |
| --- | --- | --- |
| `MARKET_DATA_MODE` | `kis` | Use `mock` for local smoke tests without KIS credentials |
| `KIS_TOKEN_CACHE_BACKEND` | same as `STORAGE_BACKEND` | Use `firestore` in Cloud Run to share KIS access tokens across instances |
| `ALERT_DRY_RUN` | `false` | Log Discord messages without sending |
| `STORAGE_BACKEND` | `sqlite` | Use `firestore` for duplicate suppression across Cloud Run instances |
| `US_WATCH_WINDOWS` | `17:00-00:00` | KST watch window for QLD and SOXX |
| `KR_WATCH_WINDOWS` | `09:00-10:00,11:30-13:00` | KST watch windows for Korean ETFs |

For production Cloud Run, prefer `STORAGE_BACKEND=firestore` if duplicate suppression must survive cold starts and multiple instances. For lowest cost and single-instance operation, SQLite in `/tmp` is sufficient but not durable across instance replacement.

For KIS, prefer `KIS_TOKEN_CACHE_BACKEND=firestore` in Cloud Run. KIS access tokens are cached per App Key and base URL so cold starts and new revisions can reuse a valid token instead of calling `/oauth2/tokenP` every run.

Firestore does not need a database URL in Cloud Run. The app uses `google.cloud.firestore.AsyncClient()`, which connects to the default Firestore database in the active GCP project through the Cloud Run service account. Create Firestore in Native mode and grant the Cloud Run service account `Cloud Datastore User`.

## Local Run

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:MARKET_DATA_MODE="mock"
$env:ALERT_DRY_RUN="true"
uvicorn app.main:app --reload --port 8080
```

Open the root page for a browser smoke test:

```text
http://localhost:8080/
```

The root page also shows whether Firestore is configured and whether a short Firestore read check succeeds.
It also displays the latest `/run` summary, including active symbols, signal
count, sent count, suppressed count, errors, and the reason no alert was sent.

Health check:

```text
http://localhost:8080/health
```

Trigger manually:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/run"
```

If `SCHEDULER_TOKEN` is set:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/run" -Headers @{"X-Scheduler-Token"="change-me"}
```

Test Discord webhook delivery without waiting for a signal:

```powershell
Invoke-RestMethod -Method Post "http://localhost:8080/test-notification" -Headers @{"X-Scheduler-Token"="change-me"}
```

Read the latest run summary as JSON:

```powershell
Invoke-RestMethod -Method Get "http://localhost:8080/last-run"
```

## Docker

```powershell
docker build -t etf-pullback-alert .
docker run --rm -p 8080:8080 --env-file .env etf-pullback-alert
```

Development workflow:

```powershell
docker build -t etf-pullback-alert:dev .
docker run --rm -p 8080:8080 --env-file .env etf-pullback-alert:dev
```

Use Docker Desktop as the default verification path before pushing completed work to GitHub.

## Deploy To Cloud Run

Create an Artifact Registry repository once:

```powershell
gcloud artifacts repositories create etf-alert `
  --repository-format=docker `
  --location=asia-northeast3
```

Build and deploy:

```powershell
gcloud builds submit --config cloudbuild.yaml .
```

Set runtime environment variables:

```powershell
gcloud run services update etf-pullback-alert `
  --region=asia-northeast3 `
  --set-env-vars APP_ENV=prod,MARKET_DATA_MODE=kis,STORAGE_BACKEND=firestore,ALERT_DRY_RUN=false `
  --set-secrets KIS_APP_KEY=KIS_APP_KEY:latest,KIS_APP_SECRET=KIS_APP_SECRET:latest,DISCORD_WEBHOOK_URL=DISCORD_WEBHOOK_URL:latest,SCHEDULER_TOKEN=SCHEDULER_TOKEN:latest
```

Create the Scheduler job:

```powershell
gcloud scheduler jobs create http etf-pullback-alert-every-minute `
  --location=asia-northeast3 `
  --schedule="* * * * *" `
  --uri="https://YOUR_CLOUD_RUN_URL/run" `
  --http-method=POST `
  --headers="X-Scheduler-Token=YOUR_TOKEN" `
  --time-zone="Asia/Seoul"
```

## Test

```powershell
python -m unittest discover -s tests
```

## Notes

- KIS 국내 현재가 API는 `uapi/domestic-stock/v1/quotations/inquire-price`, 해외 현재가는 `uapi/overseas-price/v1/quotations/price`를 사용합니다.
- Cloud Run에서는 `/healthz` 같은 일부 `z`로 끝나는 경로가 예약 경로와 충돌할 수 있으므로 외부 헬스체크는 `/health`를 사용합니다.
- KIS 호출은 초당 제한을 고려해 동시성을 낮게 유지하고 실패 시 exponential backoff로 재시도합니다.
- Cloud Run 비용 최소화를 위해 `min-instances=0`, `max-instances=1`을 기본 배포값으로 둡니다.
