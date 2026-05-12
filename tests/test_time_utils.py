from __future__ import annotations

from datetime import UTC, datetime
from unittest import TestCase

from app.utils.time import to_local_iso


class TimeUtilTest(TestCase):
    def test_to_local_iso_uses_configured_timezone(self) -> None:
        observed_at = datetime(2026, 5, 12, 11, 16, 4, tzinfo=UTC)

        self.assertEqual(
            to_local_iso(observed_at, "Asia/Seoul"),
            "2026-05-12T20:16:04+09:00",
        )

    def test_to_local_iso_accepts_iso_string(self) -> None:
        self.assertEqual(
            to_local_iso("2026-05-12T11:16:04+00:00", "Asia/Seoul"),
            "2026-05-12T20:16:04+09:00",
        )
