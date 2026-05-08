from __future__ import annotations

from app.indicators.technical import average, rsi, sma
from app.models.market import MarketSnapshot, MarketState, Signal, SignalType


class SignalEngine:
    def evaluate(self, snapshot: MarketSnapshot) -> list[Signal]:
        closes = [candle.close for candle in sorted(snapshot.candles, key=lambda c: c.trading_date)]
        highs = [candle.high for candle in sorted(snapshot.candles, key=lambda c: c.trading_date)]
        lows = [candle.low for candle in sorted(snapshot.candles, key=lambda c: c.trading_date)]
        volumes = [
            candle.volume for candle in sorted(snapshot.candles, key=lambda c: c.trading_date)
        ]

        if not closes:
            return []

        price_series = closes + [snapshot.current_price]
        ma20 = sma(price_series, 20)
        ma60 = sma(price_series, 60)
        current_rsi = rsi(price_series, 14)
        volume_ma = average(volumes, 20)
        week_low = min((lows + [snapshot.day_low])[-5:])
        range_low = min((lows + [snapshot.day_low])[-20:])
        market_state = self.classify_market_state(snapshot, ma20, ma60)

        metrics: dict[str, float | str] = {
            "ma20": round(ma20, 4) if ma20 is not None else "NA",
            "ma60": round(ma60, 4) if ma60 is not None else "NA",
            "rsi": round(current_rsi, 2) if current_rsi is not None else "NA",
            "volume_ma": round(volume_ma, 2) if volume_ma is not None else "NA",
            "week_low": round(week_low, 4),
            "range_low": round(range_low, 4),
            "day_high": snapshot.day_high,
            "day_low": snapshot.day_low,
            "prev_close": snapshot.prev_close,
        }

        signals: list[Signal] = []

        if (
            ma20 is not None
            and ma60 is not None
            and current_rsi is not None
            and volume_ma is not None
            and ma20 > ma60
            and snapshot.current_price <= ma20 * 1.01
            and 40 <= current_rsi <= 50
            and snapshot.volume < volume_ma
        ):
            signals.append(
                Signal(
                    instrument=snapshot.instrument,
                    signal_type=SignalType.PULLBACK_BUY_SIGNAL,
                    market_state=market_state,
                    current_price=snapshot.current_price,
                    reasons=[
                        "상승 추세 유지(MA20 > MA60)",
                        "현재가가 MA20 근처",
                        "RSI 40~50 조정 구간",
                        "평균 대비 거래량 감소",
                    ],
                    metrics=metrics,
                    observed_at=snapshot.observed_at,
                )
            )

        if snapshot.current_price <= week_low * 1.005:
            signals.append(
                Signal(
                    instrument=snapshot.instrument,
                    signal_type=SignalType.BUY_CANDIDATE,
                    market_state=market_state,
                    current_price=snapshot.current_price,
                    reasons=["주간 저점 0.5% 이내 접근"],
                    metrics=metrics,
                    observed_at=snapshot.observed_at,
                )
            )

        if market_state == MarketState.SIDEWAYS and snapshot.current_price <= range_low * 1.002:
            signals.append(
                Signal(
                    instrument=snapshot.instrument,
                    signal_type=SignalType.SIDEWAYS_RANGE_BUY,
                    market_state=market_state,
                    current_price=snapshot.current_price,
                    reasons=["횡보 상태에서 박스 하단 0.2% 이내 접근"],
                    metrics=metrics,
                    observed_at=snapshot.observed_at,
                )
            )

        if (
            volume_ma is not None
            and snapshot.current_price <= snapshot.prev_close * 0.97
            and snapshot.volume > volume_ma * 1.5
        ):
            signals.append(
                Signal(
                    instrument=snapshot.instrument,
                    signal_type=SignalType.CAUTION,
                    market_state=market_state,
                    current_price=snapshot.current_price,
                    reasons=["전일 종가 대비 3% 이상 하락", "평균 대비 거래량 급증"],
                    metrics=metrics,
                    observed_at=snapshot.observed_at,
                )
            )

        return signals

    @staticmethod
    def classify_market_state(
        snapshot: MarketSnapshot, ma20: float | None, ma60: float | None
    ) -> MarketState:
        if snapshot.prev_close > 0 and snapshot.current_price <= snapshot.prev_close * 0.97:
            return MarketState.CRASH

        if snapshot.current_price > 0:
            intraday_range = (snapshot.day_high - snapshot.day_low) / snapshot.current_price
            if intraday_range < 0.01:
                return MarketState.SIDEWAYS

        if ma20 is None or ma60 is None:
            return MarketState.UNKNOWN
        if ma20 > ma60:
            return MarketState.UPTREND
        if ma20 < ma60:
            return MarketState.DOWNTREND
        return MarketState.SIDEWAYS
