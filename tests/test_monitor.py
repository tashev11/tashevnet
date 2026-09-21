from __future__ import annotations

import asyncio
import os
import time
from datetime import UTC, datetime, timedelta

import pytest

from tashevnet.models import Health


async def ticks(engine, count: int) -> None:
    for _ in range(count):
        await engine.tick()


async def test_outage_keeps_monitoring_and_alerts_arrive_after_recovery(
    make_engine, net, telegram
):
    engine = await make_engine()
    await ticks(engine, 3)
    assert await engine.store.count("events") == 0  # a healthy start is not an incident

    net.internet = False
    telegram.online = False  # without Internet, Telegram is unreachable too
    await ticks(engine, 3)
    assert engine.state.confirmed.health == Health.DOWN
    assert await engine.telegram.flush() == 0
    assert engine.telegram.pending == 1  # kept, not lost

    net.internet = True
    telegram.online = True
    await ticks(engine, 3)
    assert engine.current.health == Health.UP
    assert await engine.telegram.flush() == 2
    assert telegram.sent[0].startswith("🔴 TashevNet · DOWN")
    assert telegram.sent[1].startswith("🟢 TashevNet · back to UP after")

    events = await engine.store.recent_events(10)
    assert [item["health"] for item in events] == ["UP", "DOWN"]
    assert events[0]["duration_seconds"] is not None


async def test_monitor_loop_survives_a_failing_check(make_engine, net):
    engine = await make_engine(interval_seconds=1)
    real_collect, calls = engine.collect, []

    async def flaky_collect():
        calls.append(1)
        if len(calls) == 1:
            raise OSError("disk I/O error")
        return await real_collect()

    engine.collect = flaky_collect
    task = asyncio.create_task(engine.monitor_loop())
    await asyncio.sleep(1.3)
    task.cancel()
    assert len(calls) == 2 and engine.current is not None
    assert engine.telegram.pending == 1  # one error notice, not one per check


async def test_steady_high_latency_is_one_alert(make_engine, net):
    engine = await make_engine()
    net.latencies = [300 + 5 * index for index in range(12)]
    await ticks(engine, 12)
    events = await engine.store.recent_events(20)
    assert [item["health"] for item in events] == ["DEGRADED"]
    assert engine.telegram.pending == 1
    assert engine.current.line_latency_ms >= 300


async def test_latency_jitter_is_one_alert(make_engine, net):
    engine = await make_engine()
    net.latencies = [20, 20, 20] + [240, 260] * 6
    await ticks(engine, 15)
    assert await engine.store.count("events") == 1


async def test_parallel_checks_do_not_duplicate_alerts(make_engine, net):
    engine = await make_engine()
    await ticks(engine, 3)
    net.internet = False
    await asyncio.gather(*(engine.tick() for _ in range(4)))
    assert await engine.store.count("events") == 1
    assert engine.telegram.pending == 1


async def test_proxy_vpn_cannot_fake_the_internet(make_engine, net):
    engine = await make_engine()
    net.icmp_spoofed = net.tcp_local = True
    net.internet = False  # the VPN tunnel is dead, the local client still answers
    await ticks(engine, 3)
    assert engine.current.health == Health.DOWN
    internet = [p for p in engine.current.probes if p.name.startswith("internet:")]
    assert all(p.meta["method"] == "https" and not p.ok for p in internet)
    assert engine.current.path.tcp_local is True


async def test_blocked_icmp_falls_back_to_https(make_engine, net):
    engine = await make_engine()
    net.icmp = False
    await ticks(engine, 2)
    assert engine.current.health == Health.UP
    internet = [p for p in engine.current.probes if p.name.startswith("internet:")]
    assert {p.meta["method"] for p in internet} == {"https"}


async def test_icmp_is_used_when_it_works(make_engine, net):
    engine = await make_engine()
    await ticks(engine, 1)
    assert net.https_calls == 0  # no extra traffic when ping answers


async def test_silent_router_is_ignored_while_the_internet_works(make_engine, net):
    engine = await make_engine()
    net.gateway_ping = False
    await ticks(engine, 3)
    assert engine.current.health == Health.UP
    gateway = engine.current.probes[0]
    assert gateway.name == "gateway:192.168.1.1" and gateway.meta["ignored"] is True


async def test_vpn_kill_switch_is_named_as_the_cause(make_engine, net):
    engine = await make_engine(vpn_required=True)
    net.internet = False
    await ticks(engine, 1)
    assert "VPN is disconnected" in engine.current.reason


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell command")
async def test_hanging_self_heal_does_not_stop_checks(make_engine, net):
    engine = await make_engine(
        vpn_required=True,
        self_heal_vpn_command="sleep 30",
        self_heal_timeout_seconds=1,
        self_heal_cooldown_seconds=0,
    )
    await ticks(engine, 2)  # VPN missing twice: the command starts in the background
    assert engine._heal_task is not None and not engine._heal_task.done()
    started = time.monotonic()
    await ticks(engine, 1)
    assert time.monotonic() - started < 1  # the check did not wait for the command
    await asyncio.wait_for(engine._heal_task, 5)
    assert engine.telegram.pending >= 1  # "self-heal command failed" notice


async def test_history_is_pruned_while_running(make_engine, net):
    engine = await make_engine(retention_days=30)
    old = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    await engine.store.save_event(old, "DOWN", "old", {})
    await ticks(engine, 1)  # the first check prunes
    assert await engine.store.count("events") == 0

    await engine.store.save_event(old, "DOWN", "old", {})
    await ticks(engine, 1)  # pruning is hourly, not every check
    assert await engine.store.count("events") == 1
    engine._last_prune -= 3601
    await ticks(engine, 1)
    assert await engine.store.count("events") == 0


async def test_one_slow_packet_is_not_a_slow_line(make_engine, net):
    engine = await make_engine()
    net.latencies = [20, 20, 20, 900, 20, 20, 900, 20, 20, 20]
    await ticks(engine, 10)
    assert await engine.store.count("events") == 0
    assert engine.current.line_latency_ms == 20
