from __future__ import annotations

import httpx

from tashevnet import speed
from tashevnet.config import SpeedConfig


async def test_connection_setup_is_not_counted_as_transfer_time(monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(f"{request.method} {request.url.path}?{request.url.query.decode()}")
        size = int(request.url.params.get("bytes", 0))
        return httpx.Response(200, content=b"x" * size)

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        speed.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw)
    )
    result = await speed.measure_speed(SpeedConfig(download_bytes=1000, upload_bytes=100))
    assert seen[0] == "GET /__down?bytes=0"  # warm-up first
    assert seen[1] == "GET /__down?bytes=1000"
    assert seen[2].startswith("POST /__up")
    assert result.error == "" and result.download_mbps > 0 and result.upload_mbps > 0


async def test_failure_is_reported_not_raised(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        speed.httpx, "AsyncClient", lambda **kw: real_client(transport=transport, **kw)
    )
    result = await speed.measure_speed(SpeedConfig())
    assert result.download_mbps is None and result.error == "offline"
