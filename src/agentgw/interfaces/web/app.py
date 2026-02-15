"""FastAPI application for the agentgw web UI."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agentgw.core.service import AgentService

logger = logging.getLogger(__name__)


# Request models (module-level for FastAPI compatibility with __future__ annotations)
class ChatRequest(BaseModel):
    message: str
    skill_name: str
    session_id: str | None = None


class IngestRequest(BaseModel):
    text: str
    source: str = "web_upload"
    skills: list[str] | None = None
    tags: list[str] | None = None
    collection: str = "default"


class FeedbackRequest(BaseModel):
    session_id: str
    rating: int

# Module-level service instance (initialized in create_app)
_service: AgentService | None = None

WEB_DIR = Path(__file__).parent
TEMPLATES_DIR = WEB_DIR / "templates"
STATIC_DIR = WEB_DIR / "static"


def create_app(service: AgentService | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    global _service
    _service = service or AgentService()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await _service.initialize()
        yield

    app = FastAPI(title="agentgw", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Store templates and service on app state
    app.state.templates = templates
    app.state.service = _service

    # -----------------------------------------------------------------------
    # Page routes
    # -----------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        skills = _service.skill_loader.list_skills()
        sessions = await _service.memory.get_sessions(limit=10)
        return templates.TemplateResponse(request, "index.html", {
            "skills": skills,
            "sessions": sessions,
        })

    @app.get("/chat/{skill_name}", response_class=HTMLResponse)
    async def chat_page(request: Request, skill_name: str, session_id: str | None = None):
        skill = _service.skill_loader.load(skill_name)
        if skill is None:
            return HTMLResponse("Skill not found", status_code=404)
        history = []
        if session_id:
            history = await _service.memory.get_session_messages_formatted(session_id)
        return templates.TemplateResponse(request, "chat.html", {
            "skill": skill,
            "session_id": session_id,
            "history": history,
        })

    @app.get("/ingest", response_class=HTMLResponse)
    async def ingest_page(request: Request):
        return templates.TemplateResponse(request, "ingest.html")

    @app.get("/documents", response_class=HTMLResponse)
    async def documents_page(request: Request):
        return templates.TemplateResponse(request, "documents.html")

    # -----------------------------------------------------------------------
    # API routes
    # -----------------------------------------------------------------------

    @app.post("/api/chat")
    async def api_chat(req: ChatRequest):
        """SSE endpoint for streaming chat responses."""

        async def event_generator() -> AsyncIterator[dict]:
            try:
                agent, session, skill = await _service.create_agent(
                    req.skill_name,
                    session_id=req.session_id,
                )
            except ValueError as e:
                yield {"event": "error", "data": json.dumps({"error": str(e)})}
                return

            # Send session info first
            yield {
                "event": "session",
                "data": json.dumps({"session_id": session.id, "skill": skill.name}),
            }

            try:
                async for chunk in agent.run(req.message):
                    yield {"event": "chunk", "data": json.dumps({"text": chunk})}
            except Exception as e:
                logger.exception("Agent error")
                yield {"event": "error", "data": json.dumps({"error": str(e)})}

            yield {"event": "done", "data": json.dumps({"status": "complete"})}

        return EventSourceResponse(event_generator())

    @app.post("/api/route")
    async def api_route(req: ChatRequest):
        """Route a message through the planner to find the best skill."""
        result = await _service.route_message(req.message)
        return {
            "skill": result.skill,
            "reasoning": result.reasoning,
            "refined_message": result.refined_message,
        }

    @app.post("/api/ingest")
    async def api_ingest(req: IngestRequest):
        """Ingest text into the RAG knowledge base."""
        chunk_ids = await _service.rag_store.ingest(
            text=req.text,
            metadata={"source": req.source, "skills": req.skills or [], "tags": req.tags or []},
            collection=req.collection,
        )
        return {"status": "ok", "chunks_created": len(chunk_ids)}

    @app.get("/api/documents")
    async def api_list_documents(
        collection: str = "default",
        skills: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ):
        """List ingested documents."""
        skill_list = [s.strip() for s in skills.split(",")] if skills else None
        docs = await _service.rag_store.list_documents(
            collection=collection,
            skills=skill_list,
            source=source,
            limit=limit,
        )
        return {"documents": docs, "count": len(docs)}

    @app.delete("/api/documents")
    async def api_delete_documents(
        collection: str = "default",
        source: str | None = None,
        ids: str | None = None,
    ):
        """Delete documents from the knowledge base."""
        if source:
            count = await _service.rag_store.delete_by_source(source, collection)
            return {"status": "ok", "deleted": count}
        elif ids:
            id_list = [i.strip() for i in ids.split(",")]
            await _service.rag_store.delete(id_list, collection)
            return {"status": "ok", "deleted": len(id_list)}
        else:
            return {"status": "error", "message": "Must specify either 'source' or 'ids'"}


    @app.post("/api/feedback")
    async def api_feedback(req: FeedbackRequest):
        """Submit feedback on the last assistant message."""
        msg_id = await _service.memory.get_last_assistant_message_id(req.session_id)
        if not msg_id:
            return {"status": "error", "message": "No message to rate"}
        await _service.memory.save_feedback(req.session_id, msg_id, req.rating)
        return {"status": "ok"}

    @app.get("/api/skills")
    async def api_skills():
        """List available skills."""
        skills = _service.skill_loader.list_skills()
        return [
            {"name": s.name, "description": s.description.strip(), "tags": s.tags, "tools": s.tools}
            for s in skills
        ]

    @app.get("/api/sessions")
    async def api_sessions(skill: str | None = None):
        """List recent sessions."""
        return await _service.memory.get_sessions(skill_name=skill)

    @app.get("/api/sessions/{session_id}/messages")
    async def api_session_messages(session_id: str):
        """Get messages for a session."""
        return await _service.memory.get_session_messages_formatted(session_id)

    return app
