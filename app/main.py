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
async def root(settings: Settings = Depends(get_settings)) -> str:
    firestore_status = await _firestore_status(settings)
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
        logger.info("no_active_market_window")
        return {"status": "skipped", "reason": "outside_market_windows", "signals": []}

    sent: list[Signal] = []
    suppressed: list[Signal] = []
    errors: list[dict[str, str]] = []

    for instrument in active:
        try:
            snapshot = await market_data.get_snapshot(instrument)
            signals = engine.evaluate(snapshot)
            for signal in signals:
                if await storage.should_send(signal, settings.duplicate_window_minutes):
                    await notifier.send(signal)
                    await storage.record_sent(signal)
                    sent.append(signal)
                else:
                    suppressed.append(signal)
        except Exception as exc:
            logger.exception(
                "instrument_cycle_failed", extra={"symbol": instrument.symbol}
            )
            errors.append({"symbol": instrument.symbol, "error": str(exc)})

    return {
        "status": "ok" if not errors else "partial_error",
        "active_symbols": [instrument.symbol for instrument in active],
        "sent": [_serialize_signal(signal) for signal in sent],
        "suppressed": [_serialize_signal(signal) for signal in suppressed],
        "errors": errors,
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
        reload=os.getenv("APP_ENV") == "local",
    )
