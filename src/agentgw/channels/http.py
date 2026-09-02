"""REST channel. One long-running process serves one agent package."""

import json
import os
from contextlib import asynccontextmanager
from typing import Any

from agentgw.channels.hooks import HookRunner, load_hooks
from agentgw.channels.jobs import JobRunner, load_jobs
from agentgw.channels.sessions import SessionMap, handle_inbound, handle_inbound_stream
from agentgw.channels.store import SessionStore
from agentgw.harness.run import Harness


def create_app(
    harness: Harness,
    sessions: SessionMap | None = None,
    api_key: str | None = None,
    enable_channels: bool = False,
):
    try:
        from fastapi import FastAPI, HTTPException
        from fastapi.responses import JSONResponse, StreamingResponse
        from pydantic import BaseModel
        from starlette.requests import Request
    except ImportError as e:
        raise RuntimeError(
            "Install the serve extra: uv sync --extra serve"
        ) from e

    if api_key is None:
        api_key = os.environ.get("AGENTGW_API_KEY") or None
    if api_key == "":
        api_key = None

    if sessions is None:
        store = SessionStore(harness.package.workspace / ".agentgw" / "sessions")
        sessions = SessionMap(store)

    class ChatRequest(BaseModel):
        message: str
        session_id: str | None = None

    class ChatResponse(BaseModel):
        session_id: str
        response: str

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        bots = None
        if enable_channels:
            from agentgw.channels.bots import ChannelBots

            bots = ChannelBots(harness, sessions)
            started = await bots.start()
            app.state.bots = bots
            if started:
                print("Channels: " + ", ".join(started))
        yield
        if bots is not None:
            await bots.stop()

    app = FastAPI(title="agentgw", version="0.2.0", lifespan=lifespan)
    jobs = load_jobs(harness.package.directory / "jobs.yaml")
    runner = JobRunner(harness, sessions, jobs)
    hooks = load_hooks(harness.package.directory / "hooks.yaml")
    hook_runner = HookRunner(harness, sessions, hooks)

    app.state.harness = harness
    app.state.sessions = sessions
    app.state.api_key = api_key
    app.state.job_runner = runner
    app.state.hook_runner = hook_runner
    app.state.bots = None

    @app.middleware("http")
    async def require_api_key(request: Request, call_next):
        if api_key and request.url.path.startswith("/v1"):
            header = request.headers.get("authorization") or ""
            token = ""
            if header.lower().startswith("bearer "):
                token = header[7:].strip()
            if token != api_key:
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
        return await call_next(request)

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

    @app.post("/v1/chat/stream")
    async def chat_stream(req: ChatRequest):
        if not req.message.strip():
            raise HTTPException(status_code=400, detail="message is required")
        key = req.session_id or ""
        if not key:
            from agentgw.harness.session import Session

            session = Session.create(harness.package.name)
            key = session.id
            sessions.put(key, session)

        async def events():
            async for chunk, session in handle_inbound_stream(
                harness, sessions, key, req.message
            ):
                if chunk:
                    yield f"data: {json.dumps({'delta': chunk})}\n\n"
            session = sessions.get_or_create(key, harness.package.name)
            yield f"data: {json.dumps({'session_id': session.id, 'done': True})}\n\n"

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @app.get("/v1/jobs")
    def list_jobs() -> dict[str, Any]:
        return {"jobs": runner.list_jobs()}

    @app.post("/v1/jobs/{name}/run")
    async def run_job(name: str) -> dict[str, Any]:
        try:
            return await runner.run(name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown job: {name}")

    @app.get("/v1/hooks")
    def list_hooks() -> dict[str, Any]:
        return {"hooks": hook_runner.list_hooks()}

    @app.post("/v1/hooks/{name}")
    async def fire_hook(name: str, request: Request) -> dict[str, Any]:
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        try:
            return await hook_runner.run(name, payload)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"Unknown hook: {name}")
        except PermissionError:
            raise HTTPException(status_code=403, detail=f"Hook disabled: {name}")

    return app


def serve(
    harness: Harness,
    host: str = "127.0.0.1",
    port: int = 8080,
    api_key: str | None = None,
) -> None:
    try:
        import uvicorn
    except ImportError as e:
        raise RuntimeError("Install the serve extra: uv sync --extra serve") from e
    app = create_app(harness, api_key=api_key, enable_channels=True)
    runner = app.state.job_runner
    runner.start()
    print(f"agentgw daemon: agent={harness.package.name} http://{host}:{port}")
    print("Clients: AGENTGW_URL=http://%s:%s agentgw chat" % (host, port))
    print("Discord/Telegram attach when DISCORD_BOT_TOKEN / TELEGRAM_BOT_TOKEN are set")
    if app.state.api_key:
        print("API key auth is ON for /v1/*  (/health stays public)")
    enabled = [j for j in runner.list_jobs() if j["enabled"]]
    if enabled:
        print(f"Jobs: {', '.join(j['name'] for j in enabled)}")
    try:
        uvicorn.run(app, host=host, port=port)
    finally:
        runner.stop()
