from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class Market(StrEnum):
    US = "US"
    KR = "KR"


class MarketState(StrEnum):
    UPTREND = "UPTREND"
    DOWNTREND = "DOWNTREND"
    SIDEWAYS = "SIDEWAYS"
    CRASH = "CRASH"
    UNKNOWN = "UNKNOWN"


class SignalType(StrEnum):
    PULLBACK_BUY_SIGNAL = "PULLBACK_BUY_SIGNAL"
    BUY_CANDIDATE = "BUY_CANDIDATE"
    SIDEWAYS_RANGE_BUY = "SIDEWAYS_RANGE_BUY"
    CAUTION = "CAUTION"


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    market: Market
    exchange: str
    kis_code: str


@dataclass(frozen=True)
class Candle:
    trading_date: date
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class MarketSnapshot:
    instrument: Instrument
    current_price: float
    prev_close: float
    day_high: float
    day_low: float
    volume: float
    candles: list[Candle]
    observed_at: datetime


@dataclass(frozen=True)
class Signal:
    instrument: Instrument
    signal_type: SignalType
    market_state: MarketState
    current_price: float
    reasons: list[str]
    metrics: dict[str, float | str]
    observed_at: datetime

    @property
    def key(self) -> str:
        return f"{self.instrument.symbol}:{self.signal_type.value}"
