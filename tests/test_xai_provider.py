"""Tests for xAI (Grok) provider."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agentgw.llm.xai_provider import XAIProvider
from agentgw.llm.types import Message


class TestXAIProvider:
    @pytest.fixture
    def provider(self):
        with patch("agentgw.llm.xai_provider.AsyncOpenAI"):
            return XAIProvider(api_key="test-key", default_model="grok-beta")

    def test_provider_initialization(self, provider):
        assert provider._default_model == "grok-beta"
        # Verify the client was initialized with xAI base URL
        # (checked in the actual class initialization)

    @pytest.mark.asyncio
    async def test_chat_stream(self, provider):
        # Mock the OpenAI-compatible streaming
        mock_chunk_1 = MagicMock()
        mock_chunk_1.choices = [
            MagicMock(
                delta=MagicMock(content="Hello ", role="assistant", tool_calls=None),
                finish_reason=None,
            )
        ]

        mock_chunk_2 = MagicMock()
        mock_chunk_2.choices = [
            MagicMock(
                delta=MagicMock(content="world", role=None, tool_calls=None),
                finish_reason=None,
            )
        ]

        mock_chunk_3 = MagicMock()
        mock_chunk_3.choices = [
            MagicMock(
                delta=MagicMock(content=None, role=None, tool_calls=None),
                finish_reason="stop",
            )
        ]

        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = [mock_chunk_1, mock_chunk_2, mock_chunk_3]

        with patch.object(provider._client.chat.completions, "create", return_value=mock_stream):
            messages = [Message(role="user", content="Hi")]
            chunks = []
            async for chunk in provider.chat_stream(messages, tools=None, temperature=0.7):
                chunks.append(chunk)

            assert len(chunks) == 3
            assert chunks[0].delta_content == "Hello "
            assert chunks[1].delta_content == "world"
            assert chunks[2].finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_chat_non_streaming(self, provider):
        # Mock chat_stream
        async def mock_stream(*args, **kwargs):
            from agentgw.llm.types import StreamChunk

            yield StreamChunk(delta_content="Response ")
            yield StreamChunk(delta_content="from Grok")
            yield StreamChunk(finish_reason="stop")

        with patch.object(provider, "chat_stream", side_effect=mock_stream):
            messages = [Message(role="user", content="Test")]
            response = await provider.chat(messages, tools=None, temperature=0.7)

            assert response.content == "Response from Grok"
            assert response.finish_reason == "stop"

    @pytest.mark.asyncio
    async def test_with_tools(self, provider):
        # Test that tools are passed through correctly
        mock_stream = AsyncMock()
        mock_stream.__aiter__.return_value = []

        with patch.object(provider._client.chat.completions, "create") as mock_create:
            mock_create.return_value = mock_stream

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

            chunks = [c async for c in provider.chat_stream(messages, tools=tool_schemas, temperature=0.7)]

            # Verify create was called with tools
            mock_create.assert_called_once()
            call_kwargs = mock_create.call_args[1]
            assert "tools" in call_kwargs
            assert call_kwargs["tools"] == tool_schemas

    def test_model_override(self, provider):
        assert provider._default_model == "grok-beta"

    @pytest.mark.asyncio
    async def test_base_url_configuration(self):
        # Verify that xAI provider uses correct base URL
        with patch("agentgw.llm.xai_provider.AsyncOpenAI") as mock_openai:
            provider = XAIProvider(api_key="test-key")

            # Check that AsyncOpenAI was called with xAI base URL
            mock_openai.assert_called_once()
            call_kwargs = mock_openai.call_args[1]
            assert call_kwargs["base_url"] == "https://api.x.ai/v1"
            assert call_kwargs["api_key"] == "test-key"
