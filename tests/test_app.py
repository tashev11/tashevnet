from __future__ import annotations

import httpx

from tashevnet.app import create_app


async def client_for(config):
    app = create_app(config)
    await app.state.store.init()
    transport = httpx.ASGITransport(app=app)
    return app, httpx.AsyncClient(transport=transport, base_url="http://tashevnet.test")


async def test_dashboard_is_served(app_config, net):
    app, client = await client_for(app_config)
    response = await client.get("/")
    assert response.status_code == 200 and "TashevNet" in response.text
    await client.aclose()
    await app.state.engine.close()


async def test_healthz_turns_red_when_checks_are_not_running(app_config, net):
    app, client = await client_for(app_config)
    assert (await client.get("/healthz")).status_code == 503
    await app.state.engine.tick()
    response = await client.get("/healthz")
    assert response.status_code == 200 and response.json()["ok"] is True
    await client.aclose()
    await app.state.engine.close()


async def test_check_now_requires_the_custom_header(app_config, net):
    app, client = await client_for(app_config)
    assert (await client.post("/api/check")).status_code == 403
    response = await client.post("/api/check", headers={"X-TashevNet": "check"})
    assert response.status_code == 200
    assert response.json()["snapshot"]["health"] == "UP"
    status = (await client.get("/api/status")).json()
    assert status["version"] and status["telegram"]["enabled"] is True
    events = (await client.get("/api/events?limit=5")).json()["events"]
    assert events == []
    await client.aclose()
    await app.state.engine.close()
