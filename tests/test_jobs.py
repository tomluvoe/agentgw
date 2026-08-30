from __future__ import annotations

from pathlib import Path

import pytest

from agentgw.agent.package import load_package
from agentgw.channels.http import create_app
from agentgw.channels.jobs import load_jobs
from agentgw.harness.run import Harness
from tests.conftest import DEMO_AGENT, ROOT
from tests.fakes import ScriptedLLM


def test_load_demo_jobs_disabled():
    jobs = load_jobs(ROOT / "agents" / "demo" / "jobs.yaml")
    assert len(jobs) == 1
    assert jobs[0].name == "watch-heartbeat"
    assert jobs[0].enabled is False
    assert jobs[0].session == "heartbeat"


def test_load_jobs_missing(tmp_path: Path):
    assert load_jobs(tmp_path / "nope.yaml") == []


@pytest.mark.asyncio
async def test_run_job_injects_message(tmp_path: Path):
    import httpx

    jobs_path = tmp_path / "jobs.yaml"
    jobs_path.write_text(
        "jobs:\n"
        "  - name: ping\n"
        "    session: heartbeat\n"
        "    message: heartbeat check\n"
        "    enabled: true\n"
        "    every_seconds: 3600\n",
        encoding="utf-8",
    )
    # AGENT.md lives in demo; copy jobs next to a temp agent
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    (agent_dir / "AGENT.md").write_text(
        "---\nname: job-test\ndescription: Job fixture.\n---\nYou test jobs.\n",
        encoding="utf-8",
    )
    (agent_dir / "jobs.yaml").write_text(jobs_path.read_text(encoding="utf-8"), encoding="utf-8")

    pkg = load_package(agent_dir / "AGENT.md", workspace_override=tmp_path)
    harness = Harness(pkg, ScriptedLLM(["HEARTBEAT_OK"]))
    app = create_app(harness)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        listed = (await client.get("/v1/jobs")).json()["jobs"]
        assert listed[0]["name"] == "ping"
        missing = await client.post("/v1/jobs/nope/run")
        assert missing.status_code == 404
        fired = await client.post("/v1/jobs/ping/run")
        assert fired.status_code == 200
        body = fired.json()
        assert body["response"] == "HEARTBEAT_OK"
        assert body["session_id"] == "heartbeat"


@pytest.mark.asyncio
async def test_demo_job_run_endpoint(tmp_path: Path):
    import httpx

    pkg = load_package(DEMO_AGENT, workspace_override=tmp_path)
    harness = Harness(pkg, ScriptedLLM(["HEARTBEAT_OK"]))
    app = create_app(harness)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        names = [j["name"] for j in (await client.get("/v1/jobs")).json()["jobs"]]
        assert "watch-heartbeat" in names
        fired = await client.post("/v1/jobs/watch-heartbeat/run")
        assert fired.status_code == 200
        assert fired.json()["response"] == "HEARTBEAT_OK"
