"""xAI (Grok) LLM provider implementation.

xAI uses an OpenAI-compatible API, so we can largely reuse the OpenAI implementation.
Docs: https://docs.x.ai/developers/quickstart
"""

from __future__ import annotations

import json
from typing import AsyncIterator

from openai import AsyncOpenAI

from agentgw.llm.types import (
    LLMResponse,
    Message,
    StreamChunk,
    ToolCall,
    ToolCallDelta,
    Usage,
)


class XAIProvider:
    """xAI (Grok) chat completion provider with streaming and tool calling.

    Uses OpenAI-compatible API with base_url override.
    """

    def __init__(self, api_key: str, default_model: str = "grok-beta"):
        # xAI uses OpenAI-compatible API at api.x.ai
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://api.x.ai/v1"
        )
        self._default_model = default_model

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal Message objects to OpenAI/xAI API format."""
        result = []
        for msg in messages:
            d: dict = {"role": msg.role}
            if msg.content is not None:
                d["content"] = msg.content
            if msg.tool_calls:
                d["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": tc.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id is not None:
                d["tool_call_id"] = msg.tool_call_id
            if msg.name is not None:
                d["name"] = msg.name
            result.append(d)
        return result

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> LLMResponse:
        """Non-streaming chat completion."""
        kwargs: dict = {
            "model": model or self._default_model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message

        tool_calls = None
        if message.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                )
                for tc in message.tool_calls
            ]

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            usage=Usage(
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
                total_tokens=response.usage.total_tokens if response.usage else 0,
            ),
            finish_reason=choice.finish_reason,
        )

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion yielding chunks."""
        kwargs: dict = {
            "model": model or self._default_model,
            "messages": self._convert_messages(messages),
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        stream = await self._client.chat.completions.create(**kwargs)

        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            finish_reason = chunk.choices[0].finish_reason

            delta_content = delta.content if delta.content else None
            delta_tool_calls = None

            if delta.tool_calls:
                delta_tool_calls = []
                for tc_delta in delta.tool_calls:
                    delta_tool_calls.append(ToolCallDelta(
                        index=tc_delta.index,
                        id=tc_delta.id if tc_delta.id else None,
                        name=tc_delta.function.name if tc_delta.function and tc_delta.function.name else None,
                        arguments=tc_delta.function.arguments if tc_delta.function and tc_delta.function.arguments else None,
                    ))

            yield StreamChunk(
                delta_content=delta_content,
                delta_tool_calls=delta_tool_calls,
                finish_reason=finish_reason,
            )
