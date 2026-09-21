from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
import pytest

import tashevnet.monitor as monitor_module
from tashevnet.config import AppConfig, MonitorConfig, SpeedConfig, TelegramConfig
from tashevnet.models import PathCheck, ProbeResult
from tashevnet.monitor import MonitorEngine
from tashevnet.storage import Store


@dataclass
class FakeNetwork:
    """A scriptable network: flip the fields between checks to stage an incident."""

    internet: bool = True  # the far end answers at all
    icmp: bool = True  # Internet hosts answer ping
    icmp_spoofed: bool = False  # something local answers ping for any address
    tcp_local: bool = False  # something local accepts TCP for any address
    dns: bool = True
    http: bool = True
    gateway: str | None = "192.168.1.1"
    gateway_ping: bool = True
    vpn: tuple[bool, str | None, bool] = (False, None, False)
    public_ip: str | None = "203.0.113.10"
    latencies: list[float] = field(default_factory=list)  # next ICMP latencies to 1.1.1.1
    https_calls: int = 0

    async def ping_probe(self, host: str, timeout: float = 2.0) -> ProbeResult:
        if host == self.gateway:
            ok, latency = self.gateway_ping, 2.0
        elif self.icmp_spoofed:
            ok, latency = True, 0.3
        else:
            ok = self.internet and self.icmp
            latency = self.latencies.pop(0) if self.latencies and host == "1.1.1.1" else 12.0
        return ProbeResult(
            f"ping:{host}",
            ok,
            latency if ok else None,
            "" if ok else "no ICMP reply",
            {"method": "icmp"},
        )

    async def https_probe(self, client, host: str, timeout: float = 3.0) -> ProbeResult:
        self.https_calls += 1
        ok = self.internet
        return ProbeResult(
            f"https:{host}",
            ok,
            40.0 if ok else None,
            "HTTP 301" if ok else "ConnectError",
            {"method": "https", "new_connection": False},
        )

    async def dns_probe(self, name: str, timeout: float = 2.5) -> ProbeResult:
        ok = self.internet and self.dns
        return ProbeResult(f"dns:{name}", ok, 5.0 if ok else None, "" if ok else "gaierror")

    async def http_probe(self, client, url: str, timeout: float = 4.0) -> ProbeResult:
        ok = self.internet and self.dns and self.http
        return ProbeResult("http:example", ok, 90.0 if ok else None, "HTTP 200" if ok else "error")

    async def path_check(self, timeout: float = 1.0) -> PathCheck:
        return PathCheck(self.icmp_spoofed, self.tcp_local, "2026-09-21T00:00:00+00:00")

    async def default_gateway(self) -> str | None:
        return self.gateway

    async def detect_vpn(self, patterns, target: str = "1.1.1.1"):
        return self.vpn

    async def fetch_public_ip(self, url: str, timeout: float = 4.0) -> str | None:
        return self.public_ip if self.internet else None


class FakeTelegram:
    """Bot API stand-in; set `online = False` to simulate a lost connection."""

    def __init__(self) -> None:
        self.online = True
        self.sent: list[str] = []
        self.updates: list[dict] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        if not self.online:
            raise httpx.ConnectError("[Errno 8] nodename nor servname provided", request=request)
        if request.url.path.endswith("/sendMessage"):
            if self.status != 200:
                return httpx.Response(self.status, json={"ok": False, "description": "rejected"})
            self.sent.append(json.loads(request.content)["text"])
            return httpx.Response(200, json={"ok": True, "result": {}})
        if request.url.path.endswith("/getUpdates"):
            updates, self.updates = self.updates, []
            return httpx.Response(200, json={"ok": True, "result": updates})
        return httpx.Response(404, json={"ok": False})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


@pytest.fixture
def net(monkeypatch) -> FakeNetwork:
    fake = FakeNetwork()
    for name in (
        "ping_probe",
        "https_probe",
        "dns_probe",
        "http_probe",
        "path_check",
        "default_gateway",
        "detect_vpn",
        "fetch_public_ip",
    ):
        monkeypatch.setattr(monitor_module, name, getattr(fake, name))
    return fake


@pytest.fixture
def telegram() -> FakeTelegram:
    return FakeTelegram()


def make_config(tmp_path, **monitor) -> AppConfig:
    return AppConfig(
        db_path=str(tmp_path / "tashevnet.db"),
        monitor=MonitorConfig(internet_hosts=["1.1.1.1", "8.8.8.8"], **monitor),
        speed=SpeedConfig(enabled=False),
        telegram=TelegramConfig(enabled=True, bot_token="123456:TEST-TOKEN", chat_id="42"),
    )


@pytest.fixture
def app_config(tmp_path) -> AppConfig:
    return make_config(tmp_path)


@pytest.fixture
async def make_engine(tmp_path, net, telegram):
    engines: list[MonitorEngine] = []

    async def factory(**monitor) -> MonitorEngine:
        config = make_config(tmp_path, **monitor)
        store = Store(config.db_path)
        await store.init()
        engine = MonitorEngine(config, store)
        await engine.telegram.close()
        engine.telegram._client = telegram.client()
        engines.append(engine)
        return engine

    yield factory
    for engine in engines:
        await engine.close()
