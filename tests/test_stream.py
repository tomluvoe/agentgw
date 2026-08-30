from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentgw.agent.package import load_package
from agentgw.channels.http import create_app
from agentgw.harness.run import Harness
from tests.conftest import DEMO_AGENT
from tests.fakes import ScriptedLLM


async def _read_sse(response) -> list[dict]:
    events = []
    async for line in response.aiter_lines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if raw:
            events.append(json.loads(raw))
    return events


@pytest.mark.asyncio
async def test_chat_stream_sse_and_persist(tmp_path: Path):
    import httpx

    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    app = create_app(Harness(pkg, ScriptedLLM(["Hello world"])))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream(
            "POST", "/v1/chat/stream", json={"message": "hi"}
        ) as response:
            assert response.status_code == 200
            assert "text/event-stream" in response.headers["content-type"]
            events = await _read_sse(response)
    deltas = [e["delta"] for e in events if "delta" in e]
    done = [e for e in events if e.get("done")]
    assert "".join(deltas) == "Hello world"
    assert len(done) == 1
    sid = done[0]["session_id"]

    pkg2 = load_package(DEMO_AGENT, workspace_override=tmp_path)
    app2 = create_app(Harness(pkg2, ScriptedLLM(["again"])))
    transport2 = httpx.ASGITransport(app=app2)
    async with httpx.AsyncClient(transport=transport2, base_url="http://test") as client:
        sessions = (await client.get("/v1/sessions")).json()["sessions"]
        assert sid in sessions
        async with client.stream(
            "POST",
            "/v1/chat/stream",
            json={"message": "next", "session_id": sid},
        ) as response:
            events = await _read_sse(response)
    assert any(e.get("session_id") == sid and e.get("done") for e in events)


@pytest.mark.asyncio
async def test_chat_stream_requires_auth(tmp_path: Path):
    import httpx

    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    app = create_app(Harness(pkg, ScriptedLLM(["x"])), api_key="secret")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/v1/chat/stream", json={"message": "hi"})
        assert denied.status_code == 401
        async with client.stream(
            "POST",
            "/v1/chat/stream",
            json={"message": "hi"},
            headers={"Authorization": "Bearer secret"},
        ) as response:
            assert response.status_code == 200
            events = await _read_sse(response)
    assert any(e.get("done") for e in events)


@pytest.mark.asyncio
async def test_client_assembles_stream(monkeypatch):
    import httpx

    body = b'data: {"delta": "Hel"}\n\ndata: {"delta": "lo"}\n\ndata: {"session_id": "abc", "done": true}\n\n'

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/stream"
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=body,
        )

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("agentgw.channels.client.httpx.AsyncClient", _Client)
    from agentgw.channels.client import AgentClient

    events = []
    async for event in AgentClient("http://127.0.0.1:8080").chat_stream("hi"):
        events.append(event)
    assert [e.get("delta") for e in events if "delta" in e] == ["Hel", "lo"]
    assert events[-1] == {"session_id": "abc", "done": True}
