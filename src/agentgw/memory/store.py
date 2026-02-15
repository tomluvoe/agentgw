"""Memory store for conversation history and feedback."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from agentgw.db.sqlite import DatabaseManager
from agentgw.llm.types import Message, ToolCall
from agentgw.memory.models import SCHEMA_SQL


class MemoryStore:
    """SQLite-backed conversation persistence and feedback tracking."""

    def __init__(self, db_path: Path):
        self._db = DatabaseManager(db_path)

    async def initialize(self) -> None:
        """Create tables if needed."""
        await self._db.initialize(SCHEMA_SQL)

    async def create_session(
        self, skill_name: str | None = None, session_id: str | None = None
    ) -> str:
        """Create a new session and return its ID."""
        sid = session_id or str(uuid.uuid4())
        await self._db.execute(
            "INSERT INTO sessions (id, skill_name) VALUES (?, ?)",
            (sid, skill_name),
        )
        return sid

    async def save_message(
        self,
        session_id: str,
        message: Message,
        skill_name: str | None = None,
    ) -> str:
        """Save a message to conversation history. Returns message ID."""
        msg_id = str(uuid.uuid4())
        tool_calls_json = None
        if message.tool_calls:
            tool_calls_json = json.dumps(
                [{"id": tc.id, "name": tc.name, "arguments": tc.arguments} for tc in message.tool_calls]
            )
        await self._db.execute(
            """INSERT INTO conversations
               (id, session_id, skill_name, role, content, tool_calls, tool_call_id, tool_name)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                msg_id,
                session_id,
                skill_name,
                message.role,
                message.content,
                tool_calls_json,
                message.tool_call_id,
                message.name,
            ),
        )
        # Update session timestamp
        await self._db.execute(
            "UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,),
        )
        return msg_id

    async def get_history(self, session_id: str, limit: int = 50) -> list[Message]:
        """Retrieve conversation history for a session."""
        rows = await self._db.execute_query(
            """SELECT role, content, tool_calls, tool_call_id, tool_name
               FROM conversations WHERE session_id = ?
               ORDER BY created_at ASC LIMIT ?""",
            (session_id, limit),
        )
        messages = []
        for row in rows:
            tool_calls = None
            if row["tool_calls"]:
                tc_data = json.loads(row["tool_calls"])
                tool_calls = [
                    ToolCall(id=tc["id"], name=tc["name"], arguments=tc["arguments"])
                    for tc in tc_data
                ]
            messages.append(
                Message(
                    role=row["role"],
                    content=row["content"],
                    tool_calls=tool_calls,
                    tool_call_id=row["tool_call_id"],
                    name=row["tool_name"],
                )
            )
        return messages

    async def get_last_assistant_message_id(self, session_id: str) -> str | None:
        """Get the ID of the most recent assistant message in a session."""
        rows = await self._db.execute_query(
            """SELECT id FROM conversations
               WHERE session_id = ? AND role = 'assistant'
               ORDER BY created_at DESC LIMIT 1""",
            (session_id,),
        )
        return rows[0]["id"] if rows else None

    async def save_feedback(
        self,
        session_id: str,
        message_id: str,
        rating: int,
        comment: str | None = None,
    ) -> None:
        """Save user feedback on a message."""
        feedback_id = str(uuid.uuid4())
        await self._db.execute(
            "INSERT INTO feedback (id, session_id, message_id, rating, comment) VALUES (?, ?, ?, ?, ?)",
            (feedback_id, session_id, message_id, rating, comment),
        )

    async def get_sessions(
        self, skill_name: str | None = None, limit: int = 20
    ) -> list[dict]:
        """List recent sessions."""
        if skill_name:
            return await self._db.execute_query(
                """SELECT id, skill_name, created_at, updated_at, summary
                   FROM sessions WHERE skill_name = ?
                   ORDER BY updated_at DESC LIMIT ?""",
                (skill_name, limit),
            )
        return await self._db.execute_query(
            """SELECT id, skill_name, created_at, updated_at, summary
               FROM sessions ORDER BY updated_at DESC LIMIT ?""",
            (limit,),
        )

    async def get_session_messages_formatted(self, session_id: str) -> list[dict]:
        """Get messages for display (excludes tool-internal messages)."""
        rows = await self._db.execute_query(
            """SELECT id, role, content, created_at
               FROM conversations
               WHERE session_id = ? AND role IN ('user', 'assistant') AND content IS NOT NULL
               ORDER BY created_at ASC""",
            (session_id,),
        )
        return rows
