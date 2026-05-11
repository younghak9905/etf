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

    async def record_run_summary(self, summary: dict) -> None:
        raise NotImplementedError

    async def get_last_run_summary(self) -> dict | None:
        raise NotImplementedError


class SQLiteAlertStorage(AlertStorage):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            with conn:
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
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS run_state (
                        state_key TEXT PRIMARY KEY,
                        payload TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
        finally:
            conn.close()

    async def should_send(self, signal: Signal, duplicate_window_minutes: int) -> bool:
        cutoff = datetime.now(UTC) - timedelta(minutes=duplicate_window_minutes)
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT sent_at FROM sent_alerts WHERE signal_key = ?",
                (signal.key,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return True
        return datetime.fromisoformat(row[0]) < cutoff

    async def record_sent(self, signal: Signal) -> None:
        conn = self._connect()
        try:
            with conn:
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
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)

    async def record_run_summary(self, summary: dict) -> None:
        import json

        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO run_state(state_key, payload, updated_at)
                    VALUES('last_run', ?, ?)
                    ON CONFLICT(state_key) DO UPDATE SET
                        payload = excluded.payload,
                        updated_at = excluded.updated_at
                    """,
                    (
                        json.dumps(summary, ensure_ascii=False, default=str),
                        datetime.now(UTC).isoformat(),
                    ),
                )
        finally:
            conn.close()

    async def get_last_run_summary(self) -> dict | None:
        import json

        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT payload FROM run_state WHERE state_key = 'last_run'"
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return json.loads(row[0])


class FirestoreAlertStorage(AlertStorage):
    def __init__(self, collection: str, run_state_collection: str) -> None:
        from google.cloud import firestore

        client = firestore.AsyncClient()
        self._collection = client.collection(collection)
        self._run_state = client.collection(run_state_collection)

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

    async def record_run_summary(self, summary: dict) -> None:
        await self._run_state.document("last_run").set(
            {
                **summary,
                "updated_at": datetime.now(UTC),
            },
            merge=True,
        )

    async def get_last_run_summary(self) -> dict | None:
        snapshot = await self._run_state.document("last_run").get()
        if not snapshot.exists:
            return None
        payload = snapshot.to_dict() or {}
        return payload


def build_alert_storage(settings: Settings) -> AlertStorage:
    if settings.storage_backend == "firestore":
        return FirestoreAlertStorage(
            settings.firestore_collection, settings.run_state_collection
        )
    return SQLiteAlertStorage(settings.sqlite_path)
