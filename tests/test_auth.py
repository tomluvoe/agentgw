from __future__ import annotations

from pathlib import Path

import pytest

from agentgw.agent.package import load_package
from agentgw.channels.http import create_app
from agentgw.harness.run import Harness
from tests.conftest import DEMO_AGENT
from tests.fakes import ScriptedLLM


@pytest.fixture
def demo_harness(tmp_path: Path):
    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    return Harness(pkg, ScriptedLLM(["ok"]))


@pytest.mark.asyncio
async def test_v1_open_when_no_key(demo_harness):
    import httpx

    app = create_app(demo_harness, api_key=None)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/v1/tools")).status_code == 200


@pytest.mark.asyncio
async def test_v1_requires_bearer_when_key_set(demo_harness):
    import httpx

    app = create_app(demo_harness, api_key="secret")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        assert health.status_code == 200
        denied = await client.get("/v1/tools")
        assert denied.status_code == 401
        wrong = await client.get(
            "/v1/tools", headers={"Authorization": "Bearer nope"}
        )
        assert wrong.status_code == 401
        ok = await client.get(
            "/v1/tools", headers={"Authorization": "Bearer secret"}
        )
        assert ok.status_code == 200
        chat = await client.post(
            "/v1/chat",
            json={"message": "hi"},
            headers={"Authorization": "Bearer secret"},
        )
        assert chat.status_code == 200
        assert chat.json()["response"] == "ok"


@pytest.mark.asyncio
async def test_client_sends_api_key(monkeypatch):
    import httpx

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization", ""))
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok", "agent": "demo"})
        if request.url.path == "/v1/tools":
            return httpx.Response(200, json=["read"])
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("agentgw.channels.client.httpx.AsyncClient", _Client)
    from agentgw.channels.client import AgentClient

    client = AgentClient("http://127.0.0.1:8080", api_key="secret")
    await client.health()
    await client.tools()
    assert seen[0] == ""  # health is public
    assert seen[1] == "Bearer secret"
