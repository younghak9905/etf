from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_timezone(timezone_name: str):
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        if timezone_name == "Asia/Seoul":
            return timezone(timedelta(hours=9), name="KST")
        raise


def to_local_iso(value: datetime | str, timezone_name: str) -> str:
    observed_at = value
    if isinstance(observed_at, str):
        observed_at = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    return observed_at.astimezone(resolve_timezone(timezone_name)).isoformat()
