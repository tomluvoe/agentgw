from __future__ import annotations

from pathlib import Path

import pytest

from agentgw.agent.package import load_package
from agentgw.channels.hooks import load_hooks
from agentgw.channels.http import create_app
from agentgw.harness.run import Harness
from tests.conftest import DEMO_AGENT, ROOT
from tests.fakes import ScriptedLLM


def test_load_demo_hooks():
    hooks = load_hooks(ROOT / "agents" / "demo" / "hooks.yaml")
    assert [h.name for h in hooks] == ["github"]
    assert hooks[0].session == "hook-github"


@pytest.mark.asyncio
async def test_fire_hook_runs_harness(tmp_path: Path):
    import httpx

    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    app = create_app(Harness(pkg, ScriptedLLM(["ack"])))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listed = (await client.get("/v1/hooks")).json()["hooks"]
        assert listed[0]["name"] == "github"
        missing = await client.post("/v1/hooks/nope", json={"x": 1})
        assert missing.status_code == 404
        fired = await client.post(
            "/v1/hooks/github", json={"action": "opened", "number": 3}
        )
        assert fired.status_code == 200
        body = fired.json()
        assert body["response"] == "ack"
        assert body["session_id"] == "hook-github"
        assert body["hook"] == "github"


@pytest.mark.asyncio
async def test_hook_requires_auth(tmp_path: Path):
    import httpx

    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    app = create_app(Harness(pkg, ScriptedLLM(["ack"])), api_key="secret")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/v1/hooks/github", json={})
        assert denied.status_code == 401
        ok = await client.post(
            "/v1/hooks/github",
            json={"ok": True},
            headers={"Authorization": "Bearer secret"},
        )
        assert ok.status_code == 200


@pytest.mark.asyncio
async def test_disabled_hook_forbidden(tmp_path: Path):
    import httpx

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "AGENT.md").write_text(
        "---\nname: h\ndescription: Hook fixture.\n---\nYou test hooks.\n",
        encoding="utf-8",
    )
    (agent_dir / "hooks.yaml").write_text(
        'hooks:\n  - name: "paused"\n    enabled: false\n    session: s\n',
        encoding="utf-8",
    )
    pkg = load_package(agent_dir / "AGENT.md", workspace_override=tmp_path)
    app = create_app(Harness(pkg, ScriptedLLM(["no"])))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post("/v1/hooks/paused", json={})
        assert res.status_code == 403
