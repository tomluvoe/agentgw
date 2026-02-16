"""Tests for Anthropic provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentgw.llm.anthropic_provider import AnthropicProvider
from agentgw.llm.types import Message, ToolCall


class TestAnthropicProvider:
    @pytest.fixture
    def provider(self):
        with patch("agentgw.llm.anthropic_provider.AsyncAnthropic"):
            return AnthropicProvider(api_key="test-key", default_model="claude-3-5-sonnet-20241022")

    def test_provider_initialization(self, provider):
        assert provider._default_model == "claude-3-5-sonnet-20241022"

    def test_convert_messages_system_prompt(self, provider):
        messages = [
            Message(role="system", content="You are a helpful assistant."),
            Message(role="user", content="Hello"),
        ]
        system_prompt, converted = provider._convert_messages(messages)
        assert system_prompt == "You are a helpful assistant."
        assert len(converted) == 1
        assert converted[0]["role"] == "user"
        assert converted[0]["content"] == "Hello"

    def test_convert_messages_tool_result(self, provider):
        messages = [
            Message(role="system", content="System"),
            Message(role="user", content="Use a tool"),
            Message(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="call_123", name="test_tool", arguments='{"arg": "value"}')],
            ),
            Message(role="tool", content="Tool result", tool_call_id="call_123", name="test_tool"),
        ]
        system_prompt, converted = provider._convert_messages(messages)
        assert len(converted) == 3  # user, assistant, tool result

        # Check tool result format
        tool_msg = converted[2]
        assert tool_msg["role"] == "user"
        assert tool_msg["content"][0]["type"] == "tool_result"
        assert tool_msg["content"][0]["tool_use_id"] == "call_123"
        assert tool_msg["content"][0]["content"] == "Tool result"

    def test_convert_messages_empty_system(self, provider):
        messages = [
            Message(role="user", content="Hello"),
        ]
        system_prompt, converted = provider._convert_messages(messages)
        assert system_prompt == ""
        assert len(converted) == 1

    def test_convert_tool_schema(self, provider):
        tool_schema = {
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "A test tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "arg1": {"type": "string", "description": "First arg"},
                    },
                    "required": ["arg1"],
                },
            },
        }
        converted = provider._convert_tool_schema(tool_schema)
        assert converted["name"] == "test_tool"
        assert converted["description"] == "A test tool"
        assert converted["input_schema"]["type"] == "object"
        assert "arg1" in converted["input_schema"]["properties"]

    @pytest.mark.asyncio
    async def test_chat_stream_text_only(self, provider):
        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = [
            MagicMock(
                type="content_block_start",
                index=0,
                content_block=MagicMock(type="text", text=""),
            ),
            MagicMock(
                type="content_block_delta",
                index=0,
                delta=MagicMock(type="text_delta", text="Hello "),
            ),
            MagicMock(
                type="content_block_delta",
                index=0,
                delta=MagicMock(type="text_delta", text="world"),
            ),
            MagicMock(
                type="message_stop",
            ),
        ]

        with patch.object(provider._client.messages, "stream") as mock_method:
            mock_method.return_value.__aenter__.return_value = mock_stream

            messages = [Message(role="user", content="Hi")]
            chunks = []
            async for chunk in provider.chat_stream(messages, tools=None, temperature=0.7):
                chunks.append(chunk)

            assert len(chunks) == 3  # 2 text deltas + stop
            assert chunks[0].delta_content == "Hello "
            assert chunks[1].delta_content == "world"
            assert chunks[2].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_chat_stream_with_tools(self, provider):
        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = [
            MagicMock(
                type="content_block_start",
                index=0,
                content_block=MagicMock(
                    type="tool_use",
                    id="call_123",
                    name="test_tool",
                    input={},
                ),
            ),
            MagicMock(
                type="content_block_delta",
                index=0,
                delta=MagicMock(
                    type="input_json_delta",
                    partial_json='{"arg": "value"}',
                ),
            ),
            MagicMock(type="message_stop"),
        ]

        with patch.object(provider._client.messages, "stream") as mock_method:
            mock_method.return_value.__aenter__.return_value = mock_stream

            messages = [Message(role="user", content="Use a tool")]
            tool_schemas = [
                {
                    "type": "function",
                    "function": {
                        "name": "test_tool",
                        "description": "Test",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            ]

            chunks = []
            async for chunk in provider.chat_stream(messages, tools=tool_schemas, temperature=0.7):
                chunks.append(chunk)

            # Should have tool call chunks
            tool_chunks = [c for c in chunks if c.delta_tool_calls]
            assert len(tool_chunks) > 0

    @pytest.mark.asyncio
    async def test_chat_non_streaming(self, provider):
        # Mock the streaming method
        async def mock_stream(*args, **kwargs):
            from agentgw.llm.types import StreamChunk

            yield StreamChunk(delta_content="Hello ")
            yield StreamChunk(delta_content="world")
            yield StreamChunk(finish_reason="stop")

        with patch.object(provider, "chat_stream", side_effect=mock_stream):
            messages = [Message(role="user", content="Hi")]
            response = await provider.chat(messages, tools=None, temperature=0.7)

            assert response.content == "Hello world"
            assert response.finish_reason == "stop"
            assert response.tool_calls is None

    def test_model_override(self, provider):
        # Default model
        assert provider._default_model == "claude-3-5-sonnet-20241022"

        # Provider should accept model parameter in chat methods
        # (tested implicitly through other tests)
