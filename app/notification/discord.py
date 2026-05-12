from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from app.config.settings import Settings
from app.models.market import Signal
from app.utils.time import to_local_iso

logger = logging.getLogger(__name__)


class DiscordNotifier:
    def __init__(self, settings: Settings) -> None:
        self._webhook_url = settings.discord_webhook_url
        self._dry_run = settings.alert_dry_run
        self._timeout = settings.request_timeout_seconds
        self._timezone = settings.timezone

    async def send(self, signal: Signal) -> None:
        payload = self._payload(signal)
        await self._send_payload(payload)

    async def send_test(self) -> str:
        payload = {
            "username": "ETF Pullback Alert",
            "content": (
                "**ETF Pullback Alert test notification**\n\n"
                f"Status: `ok`\n"
                f"Time: `{to_local_iso(datetime.now(UTC), self._timezone)}`\n"
                f"Timezone: `{self._timezone}`\n\n"
                "Discord webhook delivery is working."
            ),
        }
        return await self._send_payload(payload)

    async def _send_payload(self, payload: dict[str, object]) -> str:
        if self._dry_run:
            logger.info("discord_dry_run", extra={"message": payload["content"]})
            return "dry_run"

        if not self._webhook_url:
            raise RuntimeError("discord webhook url is not configured")

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(self._webhook_url, json=payload)
            response.raise_for_status()
        return "sent"

    def _payload(self, signal: Signal) -> dict[str, object]:
        metrics = signal.metrics
        reason_text = "\n".join(f"- {reason}" for reason in signal.reasons)
        content = (
            f"**[{signal.instrument.name} {signal.signal_type.value}]**\n\n"
            f"종목: `{signal.instrument.symbol}`\n"
            f"관측시각: `{to_local_iso(signal.observed_at, self._timezone)}`\n"
            f"시장상태: `{signal.market_state.value}`\n"
            f"현재가: `{signal.current_price}`\n"
            f"전일대비: `{_fmt_pct(metrics.get('prev_close_change_pct'))}`\n"
            f"MA20: `{metrics.get('ma20')}`\n"
            f"MA60: `{metrics.get('ma60')}`\n"
            f"MA20 괴리율: `{_fmt_pct(metrics.get('ma20_gap_pct'))}`\n"
            f"RSI: `{metrics.get('rsi')}`\n"
            f"주간저점: `{metrics.get('week_low')}`\n"
            f"주간저점 대비: `{_fmt_pct(metrics.get('week_low_gap_pct'))}`\n"
            f"박스하단 대비: `{_fmt_pct(metrics.get('range_low_gap_pct'))}`\n"
            f"거래량/평균: `{_fmt_ratio(metrics.get('volume_ratio'))}`\n"
            f"가격 데이터: `{metrics.get('quote_source', 'quote')}`\n\n"
            f"조건:\n{reason_text}\n\n"
            "적립식 분할매수 후보 구간입니다. 자동매매 신호가 아닌 참고 알림입니다."
        )
        return {
            "username": "ETF Pullback Alert",
            "content": content[:2000],
        }


def _fmt_pct(value: object) -> str:
    if isinstance(value, (float, int)):
        return f"{value:+.2f}%"
    return "NA"


def _fmt_ratio(value: object) -> str:
    if isinstance(value, (float, int)):
        return f"{value:.2f}x"
    return "NA"
