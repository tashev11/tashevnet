from tashevnet.classifier import classify
from tashevnet.config import MonitorConfig
from tashevnet.models import Health, ProbeResult


def p(name: str, ok: bool, latency: float | None = 20) -> ProbeResult:
    return ProbeResult(name=name, ok=ok, latency_ms=latency if ok else None)


def test_healthy_connection():
    probes = [p("internet:1.1.1.1", True), p("dns:github.com", True), p("http:github.com", True)]
    health, reason = classify(probes, MonitorConfig(), vpn_connected=False, public_ip="1.2.3.4")
    assert health == Health.UP
    assert "healthy" in reason.lower()


def test_dns_failure_is_distinguished_from_wan_outage():
    probes = [p("internet:1.1.1.1", True), p("dns:github.com", False)]
    health, reason = classify(probes, MonitorConfig(), vpn_connected=False, public_ip="1.2.3.4")
    assert health == Health.DEGRADED
    assert "dns" in reason.lower()


def test_vpn_required_and_missing_is_down():
    probes = [p("internet:1.1.1.1", True), p("dns:github.com", True)]
    cfg = MonitorConfig(vpn_required=True)
    health, reason = classify(probes, cfg, vpn_connected=False, public_ip="1.2.3.4")
    assert health == Health.DOWN
    assert "vpn" in reason.lower()


def test_vpn_leak_when_expected_ip_differs():
    probes = [p("internet:1.1.1.1", True), p("dns:github.com", True)]
    cfg = MonitorConfig(vpn_required=True, vpn_expected_ip="9.9.9.9")
    health, reason = classify(probes, cfg, vpn_connected=True, public_ip="1.2.3.4")
    assert health == Health.DOWN
    assert "leak" in reason.lower()
