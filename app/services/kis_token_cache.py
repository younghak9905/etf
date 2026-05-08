from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.config.settings import Settings


@dataclass(frozen=True)
class CachedKISToken:
    access_token: str
    expires_at: datetime


class KISTokenCache:
    async def get(self, token_key: str) -> CachedKISToken | None:
        raise NotImplementedError

    async def set(self, token_key: str, token: CachedKISToken) -> None:
        raise NotImplementedError


class SQLiteKISTokenCache(KISTokenCache):
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kis_tokens (
                        token_key TEXT PRIMARY KEY,
                        access_token TEXT NOT NULL,
                        expires_at TEXT NOT NULL
                    )
                    """
                )
        finally:
            conn.close()

    async def get(self, token_key: str) -> CachedKISToken | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT access_token, expires_at FROM kis_tokens WHERE token_key = ?",
                (token_key,),
            ).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return CachedKISToken(
            access_token=row[0],
            expires_at=datetime.fromisoformat(row[1]),
        )

    async def set(self, token_key: str, token: CachedKISToken) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute(
                    """
                    INSERT INTO kis_tokens(token_key, access_token, expires_at)
                    VALUES(?, ?, ?)
                    ON CONFLICT(token_key) DO UPDATE SET
                        access_token = excluded.access_token,
                        expires_at = excluded.expires_at
                    """,
                    (token_key, token.access_token, token.expires_at.isoformat()),
                )
        finally:
            conn.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)


class FirestoreKISTokenCache(KISTokenCache):
    def __init__(self, collection: str) -> None:
        from google.cloud import firestore

        self._collection = firestore.AsyncClient().collection(collection)

    async def get(self, token_key: str) -> CachedKISToken | None:
        snapshot = await self._collection.document(token_key).get()
        if not snapshot.exists:
            return None
        payload = snapshot.to_dict() or {}
        access_token = payload.get("access_token")
        expires_at = payload.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)
        if not isinstance(access_token, str) or not isinstance(expires_at, datetime):
            return None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return CachedKISToken(access_token=access_token, expires_at=expires_at)

    async def set(self, token_key: str, token: CachedKISToken) -> None:
        await self._collection.document(token_key).set(
            {
                "access_token": token.access_token,
                "expires_at": token.expires_at,
                "updated_at": datetime.now(UTC),
            },
            merge=True,
        )


def build_kis_token_cache(settings: Settings) -> KISTokenCache:
    backend = settings.kis_token_cache_backend
    if backend == "firestore":
        return FirestoreKISTokenCache(settings.kis_token_cache_collection)
    return SQLiteKISTokenCache(settings.sqlite_path)


def kis_token_key(base_url: str, app_key: str | None) -> str:
    raw = f"{base_url}:{app_key or ''}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
