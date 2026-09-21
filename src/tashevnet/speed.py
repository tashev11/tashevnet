from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import httpx

from .config import SpeedConfig
from .models import SpeedResult


async def measure_speed(config: SpeedConfig) -> SpeedResult:
    measured_at = datetime.now(UTC).isoformat()
    try:
        timeout = httpx.Timeout(20.0, connect=5.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            started = time.perf_counter()
            response = await client.get(
                f"{config.base_url.rstrip('/')}/__down",
                params={"bytes": config.download_bytes},
            )
            response.raise_for_status()
            downloaded = len(response.content)
            download_seconds = max(time.perf_counter() - started, 0.001)
            download_mbps = downloaded * 8 / download_seconds / 1_000_000

            payload = os.urandom(config.upload_bytes)
            started = time.perf_counter()
            response = await client.post(
                f"{config.base_url.rstrip('/')}/__up",
                content=payload,
                headers={"content-type": "application/octet-stream"},
            )
            response.raise_for_status()
            upload_seconds = max(time.perf_counter() - started, 0.001)
            upload_mbps = len(payload) * 8 / upload_seconds / 1_000_000

        return SpeedResult(
            download_mbps=round(download_mbps, 2),
            upload_mbps=round(upload_mbps, 2),
            measured_at=measured_at,
        )
    except Exception as exc:
        return SpeedResult(measured_at=measured_at, error=str(exc))
