from __future__ import annotations

import gc
import warnings
from datetime import UTC, datetime, timedelta

from tashevnet.storage import Store


async def test_events_round_trip_and_retention(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    await store.init()
    old = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    new = datetime.now(UTC).isoformat()
    await store.save_event(old, "DOWN", "old", {"duration_seconds": None})
    await store.save_event(new, "UP", "back", {"duration_seconds": 192.0})
    assert await store.prune(30) == 1
    events = await store.recent_events(10)
    assert [(e["health"], e["duration_seconds"]) for e in events] == [("UP", 192.0)]
    assert await store.prune(0) == 0  # 0 keeps everything


async def test_connections_are_closed(tmp_path):
    store = Store(str(tmp_path / "t.db"))
    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        await store.init()
        await store.recent_events(5)
        await store.count("events")
        gc.collect()
