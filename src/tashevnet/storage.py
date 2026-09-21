from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .models import Snapshot


class Store:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)

    def _init_sync(self) -> None:
        with self._connect() as db:
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    health TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            db.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    health TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            db.execute("CREATE INDEX IF NOT EXISTS ix_snapshots_ts ON snapshots(timestamp)")
            db.execute("CREATE INDEX IF NOT EXISTS ix_events_ts ON events(timestamp)")

    async def save_snapshot(self, snapshot: Snapshot, *, event: bool = False) -> None:
        await asyncio.to_thread(self._save_snapshot_sync, snapshot, event)

    def _save_snapshot_sync(self, snapshot: Snapshot, event: bool) -> None:
        payload = json.dumps(snapshot.to_dict(), ensure_ascii=False)
        table = "events" if event else "snapshots"
        with self._connect() as db:
            db.execute(
                f"INSERT INTO {table}(timestamp, health, reason, payload) VALUES (?, ?, ?, ?)",
                (snapshot.timestamp, snapshot.health.value, snapshot.reason, payload),
            )

    async def prune(self, retention_days: int) -> None:
        if retention_days <= 0:
            return
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat()
        await asyncio.to_thread(self._prune_sync, cutoff)

    def _prune_sync(self, cutoff: str) -> None:
        with self._connect() as db:
            db.execute("DELETE FROM snapshots WHERE timestamp < ?", (cutoff,))
            db.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))

    async def recent_events(self, limit: int = 20) -> list[dict]:
        return await asyncio.to_thread(self._recent_events_sync, limit)

    def _recent_events_sync(self, limit: int) -> list[dict]:
        safe_limit = max(1, min(int(limit), 200))
        with self._connect() as db:
            rows = db.execute(
                "SELECT id, timestamp, health, reason, payload FROM events "
                "ORDER BY id DESC LIMIT ?",
                (safe_limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "health": row["health"],
                "reason": row["reason"],
                "payload": json.loads(row["payload"]),
            }
            for row in rows
        ]
