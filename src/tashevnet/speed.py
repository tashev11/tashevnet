from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import httpx

from .config import SpeedConfig
from .models import SpeedResult
from .probes import short_error


async def measure_speed(config: SpeedConfig) -> SpeedResult:
    """Small download/upload sample; never raises."""
    measured_at = datetime.now(UTC).isoformat()
    base = config.base_url.rstrip("/")
    try:
        timeout = httpx.Timeout(20.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            # Open the connection first: DNS, TCP and TLS setup are not transfer time.
            warmup = await client.get(f"{base}/__down", params={"bytes": 0})
            warmup.raise_for_status()

            started = time.perf_counter()
            response = await client.get(f"{base}/__down", params={"bytes": config.download_bytes})
            response.raise_for_status()
            downloaded = len(response.content)
            download_seconds = max(time.perf_counter() - started, 0.001)

            payload = os.urandom(config.upload_bytes)
            started = time.perf_counter()
            response = await client.post(
                f"{base}/__up",
                content=payload,
                headers={"content-type": "application/octet-stream"},
            )
            response.raise_for_status()
            upload_seconds = max(time.perf_counter() - started, 0.001)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        return SpeedResult(measured_at=measured_at, error=short_error(exc))

    return SpeedResult(
        download_mbps=round(downloaded * 8 / download_seconds / 1_000_000, 2),
        upload_mbps=round(len(payload) * 8 / upload_seconds / 1_000_000, 2),
        measured_at=measured_at,
    )
