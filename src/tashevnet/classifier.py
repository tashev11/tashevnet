from __future__ import annotations

from .config import MonitorConfig
from .models import Health, ProbeResult


def _group(probes: list[ProbeResult], prefix: str) -> list[ProbeResult]:
    return [item for item in probes if item.name.startswith(prefix)]


def line_latency(probes: list[ProbeResult]) -> float | None:
    """Worst round-trip time of the line: router and Internet probes only.

    HTTP and DNS timings include server and resolver work, so they never count.
    """
    latencies = [
        item.latency_ms
        for item in _group(probes, "gateway:") + _group(probes, "internet:")
        if item.ok and item.latency_ms is not None
    ]
    return max(latencies) if latencies else None


def classify(
    probes: list[ProbeResult],
    config: MonitorConfig,
    *,
    vpn_connected: bool,
    public_ip: str | None,
    latency_ms: float | None = None,
) -> tuple[Health, str]:
    """Name the most likely broken layer. Reasons never contain numbers, so a steady
    problem keeps the same reason from check to check.

    `latency_ms` is the line latency to judge (the monitor passes a smoothed value);
    without it, the worst latency of these probes is used.
    """
    gateway = _group(probes, "gateway:")
    internet = _group(probes, "internet:")
    dns = _group(probes, "dns:")
    http = _group(probes, "http:")
    vpn_missing = config.vpn_required and not vpn_connected

    if internet and not any(item.ok for item in internet):
        # A router that ignores ping is normal; it only matters when nothing else works.
        if gateway and not any(item.ok for item in gateway):
            return Health.DOWN, "Router/default gateway is unreachable"
        if vpn_missing:
            return Health.DOWN, (
                "VPN is disconnected and the Internet is unreachable "
                "(VPN kill switch or ISP outage)"
            )
        return Health.DOWN, "Internet/WAN probes are unreachable"

    if vpn_missing:
        return Health.DOWN, "VPN is required but no active VPN interface was detected"

    if (
        config.vpn_required
        and config.vpn_expected_ip
        and public_ip
        and public_ip != config.vpn_expected_ip
    ):
        return Health.DOWN, "Possible VPN leak: public IP does not match expected VPN IP"

    if internet and dns and not any(item.ok for item in dns):
        return Health.DEGRADED, "Internet works by IP, but DNS resolution is failing"

    if dns and any(item.ok for item in dns) and http and not any(item.ok for item in http):
        return Health.DEGRADED, "DNS works, but HTTP checks are failing"

    latency = latency_ms if latency_ms is not None else line_latency(probes)
    if latency is not None and latency >= config.degraded_latency_ms:
        return Health.DEGRADED, "High line latency"

    if any(item.ok for item in internet + dns + http):
        return Health.UP, "Connectivity is healthy"

    return Health.UNKNOWN, "Not enough probe data to determine connectivity"
