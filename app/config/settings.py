from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from app.models.market import Instrument, Market


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    app_env: str
    timezone: str
    market_data_mode: str
    kis_base_url: str
    kis_app_key: str | None
    kis_app_secret: str | None
    kis_token_buffer_seconds: int
    request_timeout_seconds: float
    scheduler_token: str | None
    discord_webhook_url: str | None
    duplicate_window_minutes: int
    storage_backend: str
    sqlite_path: Path
    firestore_collection: str
    us_watch_windows: str
    kr_watch_windows: str
    alert_dry_run: bool
    log_level: str

    @property
    def instruments(self) -> list[Instrument]:
        return [
            Instrument(
                symbol="QLD",
                name="ProShares Ultra QQQ",
                market=Market.US,
                exchange="NAS",
                kis_code="QLD",
            ),
            Instrument(
                symbol="133690",
                name="TIGER 미국나스닥100",
                market=Market.KR,
                exchange="KRX",
                kis_code="133690",
            ),
            Instrument(
                symbol="379800",
                name="KODEX 미국S&P500",
                market=Market.KR,
                exchange="KRX",
                kis_code="379800",
            ),
        ]

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            app_env=os.getenv("APP_ENV", "local"),
            timezone=os.getenv("APP_TIMEZONE", "Asia/Seoul"),
            market_data_mode=os.getenv("MARKET_DATA_MODE", "kis").lower(),
            kis_base_url=os.getenv(
                "KIS_BASE_URL", "https://openapi.koreainvestment.com:9443"
            ).rstrip("/"),
            kis_app_key=os.getenv("KIS_APP_KEY"),
            kis_app_secret=os.getenv("KIS_APP_SECRET"),
            kis_token_buffer_seconds=int(os.getenv("KIS_TOKEN_BUFFER_SECONDS", "300")),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "7")),
            scheduler_token=os.getenv("SCHEDULER_TOKEN"),
            discord_webhook_url=os.getenv("DISCORD_WEBHOOK_URL"),
            duplicate_window_minutes=int(os.getenv("DUPLICATE_WINDOW_MINUTES", "30")),
            storage_backend=os.getenv("STORAGE_BACKEND", "sqlite").lower(),
            sqlite_path=Path(os.getenv("SQLITE_PATH", "/tmp/etf_alerts.db")),
            firestore_collection=os.getenv(
                "FIRESTORE_COLLECTION", "etf_signal_notifications"
            ),
            us_watch_windows=os.getenv("US_WATCH_WINDOWS", "17:00-00:00"),
            kr_watch_windows=os.getenv("KR_WATCH_WINDOWS", "09:00-10:00,11:30-13:00"),
            alert_dry_run=_bool_env("ALERT_DRY_RUN", False),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )

    def validate_runtime(self) -> None:
        if self.market_data_mode == "kis" and (
            not self.kis_app_key or not self.kis_app_secret
        ):
            raise ValueError("KIS_APP_KEY and KIS_APP_SECRET are required")

        if not self.alert_dry_run and not self.discord_webhook_url:
            raise ValueError(
                "DISCORD_WEBHOOK_URL is required unless ALERT_DRY_RUN=true"
            )
