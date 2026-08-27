from __future__ import annotations

from typing import AsyncIterator

from agentgw.llm.types import StreamChunk, ToolCallDelta


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
