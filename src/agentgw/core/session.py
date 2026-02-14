"""Session management for agent conversations."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from agentgw.llm.types import Message


@dataclass
class Session:
    """Tracks the state of an agent conversation session."""

    id: str
    skill_name: str | None = None
    messages: list[Message] = field(default_factory=list)

    @classmethod
    def create(cls, skill_name: str | None = None) -> Session:
        return cls(id=str(uuid.uuid4()), skill_name=skill_name)

    def add_message(self, message: Message) -> None:
        self.messages.append(message)

    def get_messages(self) -> list[Message]:
        return list(self.messages)
