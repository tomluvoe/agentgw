"""REST channel. One process serves one agent package."""

from typing import Any

from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.harness.run import Harness


def create_app(harness: Harness):
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except ImportError as e:
        raise RuntimeError(
            "Install the serve extra: uv sync --extra serve"
        ) from e

    sessions = SessionMap()

    class ChatRequest(BaseModel):
        message: str
        session_id: str | None = None

    class ChatResponse(BaseModel):
        session_id: str
        response: str

    app = FastAPI(title="agentgw", version="0.2.0")
    app.state.harness = harness

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "agent": harness.package.name}

    @app.get("/v1/skills")
    def skills() -> list[dict[str, str]]:
        return [
            {"name": s.name, "description": s.description, "path": str(s.path)}
            for s in harness.package.skills
        ]

    @app.get("/v1/tools")
    def tools() -> list[str]:
        return harness.package.tool_policy.filter(harness.package.registry.names())

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
    uvicorn.run(app, host=host, port=port)
