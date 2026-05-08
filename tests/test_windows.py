from __future__ import annotations

from datetime import UTC, datetime
from unittest import TestCase

from app.models.market import Market
from app.scheduler.windows import is_market_window_open


class MarketWindowTest(TestCase):
    def test_us_cross_midnight_window(self) -> None:
        now = datetime(2026, 5, 8, 15, 0, tzinfo=UTC)

        self.assertTrue(
            is_market_window_open(
                Market.US,
                now,
                "Asia/Seoul",
                "17:00-00:00",
                "09:00-10:00,11:30-13:00",
            )
        )

    def test_kr_lunch_window(self) -> None:
        now = datetime(2026, 5, 8, 3, 0, tzinfo=UTC)

        self.assertTrue(
            is_market_window_open(
                Market.KR,
                now,
                "Asia/Seoul",
                "17:00-00:00",
                "09:00-10:00,11:30-13:00",
            )
        )
