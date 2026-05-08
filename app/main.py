from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request

from app.config.settings import Settings
from app.models.market import Signal
from app.notification.telegram import TelegramNotifier
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
    app.state.notifier = TelegramNotifier(settings)
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


def get_notifier(request: Request) -> TelegramNotifier:
    return request.app.state.notifier


@app.get("/healthz")
async def healthz(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


@app.post("/run")
async def run_alert_cycle(
    x_scheduler_token: str | None = Header(default=None),
    token: str | None = Query(default=None),
    settings: Settings = Depends(get_settings),
    market_data: MarketDataService = Depends(get_market_data),
    storage: AlertStorage = Depends(get_storage),
    engine: SignalEngine = Depends(get_engine),
    notifier: TelegramNotifier = Depends(get_notifier),
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
