from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from agentgw.agent.package import load_package
from agentgw.channels.bots import ChannelBots
from agentgw.channels.client import AgentClient
from agentgw.channels.discord import (
    _visible_text,
    handle_discord_content,
    handle_discord_message,
    handle_discord_remote,
    session_key as discord_session_key,
)
from agentgw.channels.http import create_app
from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.channels.store import SessionStore
from agentgw.channels.telegram import (
    handle_telegram_content,
    handle_telegram_message,
    handle_telegram_remote,
    session_key as telegram_session_key,
)
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


def test_channel_session_keys():
    assert discord_session_key("c1") == "discord-c1"
    assert telegram_session_key("42") == "telegram-42"
    assert telegram_session_key("-100123") == "telegram--100123"


def test_session_store_accepts_channel_ids(tmp_path: Path):
    store = SessionStore(tmp_path)
    assert store.path_for("discord-99").name == "discord-99.json"
    assert store.path_for("telegram--100").name == "telegram--100.json"


@pytest.mark.asyncio
async def test_discord_and_telegram_handlers(demo_harness):
    sessions = SessionMap()
    d = await handle_discord_message(demo_harness, sessions, "c1", "<@1> hello")
    assert d == "ok"
    t = await handle_telegram_message(demo_harness, sessions, "42", "ping")
    assert t == "again"
    assert "discord-c1" in sessions._sessions
    assert "telegram-42" in sessions._sessions


@pytest.mark.asyncio
async def test_discord_content_maps_to_session():
    seen: list[tuple[str, str]] = []

    async def send(key: str, text: str) -> str:
        seen.append((key, text))
        return "ack"

    reply = await handle_discord_content("c1", "<@1> hello", send)
    assert reply == "ack"
    assert seen == [("discord-c1", "hello")]
    empty = await handle_discord_content("c1", "<@1>  ", send)
    assert empty == ""


@pytest.mark.asyncio
async def test_telegram_content_maps_to_session():
    seen: list[tuple[str, str]] = []

    async def send(key: str, text: str) -> str:
        seen.append((key, text))
        return "ack"

    reply = await handle_telegram_content("-1001", "ping", send)
    assert reply == "ack"
    assert seen == [("telegram--1001", "ping")]


@pytest.mark.asyncio
async def test_discord_session_shared_with_rest_and_survives_restart(tmp_path: Path):
    import httpx

    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    harness = Harness(pkg, ScriptedLLM(["from-discord", "from-cli"]))
    app = create_app(harness)
    reply = await handle_discord_message(
        harness, app.state.sessions, "99", "<@1> hello from discord"
    )
    assert reply == "from-discord"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listed = (await client.get("/v1/sessions")).json()["sessions"]
        assert "discord-99" in listed
        cont = (
            await client.post(
                "/v1/chat",
                json={"message": "and from cli", "session_id": "discord-99"},
            )
        ).json()
        assert cont["session_id"] == "discord-99"
        assert cont["response"] == "from-cli"

    pkg2 = load_package(DEMO_AGENT, workspace_override=tmp_path)
    app2 = create_app(Harness(pkg2, ScriptedLLM(["after-restart"])))
    transport2 = httpx.ASGITransport(app=app2)
    async with httpx.AsyncClient(transport=transport2, base_url="http://test") as client:
        listed = (await client.get("/v1/sessions")).json()["sessions"]
        assert "discord-99" in listed
        third = (
            await client.post(
                "/v1/chat",
                json={"message": "still there?", "session_id": "discord-99"},
            )
        ).json()
        assert third["session_id"] == "discord-99"
        assert third["response"] == "after-restart"


@pytest.mark.asyncio
async def test_telegram_session_shared_with_rest(tmp_path: Path):
    import httpx

    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    harness = Harness(pkg, ScriptedLLM(["from-tg", "from-cli"]))
    app = create_app(harness)
    reply = await handle_telegram_message(
        harness, app.state.sessions, "42", "hello from telegram"
    )
    assert reply == "from-tg"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listed = (await client.get("/v1/sessions")).json()["sessions"]
        assert "telegram-42" in listed
        cont = (
            await client.post(
                "/v1/chat",
                json={"message": "and from cli", "session_id": "telegram-42"},
            )
        ).json()
        assert cont["session_id"] == "telegram-42"
        assert cont["response"] == "from-cli"


@pytest.mark.asyncio
async def test_discord_and_telegram_http_client(monkeypatch):
    import httpx

    posted: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat":
            body = json.loads(request.content)
            posted.append(body)
            return httpx.Response(
                200,
                json={"session_id": body["session_id"], "response": "ack"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("agentgw.channels.client.httpx.AsyncClient", _Client)
    client = AgentClient("http://127.0.0.1:8080")
    d = await handle_discord_remote(client, "c1", "<@1> hi")
    t = await handle_telegram_remote(client, "42", "ping")
    assert d == "ack"
    assert t == "ack"
    assert posted[0]["session_id"] == "discord-c1"
    assert posted[0]["message"] == "hi"
    assert posted[1]["session_id"] == "telegram-42"
    assert posted[1]["message"] == "ping"


def test_cli_discord_needs_agent_or_url():
    from agentgw.channels.cli import cli

    result = CliRunner().invoke(cli, ["discord"])
    assert result.exit_code == 1
    assert "--agent is required" in result.output


@pytest.mark.asyncio
async def test_channel_bots_noop_without_tokens(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    bots = ChannelBots(Harness(pkg, ScriptedLLM(["x"])), SessionMap())
    started = await bots.start()
    assert started == []
    await bots.stop()


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
