from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

from agentgw.harness.loop import AgentLoop
from agentgw.harness.session import Session
from agentgw.harness.spec import AgentSpec, RunContext, ToolPolicy
from agentgw.llm.types import StreamChunk, ToolCallDelta
from agentgw.tools.registry import ToolRegistry, reset_builtin_tools


class ScriptedLLM:
    def __init__(self, turns: list):
        self.turns = turns
        self.index = 0

    async def chat_stream(self, **kwargs) -> AsyncIterator[StreamChunk]:
        turn = self.turns[self.index]
        self.index += 1
        if isinstance(turn, str):
            yield StreamChunk(delta_content=turn, finish_reason="stop")
            return
        name, arguments = turn
        yield StreamChunk(
            delta_tool_calls=[
                ToolCallDelta(index=0, id="call_1", name=name, arguments=arguments)
            ]
        )
        yield StreamChunk(finish_reason="tool_calls")


async def test_loop_tool_then_text(tmp_path: Path):
    (tmp_path / "note.txt").write_text("secret-note", encoding="utf-8")
    reset_builtin_tools()
    registry = ToolRegistry()
    registry.collect_registered()
    spec = AgentSpec(
        name="t",
        description="t",
        system_prompt="You are a test agent.",
        model=None,
        provider=None,
        temperature=0,
        max_iterations=5,
        tool_policy=ToolPolicy(allow=("read", "write", "list_dir")),
        activated_skills=(),
        catalog_skills=(),
        workspace=tmp_path,
        context=RunContext(workspace=tmp_path),
    )
    llm = ScriptedLLM(
        [
            ("read", '{"path": "note.txt"}'),
            "The note says secret-note.",
        ]
    )
    loop = AgentLoop(spec, llm, registry, Session.create("t"))
    result = await loop.run_to_completion("read the note")
    assert "secret-note" in result
    tool_msgs = [m for m in loop._session.messages if m.role == "tool"]
    assert tool_msgs and "secret-note" in (tool_msgs[0].content or "")
