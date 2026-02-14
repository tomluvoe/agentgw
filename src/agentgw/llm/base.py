"""Abstract LLM provider interface."""

from __future__ import annotations

from typing import AsyncIterator, Protocol

from agentgw.llm.types import LLMResponse, Message, StreamChunk


class LLMProvider(Protocol):
    """Protocol that all LLM providers must implement."""

    async def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> LLMResponse: ...

    async def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
        model: str | None = None,
    ) -> AsyncIterator[StreamChunk]: ...
