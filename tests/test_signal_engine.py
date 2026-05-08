from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest import TestCase

from app.models.market import Candle, Instrument, Market, MarketSnapshot, SignalType
from app.strategies.signal_engine import SignalEngine


class SignalEngineTest(TestCase):
    def setUp(self) -> None:
        self.instrument = Instrument(
            symbol="QLD",
            name="ProShares Ultra QQQ",
            market=Market.US,
            exchange="NAS",
            kis_code="QLD",
        )
        self.engine = SignalEngine()

    def test_week_low_signal(self) -> None:
        snapshot = self._snapshot(current_price=100.2, day_low=100.0)

        signals = self.engine.evaluate(snapshot)

        self.assertIn(SignalType.BUY_CANDIDATE, {signal.signal_type for signal in signals})

    def test_caution_signal(self) -> None:
        snapshot = self._snapshot(
            current_price=96.0,
            prev_close=100.0,
            volume=2_000_000,
            candle_volume=1_000_000,
        )

        signals = self.engine.evaluate(snapshot)

        self.assertIn(SignalType.CAUTION, {signal.signal_type for signal in signals})

    def test_pullback_signal(self) -> None:
        candles = self._trend_candles()
        snapshot = MarketSnapshot(
            instrument=self.instrument,
            current_price=109.0,
            prev_close=110.0,
            day_high=110.0,
            day_low=108.5,
            volume=700_000,
            candles=candles,
            observed_at=datetime.now(UTC),
        )

        signals = self.engine.evaluate(snapshot)

        self.assertIn(
            SignalType.PULLBACK_BUY_SIGNAL, {signal.signal_type for signal in signals}
        )

    def _snapshot(
        self,
        *,
        current_price: float,
        prev_close: float = 101.0,
        day_low: float = 100.0,
        volume: float = 900_000,
        candle_volume: float = 1_000_000,
    ) -> MarketSnapshot:
        candles = [
            Candle(
                trading_date=date.today() - timedelta(days=70 - index),
                open=100,
                high=102,
                low=100,
                close=101,
                volume=candle_volume,
            )
            for index in range(70)
        ]
        return MarketSnapshot(
            instrument=self.instrument,
            current_price=current_price,
            prev_close=prev_close,
            day_high=102,
            day_low=day_low,
            volume=volume,
            candles=candles,
            observed_at=datetime.now(UTC),
        )

    def _trend_candles(self) -> list[Candle]:
        closes = [80 + index * 0.45 for index in range(40)] + [
            120,
            119,
            118,
            117,
            116,
            110,
            111,
            112,
            113,
            112,
            111,
            110,
            109,
            108,
            109,
            110,
            111,
            110,
            109,
            108,
        ]
        return [
            Candle(
                trading_date=date.today() - timedelta(days=len(closes) - index),
                open=close - 0.5,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1_000_000,
            )
            for index, close in enumerate(closes)
        ]
