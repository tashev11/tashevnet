from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import platform
import re
import socket
import time
from datetime import UTC, datetime
from urllib.parse import urlparse

import httpx

from .models import PathCheck, ProbeResult

# RFC 5737 documentation address. Nothing on the public Internet answers it, so any
# reply comes from this machine itself, typically from a proxy-type VPN client.
CANARY_HOST = "203.0.113.1"

# "time=12.3 ms", "time<1ms", "время=12мс", "Zeit=12ms", "temps=12 ms".
_PING_TIME = re.compile(r"[=<]\s*(\d+(?:[.,]\d+)?)\s*(?:ms|мс)\b", re.IGNORECASE)

WINDOWS_GATEWAY = (
    "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | "
    "Where-Object {$_.NextHop -ne '0.0.0.0'} | Select-Object -First 1).NextHop"
)


def system_name() -> str:
    return platform.system().lower()


def short_error(exc: BaseException) -> str:
    text = str(exc).strip()
    return text[:200] if text else type(exc).__name__


def console_encoding() -> str:
    # Windows console tools print in the OEM code page (cp866 on Russian systems).
    return "oem" if system_name() == "windows" else "utf-8"


async def run_command(cmd: list[str], timeout: float) -> tuple[int | None, str]:
    """Run a short local tool; return (exit code, output) and kill it on timeout."""
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        raise
    return proc.returncode, stdout.decode(console_encoding(), errors="replace")


def parse_ping_latency(text: str) -> float | None:
    match = _PING_TIME.search(text)
    return float(match.group(1).replace(",", ".")) if match else None


def ping_command(host: str, timeout: float, system: str | None = None) -> list[str]:
    system = system or system_name()
    if system == "windows":
        return ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
    if system == "darwin":
        return ["ping", "-c", "1", "-W", str(int(timeout * 1000)), host]
    return ["ping", "-c", "1", "-W", str(max(1, round(timeout))), host]


def _ping_failure(text: str) -> str:
    if re.search(r"100(?:\.0)?% packet loss|\b0 (?:packets )?received", text):
        return "no ICMP reply"
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[-1][:160] if lines else "no ICMP reply"


async def ping_probe(host: str, timeout: float = 2.0) -> ProbeResult:
    name = f"ping:{host}"
    meta = {"method": "icmp"}
    try:
        code, text = await run_command(ping_command(host, timeout), timeout + 1.5)
    except TimeoutError:
        return ProbeResult(name, False, detail="no ICMP reply (timed out)", meta=meta)
    except OSError as exc:
        return ProbeResult(name, False, detail=f"ping unavailable: {short_error(exc)}", meta=meta)
    latency = parse_ping_latency(text)
    # Windows ping exits with 0 when a router answers "Destination host unreachable",
    # so only a reply that carries a round-trip time counts as success.
    if code == 0 and latency is not None:
        return ProbeResult(name, True, latency, meta=meta)
    return ProbeResult(name, False, detail=_ping_failure(text), meta=meta)


async def tcp_probe(host: str, port: int = 443, timeout: float = 2.5) -> ProbeResult:
    name = f"tcp:{host}:{port}"
    meta = {"method": "tcp"}
    started = time.perf_counter()
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
    except (OSError, TimeoutError) as exc:
        return ProbeResult(name, False, detail=short_error(exc), meta=meta)
    latency = round((time.perf_counter() - started) * 1000, 2)
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return ProbeResult(name, True, latency, meta=meta)


async def dns_probe(name: str, timeout: float = 2.5) -> ProbeResult:
    started = time.perf_counter()
    loop = asyncio.get_running_loop()
    try:
        result = await asyncio.wait_for(
            loop.getaddrinfo(name, 443, type=socket.SOCK_STREAM), timeout
        )
    except (OSError, TimeoutError, UnicodeError) as exc:
        return ProbeResult(f"dns:{name}", False, detail=short_error(exc), meta={"method": "dns"})
    addresses = sorted({str(item[4][0]) for item in result})
    return ProbeResult(
        f"dns:{name}",
        True,
        round((time.perf_counter() - started) * 1000, 2),
        meta={"method": "dns", "addresses": addresses[:4]},
    )


async def http_probe(client: httpx.AsyncClient, url: str, timeout: float = 4.0) -> ProbeResult:
    name = f"http:{urlparse(url).netloc or url}"
    started = time.perf_counter()
    try:
        response = await client.get(url, timeout=timeout)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        return ProbeResult(name, False, detail=short_error(exc), meta={"method": "http"})
    return ProbeResult(
        name,
        response.status_code < 500,
        round((time.perf_counter() - started) * 1000, 2),
        detail=f"HTTP {response.status_code}",
        meta={"method": "http"},
    )


def _url_host(host: str) -> str:
    try:
        return f"[{host}]" if ipaddress.ip_address(host).version == 6 else host
    except ValueError:
        return host


async def https_probe(client: httpx.AsyncClient, host: str, timeout: float = 3.0) -> ProbeResult:
    """End-to-end reachability: an HTTP answer over TLS from the host itself.

    A local proxy can accept a TCP connection on its own, but it cannot complete a
    TLS handshake and answer an HTTP request on behalf of the remote server.
    """
    name = f"https:{host}"
    new_connection = False

    async def trace(event: str, info: dict) -> None:
        nonlocal new_connection
        if event.startswith("connection.connect_tcp"):
            new_connection = True

    started = time.perf_counter()
    try:
        response = await client.head(
            f"https://{_url_host(host)}/", timeout=timeout, extensions={"trace": trace}
        )
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        return ProbeResult(name, False, detail=short_error(exc), meta={"method": "https"})
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    # A fresh connection includes TCP and TLS setup; only a reused one measures the line.
    return ProbeResult(
        name,
        True,
        None if new_connection else elapsed,
        detail=f"HTTP {response.status_code}",
        meta={"method": "https", "new_connection": new_connection, "elapsed_ms": elapsed},
    )


async def fetch_public_ip(url: str, timeout: float = 4.0) -> str | None:
    """Ask an echo service for the public address over a fresh connection."""
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
    except (httpx.HTTPError, httpx.InvalidURL):
        return None
    if not response.is_success:
        return None
    try:
        return str(ipaddress.ip_address(response.text.strip()))
    except ValueError:
        return None  # a captive portal or an error page, not an address


async def path_check(timeout: float = 1.0) -> PathCheck:
    """Probe CANARY_HOST: a reply means this machine answers probes by itself."""
    ping, tcp = await asyncio.gather(
        ping_probe(CANARY_HOST, timeout), tcp_probe(CANARY_HOST, 443, timeout)
    )
    return PathCheck(
        icmp_spoofed=ping.ok, tcp_local=tcp.ok, checked_at=datetime.now(UTC).isoformat()
    )


def parse_netstat_gateway(text: str) -> str | None:
    match = re.search(r"^default\s+(\d{1,3}(?:\.\d{1,3}){3})\s", text, flags=re.MULTILINE)
    return match.group(1) if match else None


def parse_ip_route_gateway(text: str) -> str | None:
    match = re.search(r"\bdefault\s+via\s+(\S+)", text)
    return match.group(1) if match else None


async def default_gateway() -> str | None:
    """The physical router, even when a full-tunnel VPN owns the default route."""
    system = system_name()
    if system == "darwin":
        cmd = ["netstat", "-rn", "-f", "inet"]
    elif system == "windows":
        cmd = ["powershell", "-NoProfile", "-Command", WINDOWS_GATEWAY]
    else:
        cmd = ["ip", "route", "show", "default"]
    try:
        _, text = await run_command(cmd, 5.0)
    except (OSError, TimeoutError):
        return None
    if system == "darwin":
        return parse_netstat_gateway(text)
    if system == "windows":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[-1] if lines else None
    return parse_ip_route_gateway(text)
