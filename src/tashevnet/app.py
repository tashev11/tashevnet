from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from importlib.resources import files

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from . import __version__
from .config import AppConfig
from .monitor import MonitorEngine
from .storage import Store

log = logging.getLogger("tashevnet.app")

CHECK_HEADER_VALUE = "check"


def _supervised(name: str, loop: Callable[[], Awaitable[None]]) -> asyncio.Task[None]:
    """Keep a background loop alive: a crash is logged and the loop restarts."""

    async def runner() -> None:
        while True:
            try:
                await loop()
                log.error("%s loop stopped unexpectedly; restarting", name)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("%s loop crashed; restarting in 5 s", name)
            await asyncio.sleep(5)

    return asyncio.create_task(runner(), name=name)


def create_app(config: AppConfig) -> FastAPI:
    store = Store(config.db_path)
    engine = MonitorEngine(config, store)
    tasks: list[asyncio.Task[None]] = []

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await store.init()
        tasks.append(_supervised("monitor", engine.monitor_loop))
        if config.speed.enabled:
            tasks.append(_supervised("speed", engine.speed_loop))
        if engine.telegram.ready:
            tasks.append(_supervised("telegram-alerts", engine.telegram.delivery_loop))
            if config.telegram.polling:
                tasks.append(_supervised("telegram-commands", engine.telegram.polling_loop))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await engine.close()

    app = FastAPI(
        title="TashevNet",
        version=__version__,
        description="Local network flight recorder and VPN watchdog.",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.store = store

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def dashboard() -> str:
        return files("tashevnet.static").joinpath("index.html").read_text(encoding="utf-8")

    @app.get("/healthz", summary="Liveness: 503 when checks have stopped")
    async def healthz() -> JSONResponse:
        ok, body = engine.liveness()
        return JSONResponse(body, status_code=200 if ok else 503)

    @app.get("/api/status", summary="Confirmed state and the latest check")
    async def status() -> dict:
        return engine.api_status()

    @app.get("/api/events", summary="Recent confirmed state changes, newest first")
    async def events(limit: int = 25) -> dict:
        return {"events": await store.recent_events(limit)}

    @app.post("/api/check", summary="Run a check now")
    async def check_now(x_tashevnet: str | None = Header(default=None)) -> dict:
        # A custom header cannot be sent cross-site without a CORS preflight, which
        # this API never approves; other web pages therefore cannot trigger checks.
        if x_tashevnet != CHECK_HEADER_VALUE:
            raise HTTPException(status_code=403, detail="Send the header X-TashevNet: check")
        await engine.tick()
        return engine.api_status()

    return app
