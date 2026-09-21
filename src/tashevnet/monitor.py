from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import statistics
import time
from collections import deque
from datetime import UTC, datetime
from typing import Any

import httpx

from . import __version__
from .classifier import classify, line_latency
from .config import AppConfig
from .models import Health, PathCheck, ProbeResult, Snapshot, SpeedResult
from .probes import (
    default_gateway,
    dns_probe,
    fetch_public_ip,
    http_probe,
    https_probe,
    path_check,
    ping_probe,
    short_error,
)
from .speed import measure_speed
from .state import Observation, StateTracker, Transition
from .storage import Store
from .telegram import TelegramBot, format_transition
from .vpn import detect_vpn, run_heal_command

log = logging.getLogger("tashevnet.monitor")

PRUNE_EVERY_SECONDS = 3600
PATH_CHECK_EVERY_SECONDS = 60
ERROR_NOTICE_EVERY_SECONDS = 900
LATENCY_WINDOW = 5  # checks in the rolling median of line latency
USER_AGENT = f"TashevNet/{__version__} (+https://github.com/tashev11/tashevnet)"


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


async def _nothing() -> None:
    return None


class MonitorEngine:
    """Runs the checks, keeps the confirmed state and records what happened."""

    def __init__(self, config: AppConfig, store: Store | None) -> None:
        self.config = config
        self.store = store
        self.current: Snapshot | None = None
        self.last_speed = SpeedResult()
        monitor = config.monitor
        self.state = StateTracker(monitor.alert_after_checks, monitor.recover_after_checks)
        self.telegram = TelegramBot(config.telegram, self.status, self._recent_events)
        self._tick_lock = asyncio.Lock()
        self._last_tick: float | None = None
        self._last_snapshot_save: float | None = None
        self._last_prune: float | None = None
        self._path: PathCheck | None = None
        self._path_at = 0.0
        self._path_key: tuple[bool, str | None] | None = None
        self._public_ip: str | None = None
        self._public_ip_at = 0.0
        self._public_ip_key: tuple[bool, str | None] | None = None
        self._latencies: deque[float] = deque(maxlen=LATENCY_WINDOW)
        self._vpn_missing_checks = 0
        self._heal_task: asyncio.Task[None] | None = None
        self._last_heal_started: float | None = None
        self._heal_failures = 0
        self._last_error: tuple[str, float] | None = None
        headers = {"User-Agent": USER_AGENT}
        # Reachability of bare IP addresses: any TLS answer from the far end counts,
        # certificates for IP literals are irrelevant here.
        self._reach_client = httpx.AsyncClient(verify=False, timeout=3.0, headers=headers)
        # Web checks keep certificate verification: a broken chain is a finding.
        self._http_client = httpx.AsyncClient(follow_redirects=True, timeout=4.0, headers=headers)

    # ---- state for the API, the dashboard and Telegram -------------------------------

    def state_dict(self) -> dict[str, Any] | None:
        confirmed = self.state.confirmed
        if confirmed is None:
            return None
        return {
            "health": confirmed.health.value,
            "reason": confirmed.reason,
            "since": confirmed.timestamp,
            "incident_started_at": self.state.incident_started_at,
        }

    def status(self) -> dict[str, Any]:
        return {"version": __version__, "snapshot": self.current, "state": self.state_dict()}

    def api_status(self) -> dict[str, Any]:
        age = None if self._last_tick is None else round(time.monotonic() - self._last_tick, 1)
        return {
            "version": __version__,
            "state": self.state_dict(),
            "snapshot": self.current.to_dict() if self.current else None,
            "last_check_seconds_ago": age,
            "telegram": {"enabled": self.telegram.ready, "pending_alerts": self.telegram.pending},
            "settings": {
                "interval_seconds": self.config.monitor.interval_seconds,
                "degraded_latency_ms": self.config.monitor.degraded_latency_ms,
                "vpn_required": self.config.monitor.vpn_required,
                "speed_enabled": self.config.speed.enabled,
            },
        }

    def liveness(self) -> tuple[bool, dict[str, Any]]:
        limit = max(60.0, self.config.monitor.interval_seconds * 6.0)
        age = None if self._last_tick is None else time.monotonic() - self._last_tick
        ok = age is not None and age <= limit
        return ok, {
            "ok": ok,
            "version": __version__,
            "last_check_seconds_ago": None if age is None else round(age, 1),
            "stale_after_seconds": limit,
        }

    async def _recent_events(self, limit: int) -> list[dict[str, Any]]:
        return [] if self.store is None else await self.store.recent_events(limit)

    # ---- one check --------------------------------------------------------------------

    async def collect(self) -> Snapshot:
        monitor = self.config.monitor
        hosts = list(monitor.internet_hosts)
        route_target = next((host for host in hosts if _is_ip(host)), "1.1.1.1")
        gateway, (vpn_connected, vpn_interface, vpn_routed) = await asyncio.gather(
            self._gateway(), detect_vpn(monitor.vpn_interface_patterns, route_target)
        )
        vpn_key = (vpn_connected, vpn_interface)
        path, pings, dns, http, gateway_ping = await asyncio.gather(
            self._path_check(vpn_key),
            asyncio.gather(*(ping_probe(host) for host in hosts)),
            asyncio.gather(*(dns_probe(name) for name in monitor.dns_names)),
            asyncio.gather(*(http_probe(self._http_client, url) for url in monitor.http_urls)),
            ping_probe(gateway) if gateway else _nothing(),
        )
        internet = await self._internet(hosts, list(pings), path)
        probes: list[ProbeResult] = []
        if gateway and gateway_ping is not None:
            probes.append(self._gateway_result(gateway, gateway_ping, internet))
        probes += internet + list(dns) + list(http)
        public_ip = await self._public_ip_for(vpn_key)
        # Without an Internet answer there is no line latency to speak of (the router's
        # round trip alone would read as a perfect line).
        internet_ok = any(item.ok for item in internet)
        latency = self._smoothed_latency(line_latency(probes)) if internet_ok else None
        health, reason = classify(
            probes,
            monitor,
            vpn_connected=vpn_connected,
            public_ip=public_ip,
            latency_ms=latency,
        )
        return Snapshot(
            timestamp=utc_now(),
            health=health,
            reason=reason,
            probes=probes,
            vpn_connected=vpn_connected,
            vpn_interface=vpn_interface,
            public_ip=public_ip,
            expected_vpn_ip=monitor.vpn_expected_ip or None,
            gateway=gateway,
            speed=self.last_speed,
            line_latency_ms=latency,
            vpn_routed=vpn_routed,
            path=path,
        )

    def _smoothed_latency(self, latest: float | None) -> float | None:
        """Median of the last few checks: one slow packet is not a slow line."""
        if latest is not None:
            self._latencies.append(latest)
        return round(statistics.median(self._latencies), 1) if self._latencies else None

    async def _gateway(self) -> str | None:
        return self.config.monitor.gateway or await default_gateway()

    async def _path_check(self, vpn_key: tuple[bool, str | None]) -> PathCheck:
        now = time.monotonic()
        if (
            self._path is not None
            and self._path_key == vpn_key
            and now - self._path_at < PATH_CHECK_EVERY_SECONDS
        ):
            return self._path
        previous, self._path = self._path, await path_check()
        self._path_at, self._path_key = now, vpn_key
        flags = (self._path.icmp_spoofed, self._path.tcp_local)
        changed = previous is None or flags != (previous.icmp_spoofed, previous.tcp_local)
        if changed and any(flags):
            log.info(
                "Something on this machine answers probes for any address "
                "(ICMP answered locally: %s, TCP accepted locally: %s), most likely a "
                "proxy-type VPN client. Internet checks rely on HTTPS answers.",
                *flags,
            )
        return self._path

    async def _internet(
        self, hosts: list[str], pings: list[ProbeResult], path: PathCheck
    ) -> list[ProbeResult]:
        """ICMP when it can be trusted, otherwise an HTTPS answer from the host."""
        trust_icmp = not path.icmp_spoofed
        need_web = [host for host, ping in zip(hosts, pings, strict=True) if not (trust_icmp and ping.ok)]
        web_results = await asyncio.gather(
            *(https_probe(self._reach_client, host) for host in need_web)
        )
        web = dict(zip(need_web, web_results, strict=True))
        results: list[ProbeResult] = []
        for host, ping in zip(hosts, pings, strict=True):
            name = f"internet:{host}"
            if trust_icmp and ping.ok:
                results.append(ProbeResult(name, True, ping.latency_ms, meta={"method": "icmp"}))
                continue
            icmp = "answered locally, ignored" if not trust_icmp else (ping.detail or "no reply")
            check = web[host]
            meta = {**check.meta, "method": "https", "icmp": icmp}
            if check.ok:
                detail = f"{check.detail} · ICMP: {icmp}"
                results.append(ProbeResult(name, True, check.latency_ms, detail, meta))
            else:
                detail = f"ICMP: {icmp} · HTTPS: {check.detail}"
                results.append(ProbeResult(name, False, None, detail, meta))
        return results

    @staticmethod
    def _gateway_result(
        gateway: str, ping: ProbeResult, internet: list[ProbeResult]
    ) -> ProbeResult:
        result = ProbeResult(
            f"gateway:{gateway}", ping.ok, ping.latency_ms, ping.detail, {"method": "icmp"}
        )
        if not result.ok and any(item.ok for item in internet):
            result.detail = "No ICMP reply; ignored because the Internet is reachable"
            result.meta["ignored"] = True
        return result

    async def _public_ip_for(self, vpn_key: tuple[bool, str | None]) -> str | None:
        """Refresh the public IP periodically and whenever the VPN state changes."""
        now = time.monotonic()
        if (
            self._public_ip is not None
            and self._public_ip_key == vpn_key
            and now - self._public_ip_at < self.config.monitor.public_ip_interval_seconds
        ):
            return self._public_ip
        self._public_ip = await fetch_public_ip(self.config.monitor.public_ip_url)
        self._public_ip_at, self._public_ip_key = now, vpn_key
        return self._public_ip

    # ---- the monitoring cycle ---------------------------------------------------------

    async def tick(self) -> Snapshot:
        """One check that updates state, history and alerts. Checks never overlap."""
        if self.store is None:
            raise RuntimeError("tick() needs a Store; use collect() for a one-off check")
        async with self._tick_lock:
            snapshot = await self.collect()
            self.current = snapshot
            self._last_tick = time.monotonic()
            transition = self.state.observe(
                Observation(snapshot.health, snapshot.reason, snapshot.timestamp)
            )
            if transition is not None:
                await self._record(transition, snapshot)
            await self._save_snapshot_if_due(snapshot)
            await self._prune_if_due()
            self._heal_if_needed(snapshot)
            return snapshot

    async def _record(self, transition: Transition, snapshot: Snapshot) -> None:
        current, previous = transition.current, transition.previous
        log.info(
            "%s -> %s: %s",
            previous.health.value if previous else "start",
            current.health.value,
            current.reason,
        )
        self.telegram.notify(format_transition(transition, snapshot))
        payload = {
            "previous": None
            if previous is None
            else {
                "health": previous.health.value,
                "reason": previous.reason,
                "since": previous.timestamp,
            },
            "duration_seconds": transition.duration_seconds,
            "snapshot": snapshot.to_dict(),
        }
        assert self.store is not None
        await self.store.save_event(current.timestamp, current.health.value, current.reason, payload)

    async def _save_snapshot_if_due(self, snapshot: Snapshot) -> None:
        now = time.monotonic()
        every = self.config.monitor.snapshot_interval_seconds
        if self._last_snapshot_save is None or now - self._last_snapshot_save >= every:
            assert self.store is not None
            await self.store.save_snapshot(snapshot)
            self._last_snapshot_save = now

    async def _prune_if_due(self) -> None:
        now = time.monotonic()
        if self._last_prune is not None and now - self._last_prune < PRUNE_EVERY_SECONDS:
            return
        self._last_prune = now
        assert self.store is not None
        days = self.config.monitor.retention_days
        deleted = await self.store.prune(days)
        if deleted:
            log.info("Deleted %d history records older than %d days", deleted, days)

    def _heal_if_needed(self, snapshot: Snapshot) -> None:
        monitor = self.config.monitor
        if not monitor.vpn_required or snapshot.vpn_connected:
            self._vpn_missing_checks = 0
            self._heal_failures = 0
            return
        self._vpn_missing_checks += 1
        if not monitor.self_heal_vpn_command:
            return
        # Same confirmation as alerts: one missed check is not a reason to reconnect.
        if self._vpn_missing_checks < monitor.alert_after_checks:
            return
        if self._heal_task is not None and not self._heal_task.done():
            return
        now = time.monotonic()
        if (
            self._last_heal_started is not None
            and now - self._last_heal_started < monitor.self_heal_cooldown_seconds
        ):
            return
        self._last_heal_started = now
        self._heal_task = asyncio.create_task(self._heal(), name="vpn-self-heal")

    async def _heal(self) -> None:
        monitor = self.config.monitor
        try:
            log.info("VPN is down; running the self-heal command")
            ok, output = await run_heal_command(
                monitor.self_heal_vpn_command, monitor.self_heal_timeout_seconds
            )
        except Exception as exc:
            ok, output = False, short_error(exc)
        tail = output.strip()[-400:]
        suffix = f"\n{tail}" if tail else ""
        if ok:
            self._heal_failures = 0
            log.info("Self-heal command succeeded")
            self.telegram.notify(f"🛠 VPN self-heal command succeeded{suffix}")
            return
        self._heal_failures += 1
        log.warning("Self-heal command failed (%d in a row): %s", self._heal_failures, tail)
        if self._heal_failures == 1:
            self.telegram.notify(
                "🛠 VPN self-heal command failed. It will be retried every "
                f"{monitor.self_heal_cooldown_seconds} s while the VPN is down.{suffix}"
            )

    async def monitor_loop(self) -> None:
        while True:
            started = time.monotonic()
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("Monitoring check failed")
                self._report_error(exc)
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.2, self.config.monitor.interval_seconds - elapsed))

    def _report_error(self, exc: Exception) -> None:
        text = short_error(exc)
        now = time.monotonic()
        if (
            self._last_error is not None
            and self._last_error[0] == text
            and now - self._last_error[1] < ERROR_NOTICE_EVERY_SECONDS
        ):
            return
        self._last_error = (text, now)
        self.telegram.notify(f"⚠️ TashevNet check failed: {text}")

    async def speed_loop(self) -> None:
        await asyncio.sleep(15)
        interval = max(1, self.config.speed.interval_minutes) * 60
        while True:
            confirmed = self.state.confirmed
            if confirmed is not None and confirmed.health == Health.DOWN:
                await asyncio.sleep(min(interval, 300))  # measure soon after recovery
                continue
            self.last_speed = await measure_speed(self.config.speed)
            if self.current is not None:
                self.current.speed = self.last_speed
            await asyncio.sleep(interval)

    async def close(self) -> None:
        if self._heal_task is not None and not self._heal_task.done():
            self._heal_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heal_task
        await self._reach_client.aclose()
        await self._http_client.aclose()
        await self.telegram.close()
