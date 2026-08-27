"""ReAct agent loop. The only execution engine."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from agentgw.harness.session import Session
from agentgw.harness.spec import AgentSpec
from agentgw.llm.types import Message, ToolCall
from agentgw.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class AgentLoop:
    def __init__(
        self,
        spec: AgentSpec,
        llm,
        registry: ToolRegistry,
        session: Session,
    ):
        self._spec = spec
        self._llm = llm
        self._registry = registry
        self._session = session

    async def run(self, user_message: str) -> AsyncIterator[str]:
        user_msg = Message(role="user", content=user_message)
        self._session.add_message(user_msg)

        tool_schemas = self._registry.get_schemas(self._spec.tool_policy)
        if not tool_schemas:
            tool_schemas = None

        iteration = 0
        while iteration < self._spec.max_iterations:
            iteration += 1
            messages = self._build_messages()
            full_content = ""
            accumulated: dict[int, dict] = {}

            async for chunk in self._llm.chat_stream(
                messages=messages,
                tools=tool_schemas,
                temperature=self._spec.temperature,
                model=self._spec.model,
            ):
                if chunk.delta_content:
                    full_content += chunk.delta_content
                    yield chunk.delta_content
                if chunk.delta_tool_calls:
                    for delta in chunk.delta_tool_calls:
                        slot = accumulated.setdefault(
                            delta.index, {"id": "", "name": "", "arguments": ""}
                        )
                        if delta.id:
                            slot["id"] = delta.id
                        if delta.name:
                            slot["name"] = delta.name
                        if delta.arguments:
                            slot["arguments"] += delta.arguments

            tool_calls = None
            if accumulated:
                tool_calls = [
                    ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                    for tc in accumulated.values()
                ]

            assistant_msg = Message(
                role="assistant",
                content=full_content or None,
                tool_calls=tool_calls,
            )
            self._session.add_message(assistant_msg)

            if not tool_calls:
                return

            for tc in tool_calls:
                logger.info("Executing tool: %s", tc.name)
                try:
                    arguments = json.loads(tc.arguments) if tc.arguments else {}
                except json.JSONDecodeError:
                    arguments = {}
                if not isinstance(arguments, dict):
                    arguments = {}
                result = await self._registry.execute(
                    tc.name,
                    arguments,
                    self._spec.tool_policy,
                    ctx=self._spec.context,
                )
                self._session.add_message(
                    Message(
                        role="tool",
                        content=result,
                        tool_call_id=tc.id,
                        name=tc.name,
                    )
                )

        yield "\n\n[Agent reached maximum iterations]"

    async def run_to_completion(self, user_message: str) -> str:
        chunks: list[str] = []
        async for chunk in self.run(user_message):
            chunks.append(chunk)
        return "".join(chunks)

    def _build_messages(self) -> list[Message]:
        messages = [Message(role="system", content=self._spec.system_prompt)]
        messages.extend(self._session.get_messages())
        return messages
