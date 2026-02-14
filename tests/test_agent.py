"""Tests for the agent loop."""

import json

import pytest

from agentgw.core.agent import AgentLoop
from agentgw.core.session import Session
from agentgw.llm.types import LLMResponse, ToolCall

from tests.conftest import MockLLMProvider


class TestAgentLoop:
    @pytest.mark.asyncio
    async def test_simple_response(self, sample_skill, memory_store, tool_registry):
        mock_llm = MockLLMProvider([
            LLMResponse(content="Hello! How can I help?", finish_reason="stop")
        ])
        session = Session.create(skill_name="test_skill")

        agent = AgentLoop(
            skill=sample_skill,
            llm=mock_llm,
            tool_registry=tool_registry,
            memory=memory_store,
            session=session,
        )

        result = await agent.run_to_completion("Hi there")
        assert "Hello! How can I help?" in result
        assert len(mock_llm.calls) == 1

    @pytest.mark.asyncio
    async def test_tool_call_then_response(self, sample_skill, memory_store, tool_registry, tmp_dir):
        # Create a test file for the tool to read
        test_file = tmp_dir / "test.txt"
        test_file.write_text("file content here")

        mock_llm = MockLLMProvider([
            # First call: LLM requests a tool call
            LLMResponse(
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="read_file",
                        arguments=json.dumps({"path": str(test_file)}),
                    )
                ],
                finish_reason="tool_calls",
            ),
            # Second call: LLM responds with text after seeing tool result
            LLMResponse(content="The file contains: file content here", finish_reason="stop"),
        ])
        session = Session.create(skill_name="test_skill")

        agent = AgentLoop(
            skill=sample_skill,
            llm=mock_llm,
            tool_registry=tool_registry,
            memory=memory_store,
            session=session,
        )

        result = await agent.run_to_completion("Read the test file")
        assert "file content here" in result
        assert len(mock_llm.calls) == 2

    @pytest.mark.asyncio
    async def test_max_iterations_guard(self, sample_skill, memory_store, tool_registry):
        # LLM always requests tool calls, never gives text
        mock_llm = MockLLMProvider([
            LLMResponse(
                tool_calls=[
                    ToolCall(id="call_1", name="read_file", arguments='{"path": "/dev/null"}')
                ],
                finish_reason="tool_calls",
            )
        ])
        sample_skill.max_iterations = 3
        session = Session.create(skill_name="test_skill")

        agent = AgentLoop(
            skill=sample_skill,
            llm=mock_llm,
            tool_registry=tool_registry,
            memory=memory_store,
            session=session,
        )

        result = await agent.run_to_completion("Do something forever")
        assert "maximum iterations" in result.lower()
        assert len(mock_llm.calls) == 3

    @pytest.mark.asyncio
    async def test_streaming_output(self, sample_skill, memory_store, tool_registry):
        mock_llm = MockLLMProvider([
            LLMResponse(content="chunk1chunk2chunk3", finish_reason="stop")
        ])
        session = Session.create(skill_name="test_skill")

        agent = AgentLoop(
            skill=sample_skill,
            llm=mock_llm,
            tool_registry=tool_registry,
            memory=memory_store,
            session=session,
        )

        chunks = []
        async for chunk in agent.run("Test streaming"):
            chunks.append(chunk)

        assert len(chunks) >= 1
        assert "".join(chunks) == "chunk1chunk2chunk3"

    @pytest.mark.asyncio
    async def test_conversation_history_persisted(self, sample_skill, memory_store, tool_registry):
        mock_llm = MockLLMProvider([
            LLMResponse(content="Response 1", finish_reason="stop")
        ])
        session = Session.create(skill_name="test_skill")
        session_id = await memory_store.create_session("test_skill")
        session.id = session_id

        agent = AgentLoop(
            skill=sample_skill,
            llm=mock_llm,
            tool_registry=tool_registry,
            memory=memory_store,
            session=session,
        )

        await agent.run_to_completion("Hello")

        history = await memory_store.get_history(session_id)
        assert len(history) == 2  # user + assistant
        assert history[0].role == "user"
        assert history[1].role == "assistant"
