from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

from .classifier import classify
from .config import AppConfig
from .models import Snapshot, SpeedResult
from .probes import default_gateway, dns_probe, fetch_public_ip, http_probe, ping_probe, tcp_probe
from .speed import measure_speed
from .storage import Store
from .telegram import TelegramBot
from .vpn import detect_vpn, run_heal_command


class MonitorEngine:
    def __init__(self, config: AppConfig, store: Store) -> None:
        self.config = config
        self.store = store
        self.current: Snapshot | None = None
        self.last_speed = SpeedResult()
        self._last_heal_monotonic = 0.0
        self.telegram = TelegramBot(config.telegram, self.status, self.store.recent_events)

    def status(self) -> dict[str, Any]:
        return {"snapshot": self.current, "version": "0.1.0"}

    async def _internet_probe(self, host: str):
        ping = await ping_probe(host)
        if ping.ok:
            ping.name = f"internet:{host}"
            return ping
        tcp = await tcp_probe(host, 443)
        tcp.name = f"internet:{host}"
        return tcp

    async def collect(self) -> Snapshot:
        gateway = self.config.monitor.gateway or await default_gateway()
        tasks = [self._internet_probe(host) for host in self.config.monitor.internet_hosts]
        tasks += [dns_probe(name) for name in self.config.monitor.dns_names]
        tasks += [http_probe(url) for url in self.config.monitor.http_urls]
        if gateway:
            tasks.append(ping_probe(gateway))
        probes = list(await asyncio.gather(*tasks))
        if gateway and probes:
            probes[-1].name = f"gateway:{gateway}"

        vpn_connected, vpn_interface = await detect_vpn(
            self.config.monitor.vpn_interface_patterns
        )
        public_ip = await fetch_public_ip(self.config.monitor.public_ip_url)
        health, reason = classify(
            probes,
            self.config.monitor,
            vpn_connected=vpn_connected,
            public_ip=public_ip,
        )
        return Snapshot(
            timestamp=datetime.now(UTC).isoformat(),
            health=health,
            reason=reason,
            probes=probes,
            vpn_connected=vpn_connected,
            vpn_interface=vpn_interface,
            public_ip=public_ip,
            expected_vpn_ip=self.config.monitor.vpn_expected_ip or None,
            gateway=gateway,
            speed=self.last_speed,
        )

    async def _maybe_heal_vpn(self, snapshot: Snapshot) -> None:
        monitor = self.config.monitor
        if not monitor.vpn_required or snapshot.vpn_connected or not monitor.self_heal_vpn_command:
            return
        now = time.monotonic()
        if now - self._last_heal_monotonic < monitor.self_heal_cooldown_seconds:
            return
        self._last_heal_monotonic = now
        ok, output = await run_heal_command(monitor.self_heal_vpn_command)
        result = "succeeded" if ok else "failed"
        await self.telegram.send(f"🛠 VPN self-heal {result}\n{output[-500:]}")

    async def tick(self) -> Snapshot:
        previous = self.current
        snapshot = await self.collect()
        changed = previous is None or (
            previous.health != snapshot.health or previous.reason != snapshot.reason
        )
        self.current = snapshot
        await self.store.save_snapshot(snapshot)
        if changed:
            await self.store.save_snapshot(snapshot, event=True)
            await self.telegram.notify_snapshot(snapshot)
        await self._maybe_heal_vpn(snapshot)
        return snapshot

    async def monitor_loop(self) -> None:
        while True:
            started = time.monotonic()
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                await self.telegram.send(f"⚠️ TashevNet monitor error: {exc}")
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.2, self.config.monitor.interval_seconds - elapsed))

    async def speed_loop(self) -> None:
        await asyncio.sleep(5)
        interval = max(1, self.config.speed.interval_minutes) * 60
        while True:
            try:
                if self.current is not None and self.current.health.value != "DOWN":
                    self.last_speed = await measure_speed(self.config.speed)
                    self.current.speed = self.last_speed
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_speed = SpeedResult(
                    measured_at=datetime.now(UTC).isoformat(),
                    error=str(exc),
                )
            await asyncio.sleep(interval)
