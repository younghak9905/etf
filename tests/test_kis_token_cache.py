from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

from app.services.kis_token_cache import (
    CachedKISToken,
    SQLiteKISTokenCache,
    kis_token_key,
)


class KISTokenCacheTest(IsolatedAsyncioTestCase):
    async def test_sqlite_cache_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cache = SQLiteKISTokenCache(Path(tmp) / "tokens.db")
            expires_at = datetime.now(UTC) + timedelta(hours=1)

            await cache.set("key", CachedKISToken("token-value", expires_at))
            cached = await cache.get("key")

        self.assertIsNotNone(cached)
        self.assertEqual(cached.access_token, "token-value")
        self.assertEqual(cached.expires_at, expires_at)

    def test_token_key_is_stable_without_exposing_secret(self) -> None:
        token_key = kis_token_key("https://openapi.koreainvestment.com:9443", "app-key")

        self.assertEqual(
            token_key,
            kis_token_key("https://openapi.koreainvestment.com:9443", "app-key"),
        )
        self.assertNotIn("app-key", token_key)
