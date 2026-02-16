"""FastAPI application for the agentgw web UI."""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agentgw.auth.middleware import APIKeyMiddleware
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
        # Startup
        logger.info("Starting agentgw service...")
        await _service.initialize()
        logger.info("agentgw service initialized successfully")

        yield

        # Shutdown
        logger.info("Shutting down agentgw service...")
        # Close any open connections, cleanup resources
        if hasattr(_service, 'db_manager') and _service.db_manager:
            await _service.db_manager.close()
        logger.info("agentgw service shut down successfully")

    app = FastAPI(
        title="agentgw",
        version="0.1.0",
        description="Local AI agent framework with extendable SKILLs and tools",
        lifespan=lifespan,
        docs_url="/docs",  # Swagger UI at /docs
        redoc_url="/redoc",  # ReDoc at /redoc
        openapi_url="/openapi.json",
    )

    # Add authentication middleware
    app.add_middleware(APIKeyMiddleware, api_key=os.environ.get("AGENTGW_API_KEY"))

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Store templates and service on app state
    app.state.templates = templates
    app.state.service = _service

    # -----------------------------------------------------------------------
    # Health check (public endpoint)
    # -----------------------------------------------------------------------

    @app.get(
        "/health",
        tags=["System"],
        summary="Health check",
        description="Returns service health status and version information",
    )
    async def health_check():
        """Health check endpoint for monitoring and load balancers."""
        return JSONResponse({
            "status": "healthy",
            "version": "0.1.0",
            "provider": _service.settings.llm.provider,
            "model": _service.settings.llm.model,
        })

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

    @app.post(
        "/api/chat",
        tags=["Chat"],
        summary="Stream chat response",
        description="Send a message to an agent skill and receive streaming responses via Server-Sent Events (SSE)",
    )
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

    @app.post("/api/route", tags=["Chat"], summary="Route message to best skill")
    async def api_route(req: ChatRequest):
        """Route a message through the planner to find the best skill."""
        result = await _service.route_message(req.message)
        return {
            "skill": result.skill,
            "reasoning": result.reasoning,
            "refined_message": result.refined_message,
        }

    @app.post("/api/ingest", tags=["Knowledge Base"], summary="Ingest text to RAG")
    async def api_ingest(req: IngestRequest):
        """Ingest text into the RAG knowledge base."""
        # Validate skills if provided
        if req.skills:
            available_skills = {s.name for s in _service.skill_loader.list_skills()}
            invalid_skills = [s for s in req.skills if s not in available_skills]

            if invalid_skills:
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": f"Unknown skill(s): {', '.join(invalid_skills)}",
                        "available_skills": sorted(available_skills)
                    }
                )

        chunk_ids = await _service.rag_store.ingest(
            text=req.text,
            metadata={"source": req.source, "skills": req.skills or [], "tags": req.tags or []},
            collection=req.collection,
        )
        return {"status": "ok", "chunks_created": len(chunk_ids)}

    @app.get("/api/documents", tags=["Knowledge Base"], summary="List documents")
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

    @app.delete("/api/documents", tags=["Knowledge Base"], summary="Delete documents")
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


    @app.post("/api/feedback", tags=["Chat"], summary="Submit feedback")
    async def api_feedback(req: FeedbackRequest):
        """Submit feedback on the last assistant message."""
        msg_id = await _service.memory.get_last_assistant_message_id(req.session_id)
        if not msg_id:
            return {"status": "error", "message": "No message to rate"}
        await _service.memory.save_feedback(req.session_id, msg_id, req.rating)
        return {"status": "ok"}

    @app.get("/api/skills", tags=["Skills"], summary="List skills")
    async def api_skills():
        """List available skills."""
        skills = _service.skill_loader.list_skills()
        return [
            {"name": s.name, "description": s.description.strip(), "tags": s.tags, "tools": s.tools}
            for s in skills
        ]

    @app.get("/api/sessions", tags=["Sessions"], summary="List sessions")
    async def api_sessions(skill: str | None = None):
        """List recent sessions."""
        return await _service.memory.get_sessions(skill_name=skill)

    @app.get("/api/sessions/{session_id}/messages", tags=["Sessions"], summary="Get session messages")
    async def api_session_messages(session_id: str):
        """Get messages for a session."""
        return await _service.memory.get_session_messages_formatted(session_id)

    # -----------------------------------------------------------------------
    # v3 REST API - Extended endpoints
    # -----------------------------------------------------------------------

    @app.get("/api/config", tags=["System"], summary="Get configuration")
    async def api_config():
        """Get current configuration information."""
        return {
            "llm_provider": _service.settings.llm.provider,
            "llm_model": _service.settings.llm.model,
            "max_iterations": _service.settings.agent.max_iterations,
            "max_orchestration_depth": _service.settings.agent.max_orchestration_depth,
        }

    @app.get("/api/tools", tags=["Tools"], summary="List tools")
    async def api_tools():
        """List all registered tools."""
        tools = _service.tool_registry.list_tools()
        return {"tools": tools, "count": len(tools)}

    @app.post("/api/tools/{tool_name}/execute", tags=["Tools"], summary="Execute tool")
    async def api_execute_tool(tool_name: str, arguments: dict):
        """Execute a tool directly (for testing/debugging)."""
        try:
            result = await _service.tool_registry.execute(tool_name, arguments)
            return {"status": "ok", "result": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    @app.get("/api/feedback")
    async def api_get_feedback(
        session_id: str | None = None,
        skill: str | None = None,
        limit: int = 100,
    ):
        """Get feedback history."""
        # This would require adding a method to MemoryStore
        # For now, return placeholder
        return {"status": "ok", "feedback": [], "message": "Not yet implemented"}

    @app.get("/api/stats", tags=["System"], summary="Usage statistics")
    async def api_stats():
        """Get usage statistics."""
        sessions = await _service.memory.get_sessions(limit=1000)
        skills_used = {}
        for s in sessions:
            skill = s.get("skill_name", "unknown")
            skills_used[skill] = skills_used.get(skill, 0) + 1

        return {
            "total_sessions": len(sessions),
            "skills_used": skills_used,
        }

    return app
