"""Test fixtures for agentgw."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import AsyncIterator

import pytest

from agentgw.core.skill_loader import Skill
from agentgw.core.tool_registry import ToolRegistry
from agentgw.llm.types import LLMResponse, Message, StreamChunk, ToolCall
from agentgw.memory.store import MemoryStore


class MockLLMProvider:
    """Mock LLM provider for testing."""

    def __init__(self, responses: list[LLMResponse] | None = None):
        self._responses = responses or [
            LLMResponse(content="Mock response", finish_reason="stop")
        ]
        self._call_index = 0
        self.calls: list[dict] = []

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> LLMResponse:
        self.calls.append({
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "model": model,
        })
        resp = self._responses[min(self._call_index, len(self._responses) - 1)]
        self._call_index += 1
        return resp

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        self.calls.append({
            "messages": messages,
            "tools": tools,
            "temperature": temperature,
            "model": model,
        })
        resp = self._responses[min(self._call_index, len(self._responses) - 1)]
        self._call_index += 1

        # Simulate streaming: yield tool_calls first if present, then content
        if resp.tool_calls:
            for tc in resp.tool_calls:
                from agentgw.llm.types import ToolCallDelta
                yield StreamChunk(
                    delta_tool_calls=[
                        ToolCallDelta(index=0, id=tc.id, name=tc.name, arguments=tc.arguments)
                    ]
                )
            yield StreamChunk(finish_reason="tool_calls")
        elif resp.content:
            # Yield content in small chunks
            for i in range(0, len(resp.content), 10):
                yield StreamChunk(delta_content=resp.content[i:i+10])
            yield StreamChunk(finish_reason="stop")


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def sample_skill():
    return Skill(
        name="test_skill",
        description="A test skill",
        system_prompt="You are a test assistant.",
        tools=["read_file"],
        temperature=0.5,
        tags=["test"],
    )


@pytest.fixture
def mock_llm():
    return MockLLMProvider()


@pytest.fixture
async def memory_store(tmp_dir):
    store = MemoryStore(tmp_dir / "test.db")
    await store.initialize()
    return store


@pytest.fixture
def tool_registry():
    registry = ToolRegistry()
    registry.discover(["agentgw.tools"])
    return registry
