from tashevnet.models import Health, Snapshot, SpeedResult
from tashevnet.telegram import format_snapshot


def test_format_snapshot_contains_operational_fields():
    snapshot = Snapshot(
        timestamp="2026-09-21T18:00:00+00:00",
        health=Health.UP,
        reason="Connectivity is healthy",
        probes=[],
        vpn_connected=True,
        vpn_interface="utun4",
        public_ip="203.0.113.10",
        gateway="192.168.1.1",
        speed=SpeedResult(download_mbps=100.5, upload_mbps=42.0),
    )
    message = format_snapshot(snapshot)
    assert "🟢" in message
    assert "VPN: ON" in message
    assert "203.0.113.10" in message
    assert "100.5 Mbps" in message
