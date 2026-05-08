from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

sys.modules.setdefault(
    "httpx",
    types.SimpleNamespace(AsyncClient=object),
)

from app.config.settings import Settings
from app.notification.discord import DiscordNotifier


class DiscordNotifierTest(IsolatedAsyncioTestCase):
    async def test_send_test_respects_dry_run(self) -> None:
        notifier = DiscordNotifier(_settings(alert_dry_run=True))

        result = await notifier.send_test()

        self.assertEqual(result, "dry_run")


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
        us_watch_windows="17:00-00:00",
        kr_watch_windows="09:00-10:00,11:30-13:00",
        alert_dry_run=alert_dry_run,
        log_level="INFO",
    )
