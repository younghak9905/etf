from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.market import Market


def is_market_window_open(
    market: Market, now: datetime, timezone_name: str, us_windows: str, kr_windows: str
) -> bool:
    local_now = now.astimezone(_timezone(timezone_name))
    windows = us_windows if market == Market.US else kr_windows
    return any(_contains(local_now.time(), item.strip()) for item in windows.split(",") if item.strip())


def _contains(current: time, window: str) -> bool:
    start_raw, end_raw = window.split("-", maxsplit=1)
    start = _parse_hhmm(start_raw)
    end = _parse_hhmm(end_raw)

    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def _parse_hhmm(raw: str) -> time:
    hour, minute = raw.strip().split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))


def _timezone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Seoul":
            return timezone(timedelta(hours=9), name="KST")
        raise
