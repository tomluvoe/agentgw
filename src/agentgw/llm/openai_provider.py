"""OpenAI LLM provider implementation."""

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


class OpenAIProvider:
    """OpenAI chat completion provider with streaming and tool calling."""

    def __init__(self, api_key: str, default_model: str = "gpt-4o"):
        self._client = AsyncOpenAI(api_key=api_key)
        self._default_model = default_model

    def _convert_messages(self, messages: list[Message]) -> list[dict]:
        """Convert internal Message objects to OpenAI API format."""
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

            delta_tool_calls = None
            if delta.tool_calls:
                delta_tool_calls = [
                    ToolCallDelta(
                        index=tc.index,
                        id=tc.id,
                        name=tc.function.name if tc.function else None,
                        arguments=tc.function.arguments if tc.function else None,
                    )
                    for tc in delta.tool_calls
                ]

            yield StreamChunk(
                delta_content=delta.content,
                delta_tool_calls=delta_tool_calls,
                finish_reason=finish_reason,
            )
