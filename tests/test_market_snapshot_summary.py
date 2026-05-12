from __future__ import annotations

from datetime import UTC, date, datetime
from unittest import TestCase

from app.main import _market_snapshots_html, _serialize_snapshot
from app.models.market import Candle, Instrument, Market, MarketSnapshot


class MarketSnapshotSummaryTest(TestCase):
    def test_serialize_snapshot_includes_local_time_and_ohlcv(self) -> None:
        snapshot = _snapshot()

        serialized = _serialize_snapshot(snapshot, "Asia/Seoul")

        self.assertEqual(serialized["symbol"], "QLD")
        self.assertEqual(serialized["current_price"], 90.5)
        self.assertEqual(serialized["day_high"], 91.2)
        self.assertEqual(serialized["day_low"], 89.8)
        self.assertEqual(serialized["volume"], 1234567)
        self.assertEqual(serialized["observed_at_local"], "2026-05-12T20:30:00+09:00")

    def test_market_snapshots_html_shows_registered_instruments(self) -> None:
        qld = _instrument()
        soxx = Instrument("SOXX", "iShares Semiconductor ETF", Market.US, "NAS", "SOXX")
        summary = {"market_snapshots": [_serialize_snapshot(_snapshot(), "Asia/Seoul")]}

        content = _market_snapshots_html([qld, soxx], summary, "Asia/Seoul")

        self.assertIn("QLD", content)
        self.assertIn("90.5", content)
        self.assertIn("1,234,567", content)
        self.assertIn("SOXX", content)
        self.assertIn("not checked in last run", content)


def _instrument() -> Instrument:
    return Instrument("QLD", "ProShares Ultra QQQ", Market.US, "AMS", "QLD")


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        instrument=_instrument(),
        current_price=90.5,
        prev_close=92.26,
        day_high=91.2,
        day_low=89.8,
        volume=1234567,
        candles=[
            Candle(
                trading_date=date(2026, 5, 12),
                open=90.0,
                high=91.2,
                low=89.8,
                close=90.5,
                volume=1234567,
            )
        ],
        observed_at=datetime(2026, 5, 12, 11, 30, tzinfo=UTC),
        quote_source="intraday_quote",
    )
