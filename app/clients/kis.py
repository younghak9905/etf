from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.config.settings import Settings
from app.models.market import Candle, Instrument, Market, MarketSnapshot
from app.services.kis_token_cache import (
    CachedKISToken,
    build_kis_token_cache,
    kis_token_key,
)

logger = logging.getLogger(__name__)


class KISClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._access_token: str | None = None
        self._token_expires_at = datetime.min.replace(tzinfo=UTC)
        self._token_lock = asyncio.Lock()
        self._token_cache = build_kis_token_cache(settings)
        self._token_key = kis_token_key(settings.kis_base_url, settings.kis_app_key)
        self._client = httpx.AsyncClient(
            base_url=settings.kis_base_url,
            timeout=settings.request_timeout_seconds,
        )
        self._rate_limiter = asyncio.Semaphore(5)

    async def close(self) -> None:
        await self._client.aclose()

    async def get_snapshot(self, instrument: Instrument) -> MarketSnapshot:
        if instrument.market == Market.KR:
            quote, candles = await asyncio.gather(
                self._domestic_quote(instrument.kis_code),
                self._domestic_daily(instrument.kis_code),
            )
        else:
            candles = await self._overseas_daily(instrument.exchange, instrument.kis_code)
            try:
                quote = await self._overseas_quote(instrument.exchange, instrument.kis_code)
            except KeyError as exc:
                logger.warning(
                    "kis_overseas_quote_fallback_to_daily",
                    extra={"symbol": instrument.symbol, "error": str(exc)},
                )
                quote = _quote_from_candles(candles)

        return MarketSnapshot(
            instrument=instrument,
            current_price=quote["current_price"],
            prev_close=quote["prev_close"],
            day_high=quote["day_high"],
            day_low=quote["day_low"],
            volume=quote["volume"],
            candles=candles,
            observed_at=datetime.now(UTC),
        )

    async def _request(
        self, method: str, path: str, *, tr_id: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        token = await self._token()
        headers = {
            "authorization": f"Bearer {token}",
            "appkey": self._settings.kis_app_key or "",
            "appsecret": self._settings.kis_app_secret or "",
            "content-type": "application/json; charset=utf-8",
            "custtype": "P",
        }
        if tr_id:
            headers["tr_id"] = tr_id

        last_error: Exception | None = None
        for attempt in range(4):
            async with self._rate_limiter:
                try:
                    response = await self._client.request(
                        method, path, headers=headers, **kwargs
                    )
                    response.raise_for_status()
                    payload = response.json()
                    if payload.get("rt_cd") not in {None, "0"}:
                        raise RuntimeError(
                            f"KIS API error {payload.get('msg_cd')}: {payload.get('msg1')}"
                        )
                    return payload
                except (httpx.HTTPError, RuntimeError) as exc:
                    last_error = exc
                    if attempt == 3:
                        break
                    await asyncio.sleep(0.5 * (2**attempt))

        raise RuntimeError(f"KIS request failed: {path}") from last_error

    async def _token(self) -> str:
        async with self._token_lock:
            now = datetime.now(UTC)
            if self._access_token and now < self._token_expires_at:
                return self._access_token

            cached = await self._cached_token(now)
            if cached:
                self._access_token = cached.access_token
                self._token_expires_at = cached.expires_at
                return cached.access_token

            response = await self._client.post(
                "/oauth2/tokenP",
                json={
                    "grant_type": "client_credentials",
                    "appkey": self._settings.kis_app_key,
                    "appsecret": self._settings.kis_app_secret,
                },
                headers={"content-type": "application/json; charset=utf-8"},
            )
            if response.status_code >= 400:
                body = response.text[:1000]
                logger.error(
                    "kis_token_request_failed",
                    extra={"status_code": response.status_code, "body": body},
                )
                raise RuntimeError(
                    f"KIS token request failed {response.status_code}: {body}"
                )

            payload = response.json()
            token = payload.get("access_token")
            if not token:
                raise RuntimeError("KIS token response did not include access_token")

            expires_in = int(payload.get("expires_in", 86400))
            self._access_token = token
            self._token_expires_at = now + timedelta(
                seconds=max(60, expires_in - self._settings.kis_token_buffer_seconds)
            )
            await self._store_token(
                CachedKISToken(
                    access_token=self._access_token,
                    expires_at=self._token_expires_at,
                )
            )
            return token

    async def _cached_token(self, now: datetime) -> CachedKISToken | None:
        try:
            cached = await self._token_cache.get(self._token_key)
        except Exception as exc:
            logger.warning("kis_token_cache_read_failed", extra={"error": str(exc)})
            return None
        if cached and now < cached.expires_at:
            logger.info("kis_token_cache_hit")
            return cached
        return None

    async def _store_token(self, token: CachedKISToken) -> None:
        try:
            await self._token_cache.set(self._token_key, token)
        except Exception as exc:
            logger.warning("kis_token_cache_write_failed", extra={"error": str(exc)})

    async def _domestic_quote(self, code: str) -> dict[str, float]:
        payload = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id="FHKST01010100",
            params={"fid_cond_mrkt_div_code": "J", "fid_input_iscd": code},
        )
        output = payload["output"]
        return {
            "current_price": _to_float(output, "stck_prpr"),
            "prev_close": _to_float(output, "stck_sdpr", "prdy_clpr"),
            "day_high": _to_float(output, "stck_hgpr"),
            "day_low": _to_float(output, "stck_lwpr"),
            "volume": _to_float(output, "acml_vol"),
        }

    async def _domestic_daily(self, code: str) -> list[Candle]:
        today = date.today().strftime("%Y%m%d")
        payload = await self._request(
            "GET",
            "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
            tr_id="FHKST03010100",
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": code,
                "FID_INPUT_DATE_1": "20200101",
                "FID_INPUT_DATE_2": today,
                "FID_PERIOD_DIV_CODE": "D",
                "FID_ORG_ADJ_PRC": "1",
            },
        )
        return [
            Candle(
                trading_date=_parse_date(item["stck_bsop_date"]),
                open=_to_float(item, "stck_oprc"),
                high=_to_float(item, "stck_hgpr"),
                low=_to_float(item, "stck_lwpr"),
                close=_to_float(item, "stck_clpr"),
                volume=_to_float(item, "acml_vol"),
            )
            for item in payload.get("output2", [])[:120]
        ]

    async def _overseas_quote(self, exchange: str, symbol: str) -> dict[str, float]:
        payload = await self._request(
            "GET",
            "/uapi/overseas-price/v1/quotations/price",
            tr_id="HHDFS00000300",
            params={"AUTH": "", "EXCD": exchange, "SYMB": symbol},
        )
        output = payload["output"]
        return {
            "current_price": _to_float(
                output, "last", "base", "clos", "close", "ovrs_nmix_prpr", "stck_prpr"
            ),
            "prev_close": _to_float(output, "base", "clos", "close", "last"),
            "day_high": _to_float(output, "high", "hprc", "ovrs_nmix_hgpr"),
            "day_low": _to_float(output, "low", "lprc", "ovrs_nmix_lwpr"),
            "volume": _to_float(output, "tvol", "evol"),
        }

    async def _overseas_daily(self, exchange: str, symbol: str) -> list[Candle]:
        payload = await self._request(
            "GET",
            "/uapi/overseas-price/v1/quotations/dailyprice",
            tr_id="HHDFS76240000",
            params={
                "AUTH": "",
                "EXCD": exchange,
                "SYMB": symbol,
                "GUBN": "0",
                "BYMD": "",
                "MODP": "1",
            },
        )
        rows = _payload_rows(payload, "output2", "output")
        return [
            Candle(
                trading_date=_parse_date(_to_str(item, "xymd", "stck_bsop_date")),
                open=_to_float(item, "open", "ovrs_nmix_oprc"),
                high=_to_float(item, "high", "hprc", "ovrs_nmix_hgpr"),
                low=_to_float(item, "low", "lprc", "ovrs_nmix_lwpr"),
                close=_to_float(item, "clos", "close", "last", "ovrs_nmix_prpr"),
                volume=_to_float(item, "tvol", "evol", "acml_vol"),
            )
            for item in rows[:120]
        ]


def _to_float(payload: dict[str, Any], *keys: str) -> float:
    for key in keys:
        raw = payload.get(key)
        if raw not in {None, ""}:
            return float(str(raw).replace(",", ""))
    available = ", ".join(sorted(payload.keys()))
    raise KeyError(f"missing numeric field: {keys}; available fields: {available}")


def _to_str(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        raw = payload.get(key)
        if raw not in {None, ""}:
            return str(raw)
    available = ", ".join(sorted(payload.keys()))
    raise KeyError(f"missing text field: {keys}; available fields: {available}")


def _payload_rows(payload: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list) and rows:
            return rows
    available = ", ".join(sorted(payload.keys()))
    raise RuntimeError(f"KIS daily rows are empty; available payload fields: {available}")


def _quote_from_candles(candles: list[Candle]) -> dict[str, float]:
    if not candles:
        raise RuntimeError("cannot build quote fallback without overseas candles")
    ordered = sorted(candles, key=lambda candle: candle.trading_date)
    latest = ordered[-1]
    previous = ordered[-2] if len(ordered) >= 2 else latest
    return {
        "current_price": latest.close,
        "prev_close": previous.close,
        "day_high": latest.high,
        "day_low": latest.low,
        "volume": latest.volume,
    }


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y%m%d").date()
