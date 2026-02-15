"""CLI interface for agentgw using Click."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from agentgw.core.config import get_project_root
from agentgw.core.service import AgentService


def _get_service(require_llm: bool = True) -> AgentService:
    """Create an AgentService, optionally skipping LLM init."""
    svc = AgentService()
    if require_llm:
        # Access .llm to trigger lazy init and fail early if no key
        try:
            _ = svc.llm
        except RuntimeError as e:
            click.echo(f"Error: {e}", err=True)
            sys.exit(1)
    return svc


@click.group()
@click.version_option(version="0.1.0", prog_name="agentgw")
def cli():
    """agentgw - Local AI Agent Framework"""
    pass


# ---------------------------------------------------------------------------
# chat — interactive session with feedback and session resume
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--skill", "-s", required=True, help="Skill to use")
@click.option("--session", "session_id", default=None, help="Resume a session by ID")
@click.option("--model", "-m", default=None, help="Override LLM model")
def chat(skill: str, session_id: str | None, model: str | None):
    """Start an interactive chat session with an agent."""
    asyncio.run(_chat(skill, session_id, model))


async def _chat(skill_name: str, session_id: str | None, model_override: str | None):
    svc = _get_service()
    await svc.initialize()

    try:
        agent, session, skill = await svc.create_agent(
            skill_name, session_id=session_id, model_override=model_override
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        return

    # Validate tools
    missing = svc.tool_registry.validate_tool_names(skill.tools)
    if missing:
        click.echo(f"Warning: Skill '{skill_name}' references unknown tools: {missing}", err=True)

    if session_id:
        msgs = await svc.memory.get_session_messages_formatted(session_id)
        click.echo(f"Resumed session {session_id} ({len(msgs)} messages)")
        for m in msgs[-6:]:  # Show last 6 messages for context
            role = "You" if m["role"] == "user" else "Agent"
            click.echo(f"  {role}> {m['content'][:120]}")
        click.echo()
    else:
        click.echo(f"Chat session started with skill: {skill.name}")
        click.echo(f"Session ID: {session.id}")
        click.echo(f"Description: {skill.description.strip()}")

    click.echo("Commands: 'exit'|'quit', '+1'/'-1' (feedback), '/history'\n")

    while True:
        try:
            user_input = click.prompt("You", prompt_suffix="> ")
        except (EOFError, KeyboardInterrupt):
            click.echo("\nGoodbye!")
            break

        stripped = user_input.strip()

        if stripped.lower() in ("exit", "quit"):
            click.echo("Goodbye!")
            break

        if not stripped:
            continue

        # Feedback commands
        if stripped in ("+1", "-1", "👍", "👎"):
            rating = 1 if stripped in ("+1", "👍") else -1
            msg_id = await svc.memory.get_last_assistant_message_id(session.id)
            if msg_id:
                await svc.memory.save_feedback(session.id, msg_id, rating)
                click.echo(f"  Feedback recorded: {'👍' if rating == 1 else '👎'}\n")
            else:
                click.echo("  No message to rate.\n")
            continue

        # History command
        if stripped == "/history":
            msgs = await svc.memory.get_session_messages_formatted(session.id)
            if not msgs:
                click.echo("  No messages yet.\n")
            else:
                for m in msgs:
                    role = "You" if m["role"] == "user" else "Agent"
                    content = m["content"][:200]
                    click.echo(f"  [{m['created_at']}] {role}> {content}")
                click.echo()
            continue

        click.echo("\nAgent> ", nl=False)
        async for chunk in agent.run(stripped):
            click.echo(chunk, nl=False)
        click.echo("\n")


# ---------------------------------------------------------------------------
# run — single-shot execution
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("message")
@click.option("--skill", "-s", required=True, help="Skill to use")
@click.option("--model", "-m", default=None, help="Override LLM model")
def run(message: str, skill: str, model: str | None):
    """Run a single message through a skill and exit."""
    asyncio.run(_run(message, skill, model))


async def _run(message: str, skill_name: str, model_override: str | None):
    svc = _get_service()
    await svc.initialize()

    try:
        agent, session, skill = await svc.create_agent(
            skill_name, model_override=model_override
        )
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        return

    async for chunk in agent.run(message):
        click.echo(chunk, nl=False)
    click.echo()


# ---------------------------------------------------------------------------
# skills — list available skills
# ---------------------------------------------------------------------------

@cli.command("skills")
def list_skills():
    """List available skills."""
    svc = _get_service(require_llm=False)
    skills = svc.skill_loader.list_skills()
    if not skills:
        click.echo("No skills found.")
        return

    click.echo(f"{'Name':<25} {'Tools':<6} {'Description'}")
    click.echo("-" * 75)
    for skill in skills:
        desc = skill.description.strip().split("\n")[0][:40]
        click.echo(f"{skill.name:<25} {len(skill.tools):<6} {desc}")


# ---------------------------------------------------------------------------
# ingest — add documents to RAG
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--collection", "-c", default="default", help="ChromaDB collection name")
@click.option("--tags", "-t", multiple=True, help="Tags for the document")
@click.option("--chunk-size", default=512, help="Characters per chunk")
def ingest(file_path: str, collection: str, tags: tuple[str, ...], chunk_size: int):
    """Ingest a document into the RAG knowledge base."""
    asyncio.run(_ingest(file_path, collection, list(tags), chunk_size))


async def _ingest(file_path: str, collection: str, tags: list[str], chunk_size: int):
    svc = _get_service(require_llm=False)
    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    chunk_ids = await svc.rag_store.ingest(
        text=text,
        metadata={"source": file_path, "tags": tags},
        collection=collection,
        chunk_size=chunk_size,
    )
    click.echo(f"Ingested {len(chunk_ids)} chunks from '{file_path}' into collection '{collection}'")
    if tags:
        click.echo(f"Tags: {', '.join(tags)}")


# ---------------------------------------------------------------------------
# sessions — list past sessions
# ---------------------------------------------------------------------------

@cli.command("sessions")
@click.option("--skill", "-s", default=None, help="Filter by skill name")
def list_sessions(skill: str | None):
    """List recent chat sessions."""
    asyncio.run(_list_sessions(skill))


async def _list_sessions(skill_name: str | None):
    svc = _get_service(require_llm=False)
    await svc.initialize()
    sessions = await svc.memory.get_sessions(skill_name=skill_name)
    if not sessions:
        click.echo("No sessions found.")
        return

    click.echo(f"{'ID':<38} {'Skill':<20} {'Updated'}")
    click.echo("-" * 80)
    for s in sessions:
        click.echo(f"{s['id']:<38} {s['skill_name'] or 'N/A':<20} {s['updated_at']}")


# ---------------------------------------------------------------------------
# history — view messages from a session
# ---------------------------------------------------------------------------

@cli.command("history")
@click.argument("session_id")
def show_history(session_id: str):
    """Show the conversation history for a session."""
    asyncio.run(_show_history(session_id))


async def _show_history(session_id: str):
    svc = _get_service(require_llm=False)
    await svc.initialize()
    msgs = await svc.memory.get_session_messages_formatted(session_id)
    if not msgs:
        click.echo("No messages found for this session.")
        return

    for m in msgs:
        role = "You" if m["role"] == "user" else "Agent"
        click.echo(f"[{m['created_at']}] {role}> {m['content']}")
        click.echo()


# ---------------------------------------------------------------------------
# web — launch the web UI server
# ---------------------------------------------------------------------------

@cli.command("web")
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to")
@click.option("--port", "-p", default=8080, help="Port to bind to")
@click.option("--reload", "do_reload", is_flag=True, help="Enable auto-reload for development")
def web_server(host: str, port: int, do_reload: bool):
    """Launch the web UI server."""
    import uvicorn
    from agentgw.interfaces.web.app import create_app

    svc = _get_service()
    app = create_app(service=svc)

    click.echo(f"Starting agentgw web UI at http://{host}:{port}")
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )
