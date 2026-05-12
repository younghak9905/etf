from __future__ import annotations

import asyncio
import html
import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from app.config.settings import Settings
from app.models.market import Signal
from app.notification.discord import DiscordNotifier
from app.scheduler.windows import is_market_window_open
from app.services.market_data import MarketDataService, build_market_data_service
from app.services.storage import AlertStorage, build_alert_storage
from app.strategies.signal_engine import SignalEngine
from app.utils.time import to_local_iso


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "time": datetime.now(UTC).isoformat(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key, value in record.__dict__.items():
            if key not in {
                "args",
                "asctime",
                "created",
                "exc_info",
                "exc_text",
                "filename",
                "funcName",
                "levelname",
                "levelno",
                "lineno",
                "module",
                "msecs",
                "message",
                "msg",
                "name",
                "pathname",
                "process",
                "processName",
                "relativeCreated",
                "stack_info",
                "thread",
                "threadName",
            }:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    configure_logging(settings.log_level)
    app.state.settings = settings
    app.state.engine = SignalEngine()
    app.state.market_data = build_market_data_service(settings)
    app.state.storage = build_alert_storage(settings)
    app.state.notifier = DiscordNotifier(settings)
    yield
    await app.state.market_data.close()


app = FastAPI(title="ETF Pullback Alert System", version="0.1.0", lifespan=lifespan)
logger = logging.getLogger(__name__)


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_market_data(request: Request) -> MarketDataService:
    return request.app.state.market_data


def get_storage(request: Request) -> AlertStorage:
    return request.app.state.storage


def get_engine(request: Request) -> SignalEngine:
    return request.app.state.engine


def get_notifier(request: Request) -> DiscordNotifier:
    return request.app.state.notifier


@app.get("/", response_class=HTMLResponse)
async def root(
    settings: Settings = Depends(get_settings),
    storage: AlertStorage = Depends(get_storage),
) -> str:
    firestore_status = await _firestore_status(settings)
    last_run = await _safe_last_run_summary(storage)
    last_run_html = _last_run_html(last_run, settings.timezone)
    return f"""
    <!doctype html>
    <html lang="en">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>ETF Pullback Alert</title>
        <style>
          :root {{
            color-scheme: light dark;
            font-family: Arial, sans-serif;
          }}
          body {{
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            background: #f6f7f9;
            color: #171717;
          }}
          main {{
            width: min(680px, calc(100% - 32px));
            border: 1px solid #d9dde3;
            border-radius: 8px;
            background: #ffffff;
            padding: 28px;
            box-sizing: border-box;
          }}
          h1 {{
            margin: 0 0 12px;
            font-size: 28px;
            line-height: 1.2;
          }}
          p {{
            margin: 8px 0;
            line-height: 1.5;
          }}
          ul {{
            margin: 8px 0 0 20px;
            padding: 0;
          }}
          li {{
            margin: 4px 0;
          }}
          code {{
            background: #eef1f5;
            border-radius: 4px;
            padding: 2px 6px;
          }}
          .status {{
            display: inline-block;
            margin: 12px 0 18px;
            padding: 6px 10px;
            border-radius: 999px;
            background: #e7f7ed;
            color: #116b34;
            font-weight: 700;
          }}
          dl {{
            display: grid;
            grid-template-columns: 160px 1fr;
            gap: 8px 12px;
            margin: 16px 0;
          }}
          dt {{
            color: #5f6876;
          }}
          dd {{
            margin: 0;
          }}
          a {{
            color: #155bd5;
          }}
          @media (prefers-color-scheme: dark) {{
            body {{
              background: #101214;
              color: #f2f3f5;
            }}
            main {{
              background: #181b1f;
              border-color: #30363d;
            }}
            code {{
              background: #252a31;
            }}
          .status {{
              background: #163b24;
              color: #7ee2a0;
            }}
            dt {{
              color: #a8b0bc;
            }}
            a {{
              color: #8ab4ff;
            }}
          }}
        </style>
      </head>
      <body>
        <main>
          <h1>ETF Pullback Alert System</h1>
          <div class="status">Service is running</div>
          <dl>
            <dt>Environment</dt>
            <dd><code>{html.escape(settings.app_env)}</code></dd>
            <dt>Storage backend</dt>
            <dd><code>{html.escape(settings.storage_backend)}</code></dd>
            <dt>KIS token cache</dt>
            <dd><code>{html.escape(settings.kis_token_cache_backend)}</code></dd>
            <dt>Firestore</dt>
            <dd><code>{html.escape(firestore_status)}</code></dd>
          </dl>
          <p>Health endpoint: <a href="/health">/health</a></p>
          <p>Scheduler endpoint: <code>POST /run</code></p>
          <p>Discord test endpoint: <code>POST /test-notification</code></p>
          <h2>Last Run</h2>
          {last_run_html}
        </main>
      </body>
    </html>
    """


@app.get("/healthz")
async def healthz(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


@app.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


async def _firestore_status(settings: Settings) -> str:
    uses_firestore = (
        settings.storage_backend == "firestore"
        or settings.kis_token_cache_backend == "firestore"
    )
    if not uses_firestore:
        return "not configured"

    try:
        from google.cloud import firestore

        client = firestore.AsyncClient()
        query = client.collection(settings.firestore_collection).limit(1)
        await asyncio.wait_for(query.get(), timeout=3)
        return "connected"
    except Exception as exc:
        return f"error: {type(exc).__name__}: {str(exc)[:160]}"


@app.get("/last-run")
async def last_run(storage: AlertStorage = Depends(get_storage)) -> dict[str, Any]:
    summary = await storage.get_last_run_summary()
    return {"status": "ok", "last_run": summary}


@app.post("/run")
async def run_alert_cycle(
    x_scheduler_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    market_data: MarketDataService = Depends(get_market_data),
    storage: AlertStorage = Depends(get_storage),
    engine: SignalEngine = Depends(get_engine),
    notifier: DiscordNotifier = Depends(get_notifier),
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    _authorize(settings, x_scheduler_token, token)
    settings.validate_runtime()

    now = datetime.now(UTC)
    active = [
        instrument
        for instrument in settings.instruments
        if is_market_window_open(
            instrument.market,
            now,
            settings.timezone,
            settings.us_watch_windows,
            settings.kr_watch_windows,
        )
    ]

    if not active:
        duration_ms = _duration_ms(started_at)
        summary = _run_summary(
            status="skipped",
            started_at=started_at,
            timezone_name=settings.timezone,
            active=[],
            sent=[],
            suppressed=[],
            errors=[],
            signal_count=0,
            duration_ms=duration_ms,
            reason="outside_market_windows",
            no_alert_reason="outside_market_windows",
        )
        await _record_run_summary(storage, summary)
        logger.info("run_cycle_completed", extra=summary)
        logger.info("no_active_market_window")
        return {"status": "skipped", "reason": "outside_market_windows", "signals": []}

    sent: list[Signal] = []
    suppressed: list[Signal] = []
    errors: list[dict[str, str]] = []
    signal_count = 0

    for instrument in active:
        try:
            snapshot = await market_data.get_snapshot(instrument)
            signals = engine.evaluate(snapshot)
            signal_count += len(signals)
            for signal in signals:
                if await storage.should_send(signal, settings.duplicate_window_minutes):
                    await notifier.send(signal)
                    await storage.record_sent(signal)
                    sent.append(signal)
                else:
                    suppressed.append(signal)
            logger.info(
                "instrument_cycle_completed",
                extra={
                    "symbol": instrument.symbol,
                    "market": instrument.market.value,
                    "signal_count": len(signals),
                    "sent_count": len(
                        [signal for signal in sent if signal.instrument == instrument]
                    ),
                    "suppressed_count": len(
                        [
                            signal
                            for signal in suppressed
                            if signal.instrument == instrument
                        ]
                    ),
                    "quote_source": snapshot.quote_source,
                    "current_price": snapshot.current_price,
                },
            )
        except Exception as exc:
            logger.exception(
                "instrument_cycle_failed", extra={"symbol": instrument.symbol}
            )
            errors.append({"symbol": instrument.symbol, "error": str(exc)})

    status = "ok" if not errors else "partial_error"
    no_alert_reason = _no_alert_reason(
        active=active,
        signal_count=signal_count,
        sent_count=len(sent),
        suppressed_count=len(suppressed),
        errors=errors,
    )
    response = {
        "status": status,
        "active_symbols": [instrument.symbol for instrument in active],
        "sent": [_serialize_signal(signal) for signal in sent],
        "suppressed": [_serialize_signal(signal) for signal in suppressed],
        "errors": errors,
        "no_alert_reason": no_alert_reason,
    }
    summary = _run_summary(
        status=status,
        started_at=started_at,
        timezone_name=settings.timezone,
        active=active,
        sent=sent,
        suppressed=suppressed,
        errors=errors,
        signal_count=signal_count,
        duration_ms=_duration_ms(started_at),
        no_alert_reason=no_alert_reason,
    )
    await _record_run_summary(storage, summary)
    logger.info("run_cycle_completed", extra=summary)
    return response


@app.post("/test-notification")
async def test_notification(
    x_scheduler_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    notifier: DiscordNotifier = Depends(get_notifier),
) -> dict[str, Any]:
    _authorize(settings, x_scheduler_token, token)
    result = await notifier.send_test()
    return {
        "status": "ok",
        "notification": result,
        "dry_run": settings.alert_dry_run,
    }


def _authorize(settings: Settings, header_token: str | None, query_token: str | None) -> None:
    expected = settings.scheduler_token
    if not expected:
        return
    if expected not in {header_token, query_token}:
        raise HTTPException(status_code=401, detail="invalid scheduler token")


def _serialize_signal(signal: Signal) -> dict[str, Any]:
    return {
        "symbol": signal.instrument.symbol,
        "name": signal.instrument.name,
        "signal_type": signal.signal_type.value,
        "market_state": signal.market_state.value,
        "current_price": signal.current_price,
        "reasons": signal.reasons,
        "metrics": signal.metrics,
        "observed_at": signal.observed_at.isoformat(),
    }


def _duration_ms(started_at: datetime) -> int:
    return int((datetime.now(UTC) - started_at).total_seconds() * 1000)


async def _record_run_summary(storage: AlertStorage, summary: dict[str, Any]) -> None:
    try:
        await storage.record_run_summary(summary)
    except Exception as exc:
        logger.warning("run_summary_record_failed", extra={"error": str(exc)})


async def _safe_last_run_summary(storage: AlertStorage) -> dict[str, Any] | None:
    try:
        return await storage.get_last_run_summary()
    except Exception as exc:
        return {"status": "error", "no_alert_reason": f"last_run_read_failed: {exc}"}


def _run_summary(
    *,
    status: str,
    started_at: datetime,
    timezone_name: str,
    active: list,
    sent: list[Signal],
    suppressed: list[Signal],
    errors: list[dict[str, str]],
    signal_count: int,
    duration_ms: int,
    reason: str | None = None,
    no_alert_reason: str | None = None,
) -> dict[str, Any]:
    completed_at = datetime.now(UTC)
    return {
        "status": status,
        "reason": reason,
        "no_alert_reason": no_alert_reason,
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "timezone": timezone_name,
        "started_at_local": to_local_iso(started_at, timezone_name),
        "completed_at_local": to_local_iso(completed_at, timezone_name),
        "active_symbols": [instrument.symbol for instrument in active],
        "active_count": len(active),
        "signal_count": signal_count,
        "sent_count": len(sent),
        "suppressed_count": len(suppressed),
        "error_count": len(errors),
        "duration_ms": duration_ms,
        "sent_signals": [signal.key for signal in sent],
        "suppressed_signals": [signal.key for signal in suppressed],
        "errors": errors,
    }


def _no_alert_reason(
    *,
    active: list,
    signal_count: int,
    sent_count: int,
    suppressed_count: int,
    errors: list[dict[str, str]],
) -> str | None:
    if not active:
        return "outside_market_windows"
    if errors and signal_count == 0:
        return "all_active_symbols_failed"
    if sent_count > 0:
        return None
    if signal_count == 0:
        return "no_signal_conditions_met"
    if suppressed_count > 0:
        return "duplicate_alert_suppressed"
    return "no_alert_sent"


def _last_run_html(summary: dict[str, Any] | None, timezone_name: str) -> str:
    if not summary:
        return "<p>No run has been recorded yet.</p>"

    completed_at = summary.get("completed_at") or summary.get("updated_at")
    completed_at_local = summary.get("completed_at_local")
    if not completed_at_local and completed_at:
        try:
            completed_at_local = to_local_iso(completed_at, timezone_name)
        except (TypeError, ValueError):
            completed_at_local = completed_at

    rows = [
        ("Status", summary.get("status")),
        ("Completed (local)", completed_at_local),
        ("Completed (UTC)", completed_at),
        ("Timezone", summary.get("timezone") or timezone_name),
        ("Active symbols", ", ".join(summary.get("active_symbols") or [])),
        ("Signals", summary.get("signal_count")),
        ("Sent", summary.get("sent_count")),
        ("Suppressed", summary.get("suppressed_count")),
        ("Errors", summary.get("error_count")),
        ("No alert reason", summary.get("no_alert_reason")),
        ("Duration", f"{summary.get('duration_ms')} ms"),
    ]
    items = "\n".join(
        f"<li><strong>{html.escape(label)}:</strong> {html.escape(str(value if value is not None else ''))}</li>"
        for label, value in rows
    )
    return f"<ul>{items}</ul>"


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=os.getenv("APP_ENV") == "local",
    )
