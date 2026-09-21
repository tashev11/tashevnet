from __future__ import annotations

from .config import MonitorConfig
from .models import Health, ProbeResult


def _group(probes: list[ProbeResult], prefix: str) -> list[ProbeResult]:
    return [item for item in probes if item.name.startswith(prefix)]


def classify(
    probes: list[ProbeResult],
    config: MonitorConfig,
    *,
    vpn_connected: bool,
    public_ip: str | None,
) -> tuple[Health, str]:
    gateway = _group(probes, "gateway:")
    internet = _group(probes, "internet:")
    dns = _group(probes, "dns:")
    http = _group(probes, "http:")

    if gateway and not any(item.ok for item in gateway):
        return Health.DOWN, "Router/default gateway is unreachable"

    if internet and not any(item.ok for item in internet):
        return Health.DOWN, "Internet/WAN probes are unreachable"

    if internet and any(item.ok for item in internet) and dns and not any(item.ok for item in dns):
        return Health.DEGRADED, "Internet works by IP, but DNS resolution is failing"

    if dns and any(item.ok for item in dns) and http and not any(item.ok for item in http):
        return Health.DEGRADED, "DNS works, but HTTP checks are failing"

    if config.vpn_required and not vpn_connected:
        return Health.DOWN, "VPN is required but no active VPN interface was detected"

    if (
        config.vpn_required
        and config.vpn_expected_ip
        and public_ip
        and public_ip != config.vpn_expected_ip
    ):
        return Health.DOWN, "Possible VPN leak: public IP does not match expected VPN IP"

    latencies = [item.latency_ms for item in probes if item.ok and item.latency_ms is not None]
    if latencies and max(latencies) >= config.degraded_latency_ms:
        return Health.DEGRADED, f"High latency detected: {max(latencies):.0f} ms"

    if any(item.ok for item in internet + dns + http):
        return Health.UP, "Connectivity is healthy"

    return Health.UNKNOWN, "Not enough probe data to determine connectivity"
