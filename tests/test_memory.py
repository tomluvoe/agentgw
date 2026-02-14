"""Tests for memory store."""

import pytest

from agentgw.llm.types import Message, ToolCall
from agentgw.memory.store import MemoryStore


class TestMemoryStore:
    @pytest.mark.asyncio
    async def test_create_session(self, memory_store):
        session_id = await memory_store.create_session("test_skill")
        assert session_id is not None
        assert len(session_id) > 0

    @pytest.mark.asyncio
    async def test_save_and_get_messages(self, memory_store):
        session_id = await memory_store.create_session("test_skill")

        # Save user message
        user_msg = Message(role="user", content="Hello")
        await memory_store.save_message(session_id, user_msg, "test_skill")

        # Save assistant message
        asst_msg = Message(role="assistant", content="Hi there!")
        await memory_store.save_message(session_id, asst_msg, "test_skill")

        # Retrieve history
        history = await memory_store.get_history(session_id)
        assert len(history) == 2
        assert history[0].role == "user"
        assert history[0].content == "Hello"
        assert history[1].role == "assistant"
        assert history[1].content == "Hi there!"

    @pytest.mark.asyncio
    async def test_save_message_with_tool_calls(self, memory_store):
        session_id = await memory_store.create_session()

        msg = Message(
            role="assistant",
            content=None,
            tool_calls=[
                ToolCall(id="call_1", name="read_file", arguments='{"path": "/tmp/test.txt"}')
            ],
        )
        await memory_store.save_message(session_id, msg)

        history = await memory_store.get_history(session_id)
        assert len(history) == 1
        assert history[0].tool_calls is not None
        assert len(history[0].tool_calls) == 1
        assert history[0].tool_calls[0].name == "read_file"

    @pytest.mark.asyncio
    async def test_save_feedback(self, memory_store):
        session_id = await memory_store.create_session()
        msg = Message(role="assistant", content="Some response")
        msg_id = await memory_store.save_message(session_id, msg)

        # Should not raise
        await memory_store.save_feedback(session_id, msg_id, rating=1, comment="Great!")

    @pytest.mark.asyncio
    async def test_get_sessions(self, memory_store):
        await memory_store.create_session("skill_a")
        await memory_store.create_session("skill_b")
        await memory_store.create_session("skill_a")

        all_sessions = await memory_store.get_sessions()
        assert len(all_sessions) == 3

        skill_a_sessions = await memory_store.get_sessions(skill_name="skill_a")
        assert len(skill_a_sessions) == 2
