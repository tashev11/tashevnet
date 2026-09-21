from __future__ import annotations

import httpx
import pytest

from tashevnet import probes
from tashevnet.probes import (
    fetch_public_ip,
    https_probe,
    parse_ip_route_gateway,
    parse_netstat_gateway,
    parse_ping_latency,
    ping_command,
)

MACOS_PING = """PING 1.1.1.1 (1.1.1.1): 56 data bytes
64 bytes from 1.1.1.1: icmp_seq=0 ttl=57 time=12.345 ms
"""
LINUX_PING = """64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=8.91 ms
rtt min/avg/max/mdev = 8.910/8.910/8.910/0.000 ms"""
WINDOWS_EN = "Reply from 1.1.1.1: bytes=32 time=14ms TTL=57"
WINDOWS_RU = "Ответ от 1.1.1.1: число байт=32 время=14мс TTL=57"
WINDOWS_FAST = "Reply from 192.168.1.1: bytes=32 time<1ms TTL=64"
WINDOWS_UNREACHABLE = "Reply from 192.168.1.1: Destination host unreachable."


@pytest.mark.parametrize(
    ("text", "expected"),
    [(MACOS_PING, 12.345), (LINUX_PING, 8.91), (WINDOWS_EN, 14), (WINDOWS_RU, 14),
     (WINDOWS_FAST, 1), (WINDOWS_UNREACHABLE, None)],
)
def test_ping_latency_is_parsed_in_any_language(text, expected):
    assert parse_ping_latency(text) == expected


def test_ping_command_uses_each_systems_timeout_units():
    assert ping_command("1.1.1.1", 2.0, "darwin")[-2] == "2000"  # milliseconds
    assert ping_command("1.1.1.1", 2.0, "linux")[-2] == "2"  # seconds
    assert ping_command("1.1.1.1", 2.0, "windows")[-2] == "2000"


async def test_windows_unreachable_reply_is_not_success(monkeypatch):
    async def fake_run(cmd, timeout):
        return 0, WINDOWS_UNREACHABLE  # Windows exits with 0 here

    monkeypatch.setattr(probes, "run_command", fake_run)
    result = await probes.ping_probe("8.8.8.8")
    assert result.ok is False


async def test_missing_ping_binary_is_reported(monkeypatch):
    async def fake_run(cmd, timeout):
        raise FileNotFoundError("ping")

    monkeypatch.setattr(probes, "run_command", fake_run)
    result = await probes.ping_probe("8.8.8.8")
    assert result.ok is False and "unavailable" in result.detail


def test_macos_gateway_is_the_physical_router_behind_a_vpn():
    table = """Routing tables

Internet:
Destination        Gateway            Flags               Netif Expire
default            link#23            UCSg                utun6
default            192.168.0.1        UGScIg                en0
127                127.0.0.1          UCS                   lo0
"""
    assert parse_netstat_gateway(table) == "192.168.0.1"


def test_linux_gateway():
    assert parse_ip_route_gateway("default via 10.0.0.1 dev eth0 proto dhcp") == "10.0.0.1"
    assert parse_ip_route_gateway("") is None


async def test_https_probe_counts_any_answer_from_the_host():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(301)))
    result = await https_probe(client, "1.1.1.1")
    await client.aclose()
    assert result.ok and result.meta["method"] == "https" and result.detail == "HTTP 301"


async def test_https_probe_fails_when_nobody_answers():
    def refuse(request):
        raise httpx.ConnectError("Connection reset by peer", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(refuse))
    result = await https_probe(client, "2606:4700:4700::1111")
    await client.aclose()
    assert not result.ok and "reset" in result.detail


@pytest.mark.parametrize(
    ("body", "expected"),
    [("203.0.113.7\n", "203.0.113.7"), ("<html>Hotel Wi-Fi login</html>", None)],
)
async def test_public_ip_must_look_like_an_address(monkeypatch, body, expected):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(lambda r: httpx.Response(200, text=body))
    monkeypatch.setattr(
        probes.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw)
    )
    assert await fetch_public_ip("https://api.ipify.org") == expected
