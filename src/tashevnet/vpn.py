from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import os
import re
import signal
import subprocess

from .probes import console_encoding, run_command, system_name

WINDOWS_ADAPTERS = (
    "Get-NetAdapter | Where-Object Status -eq 'Up' | "
    "ForEach-Object { $_.Name + ' | ' + $_.InterfaceDescription }"
)


def parse_ifconfig_active(text: str) -> list[str]:
    """macOS `ifconfig`: interfaces that are UP and carry an address."""
    active: list[str] = []
    for block in re.split(r"(?=^[A-Za-z0-9_.-]+: flags=)", text, flags=re.MULTILINE):
        match = re.match(r"^([A-Za-z0-9_.-]+): flags=\S*<([^>]*)>", block)
        if not match or "UP" not in match.group(2).split(","):
            continue
        if "inet " in block or "inet6 " in block:
            active.append(match.group(1))
    return active


def parse_ip_link(text: str) -> list[str]:
    """Linux `ip -o link show up`."""
    return re.findall(r"^\d+:\s+([^:@\s]+)", text, flags=re.MULTILINE)


def parse_route_get_interface(text: str) -> str | None:
    """macOS `route -n get <address>`."""
    match = re.search(r"interface:\s*(\S+)", text)
    return match.group(1) if match else None


def parse_ip_route_get_interface(text: str) -> str | None:
    """Linux `ip route get <address>`; follows policy routing (wg-quick, Tailscale)."""
    match = re.search(r"\bdev\s+(\S+)", text)
    return match.group(1) if match else None


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _first_line(text: str) -> str | None:
    lines = _lines(text)
    return lines[0] if lines else None


def _route_target(target: str) -> str:
    try:
        return str(ipaddress.ip_address(target))
    except ValueError:
        return "1.1.1.1"


async def routed_interface(target: str) -> str | None:
    """The interface that actually carries traffic to `target`."""
    system = system_name()
    address = _route_target(target)
    if system == "darwin":
        cmd, parse = ["route", "-n", "get", address], parse_route_get_interface
    elif system == "linux":
        cmd, parse = ["ip", "route", "get", address], parse_ip_route_get_interface
    elif system == "windows":
        script = (
            f"(Find-NetRoute -RemoteIPAddress '{address}' | "
            "Select-Object -First 1).InterfaceAlias"
        )
        cmd, parse = ["powershell", "-NoProfile", "-Command", script], _first_line
    else:
        return None
    try:
        _, text = await run_command(cmd, 5.0)
    except (OSError, TimeoutError):
        return None
    return parse(text)


async def active_network_interfaces() -> list[str]:
    system = system_name()
    if system == "darwin":
        cmd, parse = ["ifconfig"], parse_ifconfig_active
    elif system == "windows":
        cmd, parse = ["powershell", "-NoProfile", "-Command", WINDOWS_ADAPTERS], _lines
    else:
        cmd, parse = ["ip", "-o", "link", "show", "up"], parse_ip_link
    try:
        _, text = await run_command(cmd, 5.0)
    except (OSError, TimeoutError):
        return []
    return parse(text)


def _matches(interface: str, patterns: list[str]) -> bool:
    low = interface.lower()
    return any(pattern and pattern.lower() in low for pattern in patterns)


async def detect_vpn(
    patterns: list[str], target: str = "1.1.1.1"
) -> tuple[bool, str | None, bool]:
    """Return (connected, interface, routed).

    `routed` means Internet traffic really goes through the VPN interface. A VPN
    interface that is up but does not carry that traffic (split tunnel) still counts
    as connected.
    """
    routed = await routed_interface(target)
    if routed and _matches(routed, patterns):
        return True, routed, True
    system = system_name()
    for entry in await active_network_interfaces():
        name = entry.split(" | ", 1)[0]
        # macOS keeps several system utun interfaces up at all times; only a utun
        # that carries the traffic (checked above) means a VPN is on.
        if system == "darwin" and name.lower().startswith("utun"):
            continue
        if _matches(entry, patterns):
            return True, name, False
    return False, None, False


async def run_heal_command(command: str, timeout: float = 60.0) -> tuple[bool, str]:
    """Run the operator's VPN recovery command; stop it if it hangs."""
    if not command.strip():
        return False, "No self-heal command configured"
    posix = os.name != "nt"
    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=posix,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        _kill_tree(proc.pid, posix)
        await proc.wait()
        return False, f"Timed out after {timeout:g} s and was stopped"
    except asyncio.CancelledError:
        _kill_tree(proc.pid, posix)
        raise
    return proc.returncode == 0, stdout.decode(console_encoding(), errors="replace")[-1000:]


def _kill_tree(pid: int, posix: bool) -> None:
    if posix:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGKILL)
    else:
        subprocess.run(
            ["taskkill", "/T", "/F", "/PID", str(pid)], capture_output=True, check=False
        )
