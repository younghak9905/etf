from __future__ import annotations

import sys
import types
from pathlib import Path
from datetime import UTC, datetime
from unittest import IsolatedAsyncioTestCase

sys.modules.setdefault(
    "httpx",
    types.SimpleNamespace(AsyncClient=object),
)

from app.config.settings import Settings
from app.models.market import Instrument, Market, MarketState, Signal, SignalType
from app.notification.discord import DiscordNotifier


class DiscordNotifierTest(IsolatedAsyncioTestCase):
    async def test_send_test_respects_dry_run(self) -> None:
        notifier = DiscordNotifier(_settings(alert_dry_run=True))

        result = await notifier.send_test()

        self.assertEqual(result, "dry_run")

    async def test_signal_payload_includes_operational_metrics(self) -> None:
        signal = Signal(
            instrument=Instrument("QLD", "ProShares Ultra QQQ", Market.US, "AMS", "QLD"),
            signal_type=SignalType.BUY_CANDIDATE,
            market_state=MarketState.UPTREND,
            current_price=100.0,
            reasons=["주간 저점 근접"],
            metrics={
                "ma20": 99.0,
                "ma60": 92.0,
                "rsi": 44.0,
                "week_low": 99.8,
                "prev_close_change_pct": -1.25,
                "ma20_gap_pct": 1.01,
                "week_low_gap_pct": 0.2,
                "range_low_gap_pct": 0.4,
                "volume_ratio": 0.82,
                "quote_source": "intraday_quote_with_daily_fallback",
            },
            observed_at=datetime.now(UTC),
        )

        payload = DiscordNotifier._payload(signal)

        self.assertIn("전일대비", payload["content"])
        self.assertIn("-1.25%", payload["content"])
        self.assertIn("0.82x", payload["content"])
        self.assertIn("intraday_quote_with_daily_fallback", payload["content"])


def _settings(*, alert_dry_run: bool) -> Settings:
    return Settings(
        app_env="test",
        timezone="Asia/Seoul",
        market_data_mode="mock",
        kis_base_url="https://openapi.koreainvestment.com:9443",
        kis_app_key=None,
        kis_app_secret=None,
        kis_token_buffer_seconds=300,
        kis_token_cache_backend="sqlite",
        kis_token_cache_collection="kis_access_tokens",
        request_timeout_seconds=7,
        scheduler_token="token",
        discord_webhook_url=None,
        duplicate_window_minutes=30,
        storage_backend="sqlite",
        sqlite_path=Path(":memory:"),
        firestore_collection="etf_signal_notifications",
        run_state_collection="etf_run_state",
        us_watch_windows="17:00-00:00",
        kr_watch_windows="09:00-10:00,11:30-13:00",
        alert_dry_run=alert_dry_run,
        log_level="INFO",
    )
