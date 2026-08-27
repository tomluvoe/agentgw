"""Map an external conversation id to a harness Session."""

from __future__ import annotations

from agentgw.harness.session import Session


class SessionMap:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}

    def get_or_create(self, key: str, agent_name: str) -> Session:
        session = self._sessions.get(key)
        if session is None:
            session = Session.create(agent_name)
            self._sessions[key] = session
        return session

    def put(self, key: str, session: Session) -> None:
        self._sessions[key] = session


async def handle_inbound(harness, sessions: SessionMap, key: str, text: str) -> tuple[str, Session]:
    """Shared path for every channel: lookup session, run harness, return text."""
    session = sessions.get_or_create(key, harness.package.name)
    reply = await harness.run_to_completion(text, session=session)
    return reply, session
