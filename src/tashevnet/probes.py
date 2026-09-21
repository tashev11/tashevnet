from __future__ import annotations

import asyncio
import platform
import re
import socket
import time
from urllib.parse import urlparse

import httpx

from .models import ProbeResult


async def ping_probe(host: str, timeout: float = 2.0) -> ProbeResult:
    system = platform.system().lower()
    args = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), host]
    if system == "windows":
        args = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
    elif system == "darwin":
        args = ["ping", "-c", "1", "-W", str(int(timeout * 1000)), host]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout + 1)
        ok = proc.returncode == 0
        text = (stdout if ok else stderr or stdout).decode(errors="replace")
        match = re.search(r"time[=<]([0-9.]+)\s*ms", text)
        latency = float(match.group(1)) if match else None
        return ProbeResult(
            name=f"ping:{host}",
            ok=ok,
            latency_ms=latency,
            detail=text.strip()[-300:] if not ok else "",
        )
    except Exception as exc:
        return ProbeResult(name=f"ping:{host}", ok=False, detail=str(exc))


async def tcp_probe(host: str, port: int = 443, timeout: float = 2.5) -> ProbeResult:
    started = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        del reader
        writer.close()
        await writer.wait_closed()
        return ProbeResult(
            name=f"tcp:{host}:{port}",
            ok=True,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )
    except Exception as exc:
        return ProbeResult(name=f"tcp:{host}:{port}", ok=False, detail=str(exc))


async def dns_probe(name: str, timeout: float = 2.5) -> ProbeResult:
    started = time.perf_counter()
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(loop.getaddrinfo(name, 443, type=socket.SOCK_STREAM), timeout)
        addresses = sorted({item[4][0] for item in result})
        return ProbeResult(
            name=f"dns:{name}",
            ok=True,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            meta={"addresses": addresses[:4]},
        )
    except Exception as exc:
        return ProbeResult(name=f"dns:{name}", ok=False, detail=str(exc))


async def http_probe(url: str, timeout: float = 4.0) -> ProbeResult:
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            response = await client.get(url)
        return ProbeResult(
            name=f"http:{urlparse(url).netloc}",
            ok=response.status_code < 500,
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            detail=f"HTTP {response.status_code}",
        )
    except Exception as exc:
        return ProbeResult(name=f"http:{urlparse(url).netloc}", ok=False, detail=str(exc))


async def fetch_public_ip(url: str, timeout: float = 4.0) -> str | None:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.text.strip()
    except Exception:
        return None


async def default_gateway() -> str | None:
    system = platform.system().lower()
    if system == "darwin":
        cmd = ["route", "-n", "get", "default"]
    elif system == "windows":
        command = (
            "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | "
            "Select-Object -First 1).NextHop"
        )
        cmd = ["powershell", "-NoProfile", "-Command", command]
    else:
        cmd = ["ip", "route", "show", "default"]

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        text = stdout.decode(errors="replace")
        if system == "darwin":
            match = re.search(r"gateway:\s*([^\s]+)", text)
        elif system == "windows":
            value = text.strip().splitlines()
            return value[-1].strip() if value else None
        else:
            match = re.search(r"default\s+via\s+([^\s]+)", text)
        return match.group(1) if match else None
    except Exception:
        return None
