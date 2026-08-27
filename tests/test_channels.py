from __future__ import annotations

from pathlib import Path

import pytest

from agentgw.agent.package import load_package
from agentgw.channels.discord import _visible_text, handle_discord_message
from agentgw.channels.http import create_app
from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.channels.telegram import handle_telegram_message
from agentgw.harness.run import Harness
from tests.conftest import DEMO_AGENT
from tests.fakes import ScriptedLLM


@pytest.fixture
def demo_harness():
    pkg = load_package(DEMO_AGENT, workspace_override=Path.cwd())
    return Harness(pkg, ScriptedLLM(["ok", "again"]))


@pytest.mark.asyncio
async def test_handle_inbound_reuses_session(demo_harness):
    sessions = SessionMap()
    reply1, s1 = await handle_inbound(demo_harness, sessions, "chat:1", "hi")
    reply2, s2 = await handle_inbound(demo_harness, sessions, "chat:1", "again")
    assert reply1 == "ok"
    assert reply2 == "again"
    assert s1.id == s2.id
    assert len(s1.messages) >= 4


def test_strip_discord_mention():
    assert _visible_text("<@123> hello") == "hello"
    assert _visible_text("<@!99>  hi there") == "hi there"


@pytest.mark.asyncio
async def test_discord_and_telegram_handlers(demo_harness):
    sessions = SessionMap()
    d = await handle_discord_message(demo_harness, sessions, "c1", "<@1> hello")
    assert d == "ok"
    t = await handle_telegram_message(demo_harness, sessions, "42", "ping")
    assert t == "again"
    assert "discord:c1" in sessions._sessions
    assert "telegram:42" in sessions._sessions


@pytest.mark.asyncio
async def test_rest_chat_and_lists(demo_harness):
    import httpx

    app = create_app(demo_harness)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        assert health.json()["agent"] == "demo"
        skills = (await client.get("/v1/skills")).json()
        assert any(s["name"] == "greet" for s in skills)
        tools = (await client.get("/v1/tools")).json()
        assert "read" in tools

        first = (await client.post("/v1/chat", json={"message": "hello"})).json()
        assert first["response"] == "ok"
        sid = first["session_id"]
        second = (
            await client.post("/v1/chat", json={"message": "more", "session_id": sid})
        ).json()
        assert second["session_id"] == sid
        assert second["response"] == "again"
