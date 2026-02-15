"""Core agent loop implementing the ReAct pattern."""

from __future__ import annotations

import json
import logging
from contextvars import ContextVar
from typing import AsyncIterator

from agentgw.core.session import Session
from agentgw.core.skill_loader import Skill
from agentgw.core.tool_registry import ToolRegistry
from agentgw.llm.types import Message, ToolCall
from agentgw.memory.store import MemoryStore

logger = logging.getLogger(__name__)

# Context variable for tracking orchestration depth across async calls
_orchestration_depth: ContextVar[int] = ContextVar("orchestration_depth", default=0)


def get_current_orchestration_depth() -> int:
    """Get the current orchestration depth."""
    return _orchestration_depth.get()


def set_current_orchestration_depth(depth: int) -> None:
    """Set the current orchestration depth."""
    _orchestration_depth.set(depth)


class AgentLoop:
    """ReAct-style agent loop with streaming support.

    Flow:
    1. Build messages from system prompt + RAG context + examples + history + user message
    2. Call LLM (streaming)
    3. If tool_calls: execute tools, append results, go to 2
    4. If text response: yield to caller, done
    5. Guard: max_iterations to prevent runaway loops
    """

    def __init__(
        self,
        skill: Skill,
        llm,  # LLMProvider protocol
        tool_registry: ToolRegistry,
        memory: MemoryStore,
        session: Session,
        rag_store=None,
        max_iterations: int | None = None,
        orchestration_depth: int = 0,
    ):
        self._skill = skill
        self._llm = llm
        self._tools = tool_registry
        self._memory = memory
        self._session = session
        self._rag_store = rag_store
        self._max_iterations = max_iterations or skill.max_iterations
        self._orchestration_depth = orchestration_depth

    async def run(self, user_message: str) -> AsyncIterator[str]:
        """Execute the agent loop, yielding streamed text chunks."""
        # Set orchestration depth for this execution context
        set_current_orchestration_depth(self._orchestration_depth)

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
            messages = await self._build_messages()

            # Stream the LLM response and accumulate
            full_content = ""
            accumulated_tool_calls: dict[int, dict] = {}
            finish_reason = None

            async for chunk in self._llm.chat_stream(
                messages=messages,
                tools=tool_schemas,
                temperature=self._skill.temperature,
                model=self._skill.model,
            ):
                if chunk.delta_content:
                    full_content += chunk.delta_content
                    yield chunk.delta_content

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

            if not tool_calls:
                return

            # Execute tool calls
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

        yield "\n\n[Agent reached maximum iterations]"

    async def run_to_completion(self, user_message: str) -> str:
        """Non-streaming convenience method. Returns the full response."""
        chunks: list[str] = []
        async for chunk in self.run(user_message):
            chunks.append(chunk)
        return "".join(chunks)

    async def _build_messages(self) -> list[Message]:
        """Build the full message list: system prompt + RAG context + examples + history."""
        system_content = self._skill.system_prompt

        # Auto-inject RAG context if configured
        rag_ctx = self._skill.rag_context
        if rag_ctx and rag_ctx.get("enabled") and self._rag_store:
            # Auto-filter by current skill name (documents with empty skills match all)
            # Users can override with explicit skill names in rag_context.skills
            rag_skills = rag_ctx.get("skills", [self._skill.name])
            rag_tags = rag_ctx.get("tags", [])
            top_k = rag_ctx.get("top_k", 3)
            # Use the last user message as query
            last_user = None
            for msg in reversed(self._session.get_messages()):
                if msg.role == "user" and msg.content:
                    last_user = msg.content
                    break
            if last_user:
                results = await self._rag_store.search(
                    query=last_user,
                    skills=rag_skills,
                    tags=rag_tags,
                    top_k=top_k,
                )
                if results:
                    context_parts = []
                    for r in results:
                        context_parts.append(r["text"])
                    context_block = "\n---\n".join(context_parts)
                    system_content += (
                        f"\n\n## Relevant Knowledge Base Context\n{context_block}"
                    )

        messages = [Message(role="system", content=system_content)]

        # Inject few-shot examples
        for example in self._skill.examples:
            if "user" in example:
                messages.append(Message(role="user", content=example["user"]))
            if "assistant" in example:
                messages.append(Message(role="assistant", content=example["assistant"]))

        # Add conversation history
        messages.extend(self._session.get_messages())
        return messages
