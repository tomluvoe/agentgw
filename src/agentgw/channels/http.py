"""REST channel. One long-running process serves one agent package."""

from typing import Any

from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.channels.store import SessionStore
from agentgw.harness.run import Harness


def create_app(harness: Harness, sessions: SessionMap | None = None):
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except ImportError as e:
        raise RuntimeError(
            "Install the serve extra: uv sync --extra serve"
        ) from e

    if sessions is None:
        store = SessionStore(harness.package.workspace / ".agentgw" / "sessions")
        sessions = SessionMap(store)

    class ChatRequest(BaseModel):
        message: str
        session_id: str | None = None

    class ChatResponse(BaseModel):
        session_id: str
        response: str

    app = FastAPI(title="agentgw", version="0.2.0")
    app.state.harness = harness
    app.state.sessions = sessions

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "agent": harness.package.name,
            "workspace": str(harness.package.workspace),
        }

    @app.get("/v1/skills")
    def skills() -> list[dict[str, str]]:
        return [
            {"name": s.name, "description": s.description, "path": str(s.path)}
            for s in harness.package.skills
        ]

    @app.get("/v1/tools")
    def tools() -> list[str]:
        return harness.package.tool_policy.filter(harness.package.registry.names())

    @app.get("/v1/sessions")
    def list_sessions() -> dict[str, list[str]]:
        ids = set(sessions._sessions.keys())
        if sessions._store is not None:
            ids.update(sessions._store.list_ids())
        return {"sessions": sorted(ids)}

    @app.post("/v1/chat", response_model=ChatResponse)
    async def chat(req: ChatRequest) -> ChatResponse:
        if not req.message.strip():
            raise HTTPException(status_code=400, detail="message is required")
        key = req.session_id or ""
        if not key:
            from agentgw.harness.session import Session

            session = Session.create(harness.package.name)
            key = session.id
            sessions.put(key, session)
        reply, session = await handle_inbound(harness, sessions, key, req.message)
        return ChatResponse(session_id=session.id, response=reply)

    return app


def serve(harness: Harness, host: str = "127.0.0.1", port: int = 8080) -> None:
    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError("Install the serve extra: uv sync --extra serve") from e
    app = create_app(harness)
    print(f"agentgw daemon: agent={harness.package.name} http://{host}:{port}")
    print("Clients: AGENTGW_URL=http://%s:%s agentgw chat" % (host, port))
    uvicorn.run(app, host=host, port=port)
