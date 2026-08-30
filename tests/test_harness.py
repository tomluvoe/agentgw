"""End-to-end harness: AGENT.md → skills → tools → loop → reply."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from agentgw.channels.cli import cli
from agentgw.harness.run import Harness
from agentgw.harness.session import Session
from tests.conftest import DEMO_AGENT
from tests.fakes import ScriptedLLM

pytestmark = pytest.mark.harness


def _tool_names(call: dict) -> list[str]:
    tools = call.get("tools") or []
    return [t["function"]["name"] for t in tools]


def _system(call: dict) -> str:
    messages = call["messages"] or []
    assert messages and messages[0].role == "system"
    return messages[0].content or ""


def _write_agent(
    root: Path,
    *,
    allow: list[str] | None = None,
    deny: list[str] | None = None,
    modules: list[str] | None = None,
    skill_roots: list[str] | None = None,
    extra_frontmatter: str = "",
    body: str = "You are a test agent. Use tools when needed.",
) -> Path:
    skills_dir = root / "skills" / "note-taker"
    skills_dir.mkdir(parents=True)
    (skills_dir / "SKILL.md").write_text(
        "---\n"
        "name: note-taker\n"
        "description: Take notes in the workspace. Use when saving or writing notes.\n"
        "---\n\n"
        "Write notes under notes/ using the write tool. base={baseDir}\n",
        encoding="utf-8",
    )
    agent = root / "AGENT.md"
    allow = allow or ["read", "write", "list_dir", "exec"]
    deny = deny or []
    skill_roots = skill_roots if skill_roots is not None else ["skills"]
    allow_yaml = "\n".join(f"    - {n}" for n in allow)
    deny_yaml = "\n".join(f"    - {n}" for n in deny)
    roots_yaml = "\n".join(f"    - {r}" for r in skill_roots)
    modules_yaml = "\n".join(f"    - {m}" for m in (modules or []))
    agent.write_text(
        "---\n"
        "name: harness-test\n"
        "description: Isolated harness fixture.\n"
        f"{extra_frontmatter}"
        "skills:\n"
        "  roots:\n"
        f"{roots_yaml}\n"
        "tools:\n"
        "  allow:\n"
        f"{allow_yaml}\n"
        + ("  deny:\n" + deny_yaml + "\n" if deny else "")
        + ("  modules:\n" + modules_yaml + "\n" if modules else "")
        + "---\n\n"
        + body
        + "\n",
        encoding="utf-8",
    )
    return agent


def test_from_path_loads_demo(tmp_path: Path):
    harness = Harness.from_path(DEMO_AGENT, ScriptedLLM(["x"]), workspace=tmp_path)
    names = {s.name for s in harness.package.skills}
    assert {"greet", "workspace-notes", "echo-helper", "memory"} <= names
    assert harness.package.workspace == tmp_path.resolve()


@pytest.mark.asyncio
async def test_text_reply_sends_catalog_and_tools(tmp_path: Path):
    llm = ScriptedLLM(["hello from harness"])
    harness = Harness.from_path(DEMO_AGENT, llm, workspace=tmp_path)
    result = await harness.run_to_completion("what is 2+2?")
    assert result == "hello from harness"
    assert llm.calls
    names = _tool_names(llm.calls[0])
    for expected in ("read", "write", "list_dir", "exec", "echo"):
        assert expected in names
    system = _system(llm.calls[0])
    assert "You are a local demo assistant" in system
    assert "<available_skills>" in system
    assert "<name>greet</name>" in system
    assert "<name>workspace-notes</name>" in system
    assert "<name>memory</name>" in system
    assert "### greet" not in system


@pytest.mark.asyncio
async def test_remember_injects_memory_skill_and_writes(tmp_path: Path):
    llm = ScriptedLLM(
        [
            (
                "write",
                '{"path": "memory/MEMORY.md", "content": "- coffee: oat milk\\n"}',
            ),
            "Noted: oat milk.",
        ]
    )
    harness = Harness.from_path(DEMO_AGENT, llm, workspace=tmp_path)
    result = await harness.run_to_completion(
        "please remember that my coffee is oat milk"
    )
    assert "oat milk" in result.lower() or "Noted" in result
    system = _system(llm.calls[0])
    assert "### memory" in system
    assert (tmp_path / "memory" / "MEMORY.md").read_text(encoding="utf-8").find(
        "oat milk"
    ) != -1


@pytest.mark.asyncio
async def test_greeting_injects_skill_body(tmp_path: Path):
    llm = ScriptedLLM(["Hi!"])
    harness = Harness.from_path(DEMO_AGENT, llm, workspace=tmp_path)
    await harness.run_to_completion("hello there, please greet me")
    system = _system(llm.calls[0])
    assert "### greet" in system
    assert "Do not call tools for a simple hello" in system
    assert "### workspace-notes" not in system


@pytest.mark.asyncio
async def test_basedir_expanded_when_notes_skill_activates(tmp_path: Path):
    llm = ScriptedLLM(["noted"])
    agent = _write_agent(tmp_path)
    harness = Harness.from_path(agent, llm, workspace=tmp_path)
    await harness.run_to_completion("please take notes about the meeting")
    system = _system(llm.calls[0])
    assert "### note-taker" in system
    skill_dir = (tmp_path / "skills" / "note-taker").resolve()
    assert f"base={skill_dir}" in system
    assert "{baseDir}" not in system


@pytest.mark.asyncio
async def test_read_write_roundtrip_through_harness(tmp_path: Path):
    (tmp_path / "memo.txt").write_text("alpha", encoding="utf-8")
    llm = ScriptedLLM(
        [
            ("read", '{"path": "memo.txt"}'),
            ("write", '{"path": "out.txt", "content": "alpha-copy"}'),
            "wrote a copy",
        ]
    )
    harness = Harness.from_path(DEMO_AGENT, llm, workspace=tmp_path)
    result = await harness.run_to_completion("copy the memo")
    assert result == "wrote a copy"
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "alpha-copy"
    tool_msgs = [m for m in llm.calls[1]["messages"] if m.role == "tool"]
    assert any(m.content and "alpha" in m.content for m in tool_msgs)


@pytest.mark.asyncio
async def test_shared_echo_tool(tmp_path: Path):
    llm = ScriptedLLM(
        [
            ("echo", '{"text": "pong"}'),
            "got pong",
        ]
    )
    harness = Harness.from_path(DEMO_AGENT, llm, workspace=tmp_path)
    result = await harness.run_to_completion("use echo-helper to echo pong")
    assert result == "got pong"
    assert "echo" in _tool_names(llm.calls[0])
    tool_msgs = [m for m in llm.calls[1]["messages"] if m.role == "tool"]
    assert tool_msgs and tool_msgs[0].content == "pong"


@pytest.mark.asyncio
async def test_exec_runs_in_workspace(tmp_path: Path):
    llm = ScriptedLLM(
        [
            ("exec", '{"command": "pwd && echo harness-exec"}'),
            "ran",
        ]
    )
    agent = _write_agent(tmp_path, allow=["exec", "read"])
    harness = Harness.from_path(agent, llm, workspace=tmp_path)
    await harness.run_to_completion("run a command")
    tool_msgs = [m for m in llm.calls[1]["messages"] if m.role == "tool"]
    assert tool_msgs
    out = tool_msgs[0].content or ""
    assert "harness-exec" in out
    assert str(tmp_path.resolve()) in out


@pytest.mark.asyncio
async def test_denied_tool_not_offered_and_not_executed(tmp_path: Path):
    llm = ScriptedLLM(
        [
            ("exec", '{"command": "echo pwned"}'),
            "done",
        ]
    )
    agent = _write_agent(
        tmp_path,
        allow=["read", "write"],
        deny=["exec"],
    )
    harness = Harness.from_path(agent, llm, workspace=tmp_path)
    await harness.run_to_completion("run a command")
    assert "exec" not in _tool_names(llm.calls[0])
    tool_msgs = [m for m in llm.calls[1]["messages"] if m.role == "tool"]
    assert tool_msgs and "not allowed" in (tool_msgs[0].content or "")
    # nothing executed in the workspace
    assert not list(tmp_path.glob("pwned*"))


@pytest.mark.asyncio
async def test_path_escape_blocked_via_harness(tmp_path: Path):
    llm = ScriptedLLM(
        [
            ("read", '{"path": "/etc/passwd"}'),
            "blocked",
        ]
    )
    harness = Harness.from_path(DEMO_AGENT, llm, workspace=tmp_path)
    await harness.run_to_completion("read secrets")
    tool_msgs = [m for m in llm.calls[1]["messages"] if m.role == "tool"]
    assert tool_msgs and "escapes workspace" in (tool_msgs[0].content or "")


@pytest.mark.asyncio
async def test_unknown_and_bad_json_tool_args(tmp_path: Path):
    llm = ScriptedLLM(
        [
            ("not_a_tool", '{"x": 1}'),
            ("read", "not-json"),
            "recovered",
        ]
    )
    harness = Harness.from_path(DEMO_AGENT, llm, workspace=tmp_path)
    result = await harness.run_to_completion("break tools")
    assert result == "recovered"
    first = [m for m in llm.calls[1]["messages"] if m.role == "tool"][0]
    second = [m for m in llm.calls[2]["messages"] if m.role == "tool"][-1]
    assert "not allowed" in (first.content or "") or "Unknown tool" in (first.content or "")
    assert "error" in (second.content or "").lower()


@pytest.mark.asyncio
async def test_max_iterations_stops_the_loop(tmp_path: Path):
    llm = ScriptedLLM([("list_dir", '{"directory": "."}')])
    agent = _write_agent(tmp_path, extra_frontmatter="max_iterations: 2\n")
    harness = Harness.from_path(agent, llm, workspace=tmp_path)
    result = await harness.run_to_completion("loop forever")
    assert "maximum iterations" in result
    assert len(llm.calls) >= 2


@pytest.mark.asyncio
async def test_session_history_on_second_turn(tmp_path: Path):
    llm = ScriptedLLM(["first", "second"])
    harness = Harness.from_path(DEMO_AGENT, llm, workspace=tmp_path)
    session = Session.create("demo")
    await harness.run_to_completion("hi", session=session)
    await harness.run_to_completion("and then?", session=session)
    second_msgs = llm.calls[1]["messages"]
    users = [m.content for m in second_msgs if m.role == "user"]
    assert "hi" in users
    assert "and then?" in users
    assistants = [m.content for m in second_msgs if m.role == "assistant"]
    assert "first" in assistants


@pytest.mark.asyncio
async def test_gated_skill_not_in_catalog(tmp_path: Path):
    gated = tmp_path / "skills" / "needs-key"
    gated.mkdir(parents=True)
    (gated / "SKILL.md").write_text(
        "---\n"
        "name: needs-key\n"
        "description: Requires a missing env var. Use when unlocking secrets.\n"
        "metadata:\n"
        "  requires:\n"
        "    env: [AGENTGW_TEST_MISSING_KEY]\n"
        "---\n\n"
        "Should never load.\n",
        encoding="utf-8",
    )
    # also keep note-taker via helper
    agent = _write_agent(tmp_path)
    llm = ScriptedLLM(["ok"])
    harness = Harness.from_path(agent, llm, workspace=tmp_path)
    names = {s.name for s in harness.package.skills}
    assert "needs-key" not in names
    await harness.run_to_completion("unlock secrets")
    assert "needs-key" not in _system(llm.calls[0])


def test_cli_skills_and_tools():
    runner = CliRunner()
    skills = runner.invoke(cli, ["skills", "-a", str(DEMO_AGENT)])
    assert skills.exit_code == 0, skills.output
    assert "greet" in skills.output
    assert "workspace-notes" in skills.output
    assert "memory" in skills.output
    tools = runner.invoke(cli, ["tools", "-a", str(DEMO_AGENT)])
    assert tools.exit_code == 0, tools.output
    for name in ("read", "write", "list_dir", "exec", "echo"):
        assert name in tools.output


def test_cli_run_uses_harness(tmp_path: Path, monkeypatch):
    llm = ScriptedLLM(["cli-ok"])

    def fake_llm(**kwargs):
        return llm

    monkeypatch.setattr("agentgw.channels.cli.create_llm", fake_llm)
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["run", "-a", str(DEMO_AGENT), "-w", str(tmp_path), "hello"],
    )
    assert result.exit_code == 0, result.output
    assert "cli-ok" in result.output
    assert llm.calls
    assert "<available_skills>" in _system(llm.calls[0])
