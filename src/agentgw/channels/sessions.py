"""Map an external conversation id to a harness Session."""

from __future__ import annotations

from agentgw.channels.store import SessionStore
from agentgw.harness.session import Session


class SessionMap:
    def __init__(self, store: SessionStore | None = None) -> None:
        self._sessions: dict[str, Session] = {}
        self._store = store

    def get_or_create(self, key: str, agent_name: str) -> Session:
        session = self._sessions.get(key)
        if session is None and self._store is not None:
            try:
                session = self._store.load(key)
            except ValueError:
                session = None
            if session is not None:
                self._sessions[key] = session
        if session is None:
            session = Session.create(agent_name) if key == "" else Session(id=key, agent_name=agent_name)
            if not key:
                key = session.id
            self._sessions[key] = session
        return session

    def put(self, key: str, session: Session) -> None:
        self._sessions[key] = session
        if self._store is not None:
            self._store.save(session)

    def persist(self, session: Session) -> None:
        self._sessions[session.id] = session
        if self._store is not None:
            self._store.save(session)


async def handle_inbound(harness, sessions: SessionMap, key: str, text: str) -> tuple[str, Session]:
    """Shared path for every channel: lookup session, run harness, return text."""
    session = sessions.get_or_create(key, harness.package.name)
    reply = await harness.run_to_completion(text, session=session)
    sessions.persist(session)
    return reply, session


async def handle_inbound_stream(harness, sessions: SessionMap, key: str, text: str):
    """Yield (chunk, session) then persist once the turn is done."""
    session = sessions.get_or_create(key, harness.package.name)
    async for chunk in harness.run(text, session=session):
        yield chunk, session
    sessions.persist(session)
