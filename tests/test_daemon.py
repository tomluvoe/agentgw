"""Long-running daemon: disk sessions + REST client attach."""

from __future__ import annotations

from pathlib import Path

import pytest

from agentgw.agent.package import load_package
from agentgw.channels.client import AgentClient
from agentgw.channels.http import create_app
from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.channels.store import SessionStore
from agentgw.harness.run import Harness
from agentgw.harness.session import Session
from agentgw.llm.types import Message, ToolCall
from tests.conftest import DEMO_AGENT
from tests.fakes import ScriptedLLM


def test_session_store_roundtrip(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions")
    session = Session.create("demo")
    session.add_message(Message(role="user", content="hi"))
    session.add_message(
        Message(
            role="assistant",
            content=None,
            tool_calls=[ToolCall(id="1", name="echo", arguments='{"text":"x"}')],
        )
    )
    session.add_message(Message(role="tool", content="x", tool_call_id="1", name="echo"))
    store.save(session)
    loaded = store.load(session.id)
    assert loaded is not None
    assert loaded.id == session.id
    assert [m.role for m in loaded.messages] == ["user", "assistant", "tool"]
    assert loaded.messages[1].tool_calls[0].name == "echo"
    assert session.id in store.list_ids()


def test_session_store_rejects_bad_id(tmp_path: Path):
    store = SessionStore(tmp_path)
    with pytest.raises(ValueError):
        store.path_for("../escape")


@pytest.mark.asyncio
async def test_sessions_survive_new_process_map(tmp_path: Path):
    store = SessionStore(tmp_path / "sessions")
    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    first = Harness(pkg, ScriptedLLM(["one", "two"]))
    sessions = SessionMap(store)
    reply, session = await handle_inbound(first, sessions, "", "hello")
    assert reply == "one"
    sid = session.id

    pkg2 = load_package(DEMO_AGENT, workspace_override=tmp_path)
    second = Harness(pkg2, ScriptedLLM(["two"]))
    restored = SessionMap(store)
    reply2, session2 = await handle_inbound(second, restored, sid, "again")
    assert reply2 == "two"
    assert session2.id == sid
    users = [m.content for m in session2.messages if m.role == "user"]
    assert "hello" in users and "again" in users


@pytest.mark.asyncio
async def test_rest_daemon_persists_sessions(tmp_path: Path):
    import httpx

    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    app = create_app(Harness(pkg, ScriptedLLM(["pong", "pong2"])))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = (await client.get("/health")).json()
        assert health["agent"] == "demo"
        first = (await client.post("/v1/chat", json={"message": "hello"})).json()
        assert first["response"] == "pong"
        sid = first["session_id"]
        listed = (await client.get("/v1/sessions")).json()["sessions"]
        assert sid in listed
        second = (
            await client.post("/v1/chat", json={"message": "again", "session_id": sid})
        ).json()
        assert second["session_id"] == sid
        assert second["response"] == "pong2"

    # New process, same workspace: history is on disk.
    pkg2 = load_package(DEMO_AGENT, workspace_override=tmp_path)
    app2 = create_app(Harness(pkg2, ScriptedLLM(["from-disk"])))
    transport2 = httpx.ASGITransport(app=app2)
    async with httpx.AsyncClient(transport=transport2, base_url="http://test") as client:
        third = (
            await client.post("/v1/chat", json={"message": "still there?", "session_id": sid})
        ).json()
        assert third["session_id"] == sid
        assert third["response"] == "from-disk"


@pytest.mark.asyncio
async def test_agent_client_http_shape(monkeypatch):
    import httpx

    captured: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((request.method, str(request.url)))
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "ok", "agent": "demo"})
        if path == "/v1/skills":
            return httpx.Response(200, json=[{"name": "greet", "path": "/x"}])
        if path == "/v1/tools":
            return httpx.Response(200, json=["read"])
        if path == "/v1/sessions":
            return httpx.Response(200, json={"sessions": ["abc"]})
        if path == "/v1/chat":
            return httpx.Response(200, json={"session_id": "abc", "response": "hi"})
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("agentgw.channels.client.httpx.AsyncClient", _Client)
    client = AgentClient("http://127.0.0.1:8080")
    assert (await client.health())["agent"] == "demo"
    assert (await client.skills())[0]["name"] == "greet"
    assert await client.tools() == ["read"]
    assert await client.sessions() == ["abc"]
    chat = await client.chat("hello", session_id="abc")
    assert chat["response"] == "hi"
    assert any(path.endswith("/v1/chat") for _, path in captured)
