from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config.settings import Settings
from app.models.market import Signal


class AlertStorage:
    async def should_send(self, signal: Signal, duplicate_window_minutes: int) -> bool:
        raise NotImplementedError

    async def record_sent(self, signal: Signal) -> None:
        raise NotImplementedError


class SQLiteAlertStorage(AlertStorage):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sent_alerts (
                    signal_key TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    signal_type TEXT NOT NULL,
                    sent_at TEXT NOT NULL
                )
                """
            )

    async def should_send(self, signal: Signal, duplicate_window_minutes: int) -> bool:
        cutoff = datetime.now(UTC) - timedelta(minutes=duplicate_window_minutes)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT sent_at FROM sent_alerts WHERE signal_key = ?",
                (signal.key,),
            ).fetchone()
        if not row:
            return True
        return datetime.fromisoformat(row[0]) < cutoff

    async def record_sent(self, signal: Signal) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sent_alerts(signal_key, symbol, signal_type, sent_at)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(signal_key) DO UPDATE SET sent_at = excluded.sent_at
                """,
                (
                    signal.key,
                    signal.instrument.symbol,
                    signal.signal_type.value,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)


class FirestoreAlertStorage(AlertStorage):
    def __init__(self, collection: str) -> None:
        from google.cloud import firestore

        self._collection = firestore.AsyncClient().collection(collection)

    async def should_send(self, signal: Signal, duplicate_window_minutes: int) -> bool:
        snapshot = await self._collection.document(signal.key).get()
        if not snapshot.exists:
            return True
        payload = snapshot.to_dict() or {}
        sent_at = payload.get("sent_at")
        if not isinstance(sent_at, datetime):
            return True
        cutoff = datetime.now(UTC) - timedelta(minutes=duplicate_window_minutes)
        return sent_at < cutoff

    async def record_sent(self, signal: Signal) -> None:
        await self._collection.document(signal.key).set(
            {
                "symbol": signal.instrument.symbol,
                "signal_type": signal.signal_type.value,
                "sent_at": datetime.now(UTC),
            },
            merge=True,
        )


def build_alert_storage(settings: Settings) -> AlertStorage:
    if settings.storage_backend == "firestore":
        return FirestoreAlertStorage(settings.firestore_collection)
    return SQLiteAlertStorage(settings.sqlite_path)
