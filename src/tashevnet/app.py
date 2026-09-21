from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from importlib.resources import files

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .config import AppConfig
from .monitor import MonitorEngine
from .storage import Store


def create_app(config: AppConfig) -> FastAPI:
    store = Store(config.db_path)
    engine = MonitorEngine(config, store)
    tasks: list[asyncio.Task] = []

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await store.init()
        tasks.append(asyncio.create_task(engine.monitor_loop(), name="monitor"))
        if engine.telegram.ready and config.telegram.polling:
            tasks.append(asyncio.create_task(engine.telegram.polling_loop(), name="telegram"))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            await engine.telegram.close()

    app = FastAPI(
        title="TashevNet",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.engine = engine
    app.state.store = store

    @app.get("/", response_class=HTMLResponse)
    async def dashboard() -> str:
        return files("tashevnet.static").joinpath("index.html").read_text(encoding="utf-8")

    @app.get("/healthz")
    async def healthz() -> dict:
        return {"ok": True, "monitor_started": engine.current is not None}

    @app.get("/api/status")
    async def status() -> dict:
        snapshot = engine.current
        return {
            "version": "0.1.0",
            "snapshot": snapshot.to_dict() if snapshot else None,
        }

    @app.get("/api/events")
    async def events(limit: int = 25) -> dict:
        return {"events": await store.recent_events(limit)}

    @app.post("/api/check")
    async def check_now() -> dict:
        snapshot = await engine.tick()
        return snapshot.to_dict()

    return app
