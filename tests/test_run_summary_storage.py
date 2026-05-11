from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import IsolatedAsyncioTestCase

from app.services.storage import SQLiteAlertStorage


class RunSummaryStorageTest(IsolatedAsyncioTestCase):
    async def test_sqlite_run_summary_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            storage = SQLiteAlertStorage(Path(tmp) / "alerts.db")
            summary = {
                "status": "ok",
                "active_symbols": ["QLD", "SOXX"],
                "signal_count": 0,
                "sent_count": 0,
                "suppressed_count": 0,
                "error_count": 0,
                "no_alert_reason": "no_signal_conditions_met",
            }

            await storage.record_run_summary(summary)
            loaded = await storage.get_last_run_summary()

        self.assertEqual(loaded["status"], "ok")
        self.assertEqual(loaded["active_symbols"], ["QLD", "SOXX"])
        self.assertEqual(loaded["no_alert_reason"], "no_signal_conditions_met")
