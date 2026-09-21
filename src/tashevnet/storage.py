from __future__ import annotations

import asyncio
import json
import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .models import Snapshot


class Store:
    """SQLite flight recorder: periodic snapshots plus confirmed state changes."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _db(self) -> Generator[sqlite3.Connection, None, None]:
        with closing(sqlite3.connect(self.path, timeout=10)) as connection:
            connection.row_factory = sqlite3.Row
            with connection:  # commit on success, roll back on error
                yield connection

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        with self._db() as db:
            db.execute("PRAGMA journal_mode=WAL")
            for table in ("snapshots", "events"):
                db.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        health TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        payload TEXT NOT NULL
                    )
                    """
                )
                db.execute(f"CREATE INDEX IF NOT EXISTS ix_{table}_ts ON {table}(timestamp)")

    async def save_snapshot(self, snapshot: Snapshot) -> None:
        await asyncio.to_thread(
            self._insert,
            "snapshots",
            snapshot.timestamp,
            snapshot.health.value,
            snapshot.reason,
            snapshot.to_dict(),
        )

    async def save_event(
        self, timestamp: str, health: str, reason: str, payload: dict[str, Any]
    ) -> None:
        await asyncio.to_thread(self._insert, "events", timestamp, health, reason, payload)

    def _insert(
        self, table: str, timestamp: str, health: str, reason: str, payload: dict[str, Any]
    ) -> None:
        with self._db() as db:
            db.execute(
                f"INSERT INTO {table}(timestamp, health, reason, payload) VALUES (?, ?, ?, ?)",
                (timestamp, health, reason, json.dumps(payload, ensure_ascii=False)),
            )

    async def prune(self, retention_days: int) -> int:
        """Delete history older than the retention window; return deleted rows."""
        if retention_days <= 0:
            return 0
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        return await asyncio.to_thread(self._prune_sync, cutoff)

    def _prune_sync(self, cutoff: str) -> int:
        with self._db() as db:
            deleted = db.execute("DELETE FROM snapshots WHERE timestamp < ?", (cutoff,)).rowcount
            deleted += db.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,)).rowcount
        return deleted

    async def recent_events(self, limit: int = 20) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._recent_events_sync, limit)

    def _recent_events_sync(self, limit: int) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        with self._db() as db:
            rows = db.execute(
                "SELECT id, timestamp, health, reason, payload FROM events "
                "ORDER BY id DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        events = []
        for row in rows:
            payload = json.loads(row["payload"])
            events.append(
                {
                    "id": row["id"],
                    "timestamp": row["timestamp"],
                    "health": row["health"],
                    "reason": row["reason"],
                    "duration_seconds": payload.get("duration_seconds"),
                    "previous": payload.get("previous"),
                    "payload": payload,
                }
            )
        return events

    async def count(self, table: str) -> int:
        if table not in {"snapshots", "events"}:
            raise ValueError(table)
        return await asyncio.to_thread(self._count_sync, table)

    def _count_sync(self, table: str) -> int:
        with self._db() as db:
            return int(db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
