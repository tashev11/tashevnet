from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Health(StrEnum):
    UP = "UP"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


class IncidentKind(StrEnum):
    LINK_DOWN = "link_down"
    ROUTER_DOWN = "router_down"
    INTERNET_DOWN = "internet_down"
    DNS_FAILURE = "dns_failure"
    HTTP_FAILURE = "http_failure"
    HIGH_LATENCY = "high_latency"
    VPN_DOWN = "vpn_down"
    VPN_LEAK = "vpn_leak"
    RECOVERED = "recovered"


@dataclass(slots=True)
class ProbeResult:
    name: str
    ok: bool
    latency_ms: float | None = None
    detail: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SpeedResult:
    download_mbps: float | None = None
    upload_mbps: float | None = None
    measured_at: str | None = None
    error: str = ""


@dataclass(slots=True)
class Snapshot:
    timestamp: str
    health: Health
    reason: str
    probes: list[ProbeResult]
    vpn_connected: bool
    vpn_interface: str | None
    public_ip: str | None
    expected_vpn_ip: str | None = None
    gateway: str | None = None
    speed: SpeedResult | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["health"] = self.health.value
        return data
