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
            "powershell", "-NoProfile", "-Command",
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


async def detect_vpn(patterns: list[str]) -> tuple[bool, str | None]:
    interfaces = await active_network_interfaces()
    for pattern in patterns:
        p = pattern.lower()
        for interface in interfaces:
            if p in interface.lower():
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
