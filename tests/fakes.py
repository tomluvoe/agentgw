from __future__ import annotations

from typing import AsyncIterator

from agentgw.llm.types import StreamChunk, ToolCallDelta


class ScriptedLLM:
    """Deterministic LLM for harness tests. Records every chat_stream call."""

    def __init__(self, turns: list):
        self.turns = turns
        self.index = 0
        self.calls: list[dict] = []

    async def chat_stream(self, **kwargs) -> AsyncIterator[StreamChunk]:
        self.calls.append(
            {
                "messages": kwargs.get("messages"),
                "tools": kwargs.get("tools"),
                "temperature": kwargs.get("temperature"),
                "model": kwargs.get("model"),
            }
        )
        if not self.turns:
            yield StreamChunk(delta_content="", finish_reason="stop")
            return
        if self.index < len(self.turns):
            turn = self.turns[self.index]
            self.index += 1
        else:
            turn = self.turns[-1]
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
