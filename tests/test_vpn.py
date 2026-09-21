from __future__ import annotations

import asyncio
import os
import time

import pytest

from tashevnet import vpn
from tashevnet.vpn import (
    detect_vpn,
    parse_ifconfig_active,
    parse_ip_link,
    parse_ip_route_get_interface,
    parse_route_get_interface,
    run_heal_command,
)

IFCONFIG = """lo0: flags=8049<UP,LOOPBACK,RUNNING,MULTICAST> mtu 16384
\tinet 127.0.0.1 netmask 0xff000000
en0: flags=8863<UP,BROADCAST,SMART,RUNNING,SIMPLEX,MULTICAST> mtu 1500
\tinet 192.168.0.23 netmask 0xffffff00 broadcast 192.168.0.255
en1: flags=8822<BROADCAST,SMART,SIMPLEX,MULTICAST> mtu 1500
utun0: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1380
\tinet6 fe80::1%utun0 prefixlen 64 scopeid 0x10
ppp0: flags=8051<UP,POINTOPOINT,RUNNING,MULTICAST> mtu 1280
\tinet 10.8.0.2 --> 10.8.0.1 netmask 0xff000000
"""


def test_ifconfig_lists_only_up_interfaces_with_addresses():
    assert parse_ifconfig_active(IFCONFIG) == ["lo0", "en0", "utun0", "ppp0"]


def test_ip_link_names():
    text = "1: lo: <LOOPBACK,UP> mtu 65536\n4: wg0: <POINTOPOINT,UP> mtu 1420\n5: eth0@if7: <UP>"
    assert parse_ip_link(text) == ["lo", "wg0", "eth0"]


def test_route_parsers():
    assert parse_route_get_interface("   route to: 1.1.1.1\n  interface: utun6\n") == "utun6"
    assert parse_ip_route_get_interface("1.1.1.1 dev wg0 table 51820 src 10.0.0.2") == "wg0"


def _fake(monkeypatch, system, routed, interfaces):
    async def fake_routed(target):
        return routed

    async def fake_interfaces():
        return interfaces

    monkeypatch.setattr(vpn, "system_name", lambda: system)
    monkeypatch.setattr(vpn, "routed_interface", fake_routed)
    monkeypatch.setattr(vpn, "active_network_interfaces", fake_interfaces)


PATTERNS = ["utun", "tun", "wg", "ppp", "wintun"]


async def test_macos_full_tunnel_vpn(monkeypatch):
    _fake(monkeypatch, "darwin", "utun6", ["en0", "utun0", "utun6"])
    assert await detect_vpn(PATTERNS) == (True, "utun6", True)


async def test_macos_system_utun_interfaces_are_not_a_vpn(monkeypatch):
    _fake(monkeypatch, "darwin", "en0", ["en0", "utun0", "utun1", "utun2"])
    assert await detect_vpn(PATTERNS) == (False, None, False)


async def test_linux_split_tunnel_counts_as_connected_but_not_routed(monkeypatch):
    _fake(monkeypatch, "linux", "eth0", ["lo", "eth0", "wg0"])
    assert await detect_vpn(PATTERNS) == (True, "wg0", False)


async def test_windows_adapter_description_is_matched(monkeypatch):
    _fake(monkeypatch, "windows", "Wi-Fi", ["Wi-Fi | Intel Wireless", "Office | Wintun Tunnel"])
    assert await detect_vpn(PATTERNS) == (True, "Office", False)


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell command")
async def test_hanging_heal_command_is_stopped_with_its_children(tmp_path):
    marker = tmp_path / "child.pid"
    started = time.monotonic()
    ok, output = await run_heal_command(f"sleep 30 & echo $! > {marker}; wait", timeout=0.5)
    assert not ok and "Timed out" in output
    assert time.monotonic() - started < 5
    child = int(marker.read_text())
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:  # the orphaned child is reaped asynchronously
        try:
            os.kill(child, 0)
        except ProcessLookupError:
            break
        await asyncio.sleep(0.05)
    with pytest.raises(ProcessLookupError):
        os.kill(child, 0)


@pytest.mark.skipif(os.name == "nt", reason="uses a POSIX shell command")
async def test_heal_command_output_and_status():
    assert await run_heal_command("echo reconnected") == (True, "reconnected\n")
    ok, _ = await run_heal_command("exit 3")
    assert ok is False
