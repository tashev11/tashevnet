from __future__ import annotations

import asyncio
import platform
import re


async def active_network_interfaces() -> list[str]:
    system = platform.system().lower()
    if system == "darwin":
        cmd = ["ifconfig"]
    elif system == "windows":
        cmd = [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-NetAdapter | Where-Object Status -eq 'Up' | Select-Object -ExpandProperty Name",
        ]
    else:
        cmd = ["ip", "-o", "link", "show", "up"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        text = stdout.decode(errors="replace")
        if system == "darwin":
            blocks = re.split(r"(?=^[A-Za-z0-9_.-]+: flags=)", text, flags=re.MULTILINE)
            active: list[str] = []
            for block in blocks:
                match = re.match(r"^([A-Za-z0-9_.-]+): flags=.*<([^>]+)>", block)
                if match and "UP" in match.group(2) and ("inet " in block or "inet6 " in block):
                    active.append(match.group(1))
            return active
        if system == "windows":
            return [line.strip() for line in text.splitlines() if line.strip()]
        return re.findall(r"^\d+:\s+([^:@]+)", text, flags=re.MULTILINE)
    except Exception:
        return []


async def default_route_interface() -> str | None:
    system = platform.system().lower()
    if system == "darwin":
        cmd = ["route", "-n", "get", "default"]
    elif system == "linux":
        cmd = ["ip", "route", "show", "default"]
    else:
        return None

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        text = stdout.decode(errors="replace")
        if system == "darwin":
            match = re.search(r"interface:\s*([^\s]+)", text)
        else:
            match = re.search(r"\bdev\s+([^\s]+)", text)
        return match.group(1) if match else None
    except Exception:
        return None


def _matches(interface: str, patterns: list[str]) -> bool:
    low = interface.lower()
    return any(pattern.lower() in low for pattern in patterns)


async def detect_vpn(patterns: list[str]) -> tuple[bool, str | None]:
    routed = await default_route_interface()
    if routed and _matches(routed, patterns):
        return True, routed

    interfaces = await active_network_interfaces()
    system = platform.system().lower()
    for interface in interfaces:
        if system == "darwin" and interface.lower().startswith("utun"):
            continue
        if _matches(interface, patterns):
            return True, interface
    return False, None


async def run_heal_command(command: str) -> tuple[bool, str]:
    if not command.strip():
        return False, "No self-heal command configured"
    proc = await asyncio.create_subprocess_shell(
        command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    stdout, _ = await proc.communicate()
    return proc.returncode == 0, stdout.decode(errors="replace")[-1000:]
