from __future__ import annotations

import logging

import httpx

from app.config.settings import Settings
from app.models.market import Signal

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, settings: Settings) -> None:
        self._token = settings.telegram_bot_token
        self._chat_id = settings.telegram_chat_id
        self._dry_run = settings.alert_dry_run
        self._timeout = settings.request_timeout_seconds

    async def send(self, signal: Signal) -> None:
        text = self._format(signal)
        if self._dry_run:
            logger.info("telegram_dry_run", extra={"message": text})
            return

        if not self._token or not self._chat_id:
            raise RuntimeError("telegram credentials are not configured")

        url = f"https://api.telegram.org/bot{self._token}/sendMessage"
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                url,
                json={"chat_id": self._chat_id, "text": text},
            )
            response.raise_for_status()

    @staticmethod
    def _format(signal: Signal) -> str:
        metrics = signal.metrics
        reason_text = "\n".join(f"- {reason}" for reason in signal.reasons)
        return (
            f"[{signal.instrument.name} {signal.signal_type.value}]\n\n"
            f"종목: {signal.instrument.symbol}\n"
            f"시장상태: {signal.market_state.value}\n"
            f"현재가: {signal.current_price}\n"
            f"MA20: {metrics.get('ma20')}\n"
            f"MA60: {metrics.get('ma60')}\n"
            f"RSI: {metrics.get('rsi')}\n"
            f"주간저점: {metrics.get('week_low')}\n\n"
            f"조건:\n{reason_text}\n\n"
            "적립식 분할매수 후보 구간입니다. 자동매매 신호가 아닌 참고 알림입니다."
        )
