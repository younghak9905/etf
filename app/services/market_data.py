from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.clients.kis import KISClient
from app.config.settings import Settings
from app.models.market import Candle, Instrument, MarketSnapshot


class MarketDataService:
    async def get_snapshot(self, instrument: Instrument) -> MarketSnapshot:
        raise NotImplementedError

    async def close(self) -> None:
        return None


class KISMarketDataService(MarketDataService):
    def __init__(self, settings: Settings) -> None:
        self._client = KISClient(settings)

    async def get_snapshot(self, instrument: Instrument) -> MarketSnapshot:
        return await self._client.get_snapshot(instrument)

    async def close(self) -> None:
        await self._client.close()


class MockMarketDataService(MarketDataService):
    async def get_snapshot(self, instrument: Instrument) -> MarketSnapshot:
        today = date.today()
        candles = [
            Candle(
                trading_date=today - timedelta(days=80 - index),
                open=100 + index * 0.2,
                high=101 + index * 0.2,
                low=99 + index * 0.2,
                close=100 + index * 0.2,
                volume=1_000_000,
            )
            for index in range(80)
        ]
        ma_like = candles[-20].close
        return MarketSnapshot(
            instrument=instrument,
            current_price=ma_like * 1.002,
            prev_close=ma_like * 1.01,
            day_high=ma_like * 1.006,
            day_low=ma_like * 0.998,
            volume=700_000,
            candles=candles,
            observed_at=datetime.now(UTC),
        )


def build_market_data_service(settings: Settings) -> MarketDataService:
    if settings.market_data_mode == "mock":
        return MockMarketDataService()
    return KISMarketDataService(settings)
