"""Disk-backed conversation sessions so a running agent survives over time."""

from __future__ import annotations

import json
from pathlib import Path

from agentgw.harness.session import Session
from agentgw.llm.types import Message, ToolCall


class SessionStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, session_id: str) -> Path:
        safe = "".join(c for c in session_id if c.isalnum() or c in "-_")
        if not safe or safe != session_id:
            raise ValueError(f"Invalid session id: {session_id}")
        return self.root / f"{safe}.json"

    def load(self, session_id: str) -> Session | None:
        path = self.path_for(session_id)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return _session_from_dict(data)

    def save(self, session: Session) -> None:
        path = self.path_for(session.id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(_session_to_dict(session), indent=2), encoding="utf-8")
        tmp.replace(path)

    def list_ids(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.json"))


def _session_to_dict(session: Session) -> dict:
    return {
        "id": session.id,
        "agent_name": session.agent_name,
        "messages": [_message_to_dict(m) for m in session.messages],
    }


def _session_from_dict(data: dict) -> Session:
    session = Session(id=data["id"], agent_name=data.get("agent_name"))
    for raw in data.get("messages") or []:
        session.add_message(_message_from_dict(raw))
    return session


def _message_to_dict(message: Message) -> dict:
    payload: dict = {"role": message.role, "content": message.content}
    if message.tool_call_id:
        payload["tool_call_id"] = message.tool_call_id
    if message.name:
        payload["name"] = message.name
    if message.tool_calls:
        payload["tool_calls"] = [
            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
            for tc in message.tool_calls
        ]
    return payload


def _message_from_dict(data: dict) -> Message:
    tool_calls = None
    if data.get("tool_calls"):
        tool_calls = [
            ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
            for tc in data["tool_calls"]
        ]
    return Message(
        role=data["role"],
        content=data.get("content"),
        tool_calls=tool_calls,
        tool_call_id=data.get("tool_call_id"),
        name=data.get("name"),
    )
