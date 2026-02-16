"""Anthropic (Claude) LLM provider implementation."""

from __future__ import annotations

import json
from typing import AsyncIterator

from anthropic import AsyncAnthropic

from agentgw.llm.types import (
    LLMResponse,
    Message,
    StreamChunk,
    ToolCall,
    ToolCallDelta,
    Usage,
)


class AnthropicProvider:
    """Anthropic Claude chat completion provider with streaming and tool calling."""

    def __init__(self, api_key: str, default_model: str = "claude-3-5-sonnet-20241022"):
        self._client = AsyncAnthropic(api_key=api_key)
        self._default_model = default_model

    def _convert_messages(self, messages: list[Message]) -> tuple[str, list[dict]]:
        """Convert internal Message objects to Anthropic API format.

        Returns (system_prompt, messages_list)
        """
        system_prompt = ""
        result = []

        for msg in messages:
            if msg.role == "system":
                # Anthropic uses separate system parameter
                system_prompt = msg.content or ""
                continue

            # Convert tool messages to user messages (Anthropic format)
            if msg.role == "tool":
                result.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content or "",
                    }],
                })
                continue

            # Regular assistant/user messages
            content = []
            if msg.content:
                content.append({"type": "text", "text": msg.content})

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        input_data = json.loads(tc.arguments)
                    except json.JSONDecodeError:
                        input_data = {}
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": input_data,
                    })

            if content:
                result.append({"role": msg.role, "content": content})

        return system_prompt, result

    def _convert_tools(self, tools: list[dict] | None) -> list[dict]:
        """Convert OpenAI tool format to Anthropic format."""
        if not tools:
            return []

        result = []
        for tool in tools:
            # OpenAI format: {type: "function", function: {name, description, parameters}}
            # Anthropic format: {name, description, input_schema}
            func = tool.get("function", {})
            result.append({
                "name": func.get("name", ""),
                "description": func.get("description", ""),
                "input_schema": func.get("parameters", {}),
            })
        return result

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> LLMResponse:
        """Non-streaming chat completion."""
        system_prompt, anthropic_messages = self._convert_messages(messages)

        kwargs: dict = {
            "model": model or self._default_model,
            "messages": anthropic_messages,
            "max_tokens": 4096,
            "temperature": temperature,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        response = await self._client.messages.create(**kwargs)

        # Parse response
        content_text = ""
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=json.dumps(block.input),
                ))

        return LLMResponse(
            content=content_text if content_text else None,
            tool_calls=tool_calls if tool_calls else None,
            usage=Usage(
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                total_tokens=response.usage.input_tokens + response.usage.output_tokens,
            ),
            finish_reason=response.stop_reason,
        )

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Streaming chat completion yielding chunks."""
        system_prompt, anthropic_messages = self._convert_messages(messages)

        kwargs: dict = {
            "model": model or self._default_model,
            "messages": anthropic_messages,
            "max_tokens": 4096,
            "temperature": temperature,
            "stream": True,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        if tools:
            kwargs["tools"] = self._convert_tools(tools)

        stream = await self._client.messages.create(**kwargs)

        # Track tool calls being accumulated
        current_tool_calls: dict[int, dict] = {}
        tool_call_index = 0

        async for event in stream:
            delta_content = None
            delta_tool_calls = None
            finish_reason = None

            if event.type == "content_block_start":
                if event.content_block.type == "tool_use":
                    # New tool call starting
                    current_tool_calls[tool_call_index] = {
                        "id": event.content_block.id,
                        "name": event.content_block.name,
                        "input": "",
                    }
                    delta_tool_calls = [ToolCallDelta(
                        index=tool_call_index,
                        id=event.content_block.id,
                        name=event.content_block.name,
                        arguments="",
                    )]
                    tool_call_index += 1

            elif event.type == "content_block_delta":
                if event.delta.type == "text_delta":
                    delta_content = event.delta.text
                elif event.delta.type == "input_json_delta":
                    # Accumulate tool input
                    idx = event.index
                    if idx in current_tool_calls:
                        current_tool_calls[idx]["input"] += event.delta.partial_json
                        delta_tool_calls = [ToolCallDelta(
                            index=idx,
                            arguments=event.delta.partial_json,
                        )]

            elif event.type == "message_delta":
                if event.delta.stop_reason:
                    finish_reason = event.delta.stop_reason

            yield StreamChunk(
                delta_content=delta_content,
                delta_tool_calls=delta_tool_calls,
                finish_reason=finish_reason,
            )
