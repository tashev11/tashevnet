from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Health(StrEnum):
    UP = "UP"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"
    UNKNOWN = "UNKNOWN"


# How bad a state is. UNKNOWN is not an incident: it only means "not enough data".
SEVERITY: dict[Health, int] = {
    Health.UP: 0,
    Health.UNKNOWN: 0,
    Health.DEGRADED: 1,
    Health.DOWN: 2,
}


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
class PathCheck:
    """Whether something on this machine answers probes on the Internet's behalf.

    Proxy-type VPN clients in TUN mode accept any TCP connection locally, and some
    of them reply to ICMP themselves. Such an answer proves nothing about the
    Internet, so TashevNet probes an address that cannot answer (see CANARY_HOST).
    """

    icmp_spoofed: bool = False
    tcp_local: bool = False
    checked_at: str | None = None


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
    line_latency_ms: float | None = None
    vpn_routed: bool = False
    path: PathCheck | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["health"] = self.health.value
        return data
