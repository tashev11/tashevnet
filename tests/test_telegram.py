from __future__ import annotations

import logging
import os
import time

import httpx
import pytest

from tashevnet.config import TelegramConfig
from tashevnet.models import Health, Snapshot, SpeedResult
from tashevnet.state import Observation, Transition
from tashevnet.telegram import (
    TelegramBot,
    format_snapshot,
    format_transition,
    human_duration,
    local_time,
)

TOKEN = "123456:SECRET-TOKEN-VALUE"


def snapshot(**overrides) -> Snapshot:
    values = {
        "timestamp": "2026-09-21T18:00:00+00:00",
        "health": Health.UP,
        "reason": "Connectivity is healthy",
        "probes": [],
        "vpn_connected": True,
        "vpn_interface": "utun4",
        "public_ip": "203.0.113.10",
        "gateway": "192.168.1.1",
        "speed": SpeedResult(download_mbps=100.5, upload_mbps=42.0),
    }
    values.update(overrides)
    return Snapshot(**values)


def bot(telegram, **config) -> TelegramBot:
    settings = TelegramConfig(enabled=True, bot_token=TOKEN, chat_id="42", **config)
    return TelegramBot(
        settings,
        lambda: {"version": "test", "snapshot": snapshot(), "state": None},
        lambda limit: _no_events(),
        client=telegram.client(),
    )


async def _no_events():
    return []


def test_format_snapshot_contains_operational_fields():
    message = format_snapshot(snapshot())
    assert "🟢" in message
    assert "VPN: ON" in message
    assert "203.0.113.10" in message
    assert "100.5 Mbps" in message


def test_recovery_message_says_how_long_it_lasted():
    down = Observation(Health.DOWN, "Internet/WAN probes are unreachable", "2026-09-21T18:00:00+00:00")
    up = Observation(Health.UP, "Connectivity is healthy", "2026-09-21T18:03:12+00:00")
    text = format_transition(Transition(down, up, 192), snapshot())
    assert text.startswith("🟢 TashevNet · back to UP after 3 min 12 s")
    assert "Was DOWN: Internet/WAN probes are unreachable" in text


@pytest.mark.skipif(os.name == "nt", reason="time.tzset is POSIX only")
def test_times_are_shown_in_local_time(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Moscow")
    time.tzset()
    try:
        assert local_time("2026-09-21T18:54:10+00:00") == "21.09 21:54:10 MSK"
    finally:
        monkeypatch.delenv("TZ")
        time.tzset()


def test_human_duration():
    assert human_duration(42) == "42 s"
    assert human_duration(192) == "3 min 12 s"
    assert human_duration(7260) == "2 h 1 min"
    assert human_duration(90000) == "1 d 1 h"


async def test_alerts_wait_for_the_network_and_keep_their_order(telegram):
    client = bot(telegram)
    telegram.online = False
    client.notify("first")
    client.notify("second")
    assert await client.flush() == 0 and client.pending == 2
    telegram.online = True
    assert await client.flush() == 2
    assert telegram.sent == ["first", "second"]
    await client.close()


async def test_rejected_alert_is_dropped_not_retried_forever(telegram):
    client = bot(telegram)
    telegram.status = 400
    client.notify("bad")
    assert await client.flush() == 1 and client.pending == 0
    await client.close()


async def test_commands_ignore_stickers_foreign_chats_and_stale_messages(telegram):
    client = bot(telegram)
    now = int(time.time())
    telegram.updates = [
        {"update_id": 1, "message": {"chat": {"id": 42}, "date": now, "sticker": {}}},
        {"update_id": 2, "message": {"chat": {"id": 7}, "date": now, "text": "/status"}},
        {"update_id": 3, "message": {"chat": {"id": 42}, "date": now - 3600, "text": "/vpn"}},
        {"update_id": 4, "message": {"chat": {"id": 42}, "date": now, "text": "/ping@bot"}},
    ]
    await client.poll_once()
    assert len(telegram.sent) == 1 and telegram.sent[0].startswith("🏓 TashevNet test is alive")
    assert client.offset == 5
    await client.close()


async def test_token_never_reaches_the_log(telegram, caplog):
    def leaky(request):
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    client = TelegramBot(
        TelegramConfig(enabled=True, bot_token=TOKEN, chat_id="42"),
        dict,
        lambda limit: _no_events(),
        client=httpx.AsyncClient(transport=httpx.MockTransport(leaky)),
    )
    with caplog.at_level(logging.WARNING):
        assert await client.send("hello") is False
    assert TOKEN not in caplog.text and "<bot-token>" in caplog.text
    await client.close()
