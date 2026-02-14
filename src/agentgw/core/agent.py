"""Core agent loop implementing the ReAct pattern."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from agentgw.core.session import Session
from agentgw.core.skill_loader import Skill
from agentgw.core.tool_registry import ToolRegistry
from agentgw.llm.openai_provider import OpenAIProvider
from agentgw.llm.types import LLMResponse, Message, StreamChunk, ToolCall, ToolCallDelta
from agentgw.memory.store import MemoryStore

logger = logging.getLogger(__name__)


class AgentLoop:
    """ReAct-style agent loop with streaming support.

    Flow:
    1. Build messages from system prompt + history + user message
    2. Call LLM (streaming)
    3. If tool_calls: execute tools, append results, go to 2
    4. If text response: yield to caller, done
    5. Guard: max_iterations to prevent runaway loops
    """

    def __init__(
        self,
        skill: Skill,
        llm: OpenAIProvider,
        tool_registry: ToolRegistry,
        memory: MemoryStore,
        session: Session,
        max_iterations: int | None = None,
    ):
        self._skill = skill
        self._llm = llm
        self._tools = tool_registry
        self._memory = memory
        self._session = session
        self._max_iterations = max_iterations or skill.max_iterations

    async def run(self, user_message: str) -> AsyncIterator[str]:
        """Execute the agent loop, yielding streamed text chunks.

        This is an async generator that yields text as it arrives from the LLM.
        Tool calls are executed silently between text chunks.
        """
        # Add user message to session
        user_msg = Message(role="user", content=user_message)
        self._session.add_message(user_msg)
        await self._memory.save_message(
            self._session.id, user_msg, self._skill.name
        )

        # Get tool schemas for this skill
        tool_schemas = self._tools.get_schemas(self._skill.tools) if self._skill.tools else None

        iteration = 0
        while iteration < self._max_iterations:
            iteration += 1
            logger.debug("Agent iteration %d/%d", iteration, self._max_iterations)

            # Build full message list
            messages = self._build_messages()

            # Stream the LLM response and accumulate
            full_content = ""
            accumulated_tool_calls: dict[int, dict] = {}  # index -> {id, name, arguments}
            finish_reason = None

            async for chunk in self._llm.chat_stream(
                messages=messages,
                tools=tool_schemas,
                temperature=self._skill.temperature,
                model=self._skill.model,
            ):
                # Yield text content to the caller
                if chunk.delta_content:
                    full_content += chunk.delta_content
                    yield chunk.delta_content

                # Accumulate tool call deltas
                if chunk.delta_tool_calls:
                    for tc_delta in chunk.delta_tool_calls:
                        if tc_delta.index not in accumulated_tool_calls:
                            accumulated_tool_calls[tc_delta.index] = {
                                "id": "", "name": "", "arguments": ""
                            }
                        tc = accumulated_tool_calls[tc_delta.index]
                        if tc_delta.id:
                            tc["id"] = tc_delta.id
                        if tc_delta.name:
                            tc["name"] = tc_delta.name
                        if tc_delta.arguments:
                            tc["arguments"] += tc_delta.arguments

                if chunk.finish_reason:
                    finish_reason = chunk.finish_reason

            # Build the assistant message
            tool_calls = None
            if accumulated_tool_calls:
                tool_calls = [
                    ToolCall(
                        id=tc["id"],
                        name=tc["name"],
                        arguments=tc["arguments"],
                    )
                    for tc in accumulated_tool_calls.values()
                ]

            assistant_msg = Message(
                role="assistant",
                content=full_content or None,
                tool_calls=tool_calls,
            )
            self._session.add_message(assistant_msg)
            await self._memory.save_message(
                self._session.id, assistant_msg, self._skill.name
            )

            # If no tool calls, we're done
            if not tool_calls:
                return

            # Execute tool calls and add results
            for tc in tool_calls:
                logger.info("Executing tool: %s", tc.name)
                try:
                    arguments = json.loads(tc.arguments)
                except json.JSONDecodeError:
                    arguments = {}

                result = await self._tools.execute(tc.name, arguments)

                tool_msg = Message(
                    role="tool",
                    content=result,
                    tool_call_id=tc.id,
                    name=tc.name,
                )
                self._session.add_message(tool_msg)
                await self._memory.save_message(
                    self._session.id, tool_msg, self._skill.name
                )

            # Loop back to call LLM again with tool results

        # Max iterations reached
        yield "\n\n[Agent reached maximum iterations]"

    async def run_to_completion(self, user_message: str) -> str:
        """Non-streaming convenience method. Returns the full response."""
        chunks: list[str] = []
        async for chunk in self.run(user_message):
            chunks.append(chunk)
        return "".join(chunks)

    def _build_messages(self) -> list[Message]:
        """Build the full message list: system prompt + conversation history."""
        messages = [Message(role="system", content=self._skill.system_prompt)]
        messages.extend(self._session.get_messages())
        return messages
