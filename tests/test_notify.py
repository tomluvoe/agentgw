from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from agentgw.agent.package import load_package
from agentgw.harness.run import Harness
from agentgw.harness.spec import RunContext, ToolPolicy
from agentgw.tools.registry import ToolRegistry, reset_builtin_tools
from tests.conftest import DEMO_AGENT
from tests.fakes import ScriptedLLM

_SINK_ENV = (
    "NOTIFY_WEBHOOK_URL",
    "DISCORD_WEBHOOK_URL",
    "TELEGRAM_BOT_TOKEN",
    "NOTIFY_CHAT_ID",
)


def _clear_sinks(monkeypatch) -> None:
    for key in _SINK_ENV:
        monkeypatch.delenv(key, raising=False)


def _stub_posts(monkeypatch, *, status: int = 200) -> list[tuple[str, dict]]:
    posted: list[tuple[str, dict]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        posted.append((str(request.url), body))
        if status >= 400:
            return httpx.Response(status, json={"ok": False})
        return httpx.Response(status, json={"ok": True})

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    # Patch the shared httpx module so reloads of notify.py keep the stub.
    monkeypatch.setattr(httpx, "AsyncClient", _Client)
    return posted


async def _run_notify(text: str) -> str:
    reset_builtin_tools()
    registry = ToolRegistry()
    registry.collect_registered()
    return await registry.execute(
        "notify",
        {"text": text},
        ToolPolicy(allow=("notify",)),
        ctx=RunContext(workspace=Path(".")),
    )


@pytest.mark.asyncio
async def test_notify_without_sink(monkeypatch):
    _clear_sinks(monkeypatch)
    result = await _run_notify("hi")
    assert "no notify sink" in result


@pytest.mark.asyncio
async def test_notify_webhook(monkeypatch):
    _clear_sinks(monkeypatch)
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://example.test/hook")
    posted = _stub_posts(monkeypatch)
    result = await _run_notify("watch fired")
    assert result == "sent via webhook"
    assert posted[0][0] == "https://example.test/hook"
    assert posted[0][1]["text"] == "watch fired"
    assert posted[0][1]["content"] == "watch fired"


@pytest.mark.asyncio
async def test_notify_discord_and_telegram(monkeypatch):
    _clear_sinks(monkeypatch)
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", "https://discord.test/api/webhooks/1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("NOTIFY_CHAT_ID", "42")
    posted = _stub_posts(monkeypatch)
    result = await _run_notify("ping")
    assert result == "sent via discord, telegram"
    urls = [u for u, _ in posted]
    assert urls[0] == "https://discord.test/api/webhooks/1"
    assert posted[0][1] == {"content": "ping"}
    assert urls[1] == "https://api.telegram.org/bottok/sendMessage"
    assert posted[1][1] == {"chat_id": "42", "text": "ping"}


@pytest.mark.asyncio
async def test_notify_http_error(monkeypatch):
    _clear_sinks(monkeypatch)
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://example.test/hook")
    _stub_posts(monkeypatch, status=500)
    result = await _run_notify("oops")
    assert result.startswith("error: webhook:")


@pytest.mark.asyncio
async def test_harness_can_call_notify(tmp_path: Path, monkeypatch):
    _clear_sinks(monkeypatch)
    monkeypatch.setenv("NOTIFY_WEBHOOK_URL", "https://example.test/hook")
    posted = _stub_posts(monkeypatch)
    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    assert pkg.tool_policy.permits("notify")
    llm = ScriptedLLM(
        [
            ("notify", '{"text": "coffee is oat"}'),
            "notified",
        ]
    )
    harness = Harness(pkg, llm)
    result = await harness.run_to_completion("if anything happens, notify me")
    assert result == "notified"
    assert posted[0][1]["text"] == "coffee is oat"
