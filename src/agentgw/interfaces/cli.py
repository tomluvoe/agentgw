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
@click.option("--skills", "-s", multiple=True, help="Skill names (empty = all skills)")
@click.option("--tags", "-t", multiple=True, help="Tags for the document")
@click.option("--chunk-size", default=512, help="Characters per chunk")
def ingest(file_path: str, collection: str, skills: tuple[str, ...], tags: tuple[str, ...], chunk_size: int):
    """Ingest a document into the RAG knowledge base."""
    asyncio.run(_ingest(file_path, collection, list(skills), list(tags), chunk_size))


async def _ingest(file_path: str, collection: str, skills: list[str], tags: list[str], chunk_size: int):
    svc = _get_service(require_llm=False)

    # Validate skills if provided
    if skills:
        available_skills = {s.name for s in svc.skill_loader.list_skills()}
        invalid_skills = [s for s in skills if s not in available_skills]

        if invalid_skills:
            click.echo(f"Error: Unknown skill(s): {', '.join(invalid_skills)}", err=True)
            click.echo(f"\nAvailable skills:", err=True)
            for skill_name in sorted(available_skills):
                click.echo(f"  - {skill_name}", err=True)
            click.echo(f"\nUse 'agentgw skills' to see all available skills.", err=True)
            sys.exit(1)

    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    chunk_ids = await svc.rag_store.ingest(
        text=text,
        metadata={"source": file_path, "skills": skills, "tags": tags},
        collection=collection,
        chunk_size=chunk_size,
    )
    click.echo(f"Ingested {len(chunk_ids)} chunks from '{file_path}' into collection '{collection}'")
    if skills:
        click.echo(f"Skills: {', '.join(skills)}")
    elif not skills:
        click.echo("Skills: (available to all)")
    if tags:
        click.echo(f"Tags: {', '.join(tags)}")


# ---------------------------------------------------------------------------
# documents — list ingested documents
# ---------------------------------------------------------------------------

@cli.command("documents")
@click.option("--collection", "-c", default="default", help="Collection to list from")
@click.option("--skills", "-s", multiple=True, help="Filter by skill name")
@click.option("--source", default=None, help="Filter by source (substring match)")
@click.option("--limit", "-n", default=100, help="Maximum number to display")
def list_documents(collection: str, skills: tuple[str, ...], source: str | None, limit: int):
    """List ingested RAG documents."""
    asyncio.run(_list_documents(collection, list(skills), source, limit))


async def _list_documents(collection: str, skills: list[str], source: str | None, limit: int):
    svc = _get_service(require_llm=False)
    docs = await svc.rag_store.list_documents(
        collection=collection,
        skills=skills if skills else None,
        source=source,
        limit=limit,
    )

    if not docs:
        click.echo("No documents found.")
        return

    click.echo(f"\n{len(docs)} document(s) in collection '{collection}':\n")
    for doc in docs:
        meta = doc["metadata"]
        doc_skills = meta.get("skills", "")
        doc_tags = meta.get("tags", "")
        chunk_info = f"chunk {meta.get('chunk_index', 0) + 1}/{meta.get('total_chunks', 1)}"

        click.echo(f"ID: {doc['id']}")
        click.echo(f"  Source: {meta.get('source', 'unknown')} ({chunk_info})")
        if doc_skills:
            click.echo(f"  Skills: {doc_skills}")
        else:
            click.echo(f"  Skills: (available to all)")
        if doc_tags:
            click.echo(f"  Tags: {doc_tags}")
        click.echo(f"  Preview: {doc['text']}")
        click.echo()


# ---------------------------------------------------------------------------
# delete-documents — remove documents from RAG
# ---------------------------------------------------------------------------

@cli.command("delete-documents")
@click.option("--collection", "-c", default="default", help="Collection to delete from")
@click.option("--source", default=None, help="Delete all chunks from this source")
@click.option("--id", "doc_ids", multiple=True, help="Document IDs to delete")
@click.confirmation_option(prompt="Are you sure you want to delete these documents?")
def delete_documents(collection: str, source: str | None, doc_ids: tuple[str, ...]):
    """Delete documents from the RAG knowledge base."""
    asyncio.run(_delete_documents(collection, source, list(doc_ids)))


async def _delete_documents(collection: str, source: str | None, doc_ids: list[str]):
    svc = _get_service(require_llm=False)

    if source:
        # Delete by source
        count = await svc.rag_store.delete_by_source(source, collection)
        click.echo(f"Deleted {count} document(s) with source '{source}'")
    elif doc_ids:
        # Delete by IDs
        await svc.rag_store.delete(doc_ids, collection)
        click.echo(f"Deleted {len(doc_ids)} document(s)")
    else:
        click.echo("Error: Must specify either --source or --id", err=True)


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
    """Launch the web UI server. DEPRECATED: Use 'agentgw serve' instead."""
    click.echo("⚠️  WARNING: 'agentgw web' is deprecated. Use 'agentgw serve' for daemon mode.", err=True)

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


@cli.command("serve")
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to")
@click.option("--port", "-p", default=8080, help="Port to bind to")
@click.option("--pidfile", type=click.Path(), help="PID file path")
@click.option("--no-scheduler", is_flag=True, help="Disable scheduler")
@click.option("--scheduler-config", type=click.Path(exists=True), help="Scheduler config file")
def serve(host: str, port: int, pidfile: str | None, no_scheduler: bool, scheduler_config: str | None):
    """Start agentgw daemon server (web + scheduler + API).

    This is the recommended way to run agentgw for production use.
    The daemon combines the web UI, REST API, and optional scheduler
    in a single long-running process.

    Examples:
      agentgw serve                                    # Start with defaults
      agentgw serve --host 0.0.0.0 --port 8080        # Bind to all interfaces
      agentgw serve --no-scheduler                     # Disable scheduler
      agentgw serve --pidfile /var/run/agentgw.pid    # Write PID file
    """
    import asyncio
    from pathlib import Path
    from agentgw.interfaces.server import DaemonServer

    svc = _get_service()

    daemon = DaemonServer(
        service=svc,
        pidfile=Path(pidfile) if pidfile else None,
    )

    try:
        asyncio.run(daemon.start(
            host=host,
            port=port,
            enable_scheduler=not no_scheduler,
            scheduler_config=Path(scheduler_config) if scheduler_config else None,
        ))
    except KeyboardInterrupt:
        click.echo("\nShutdown requested via Ctrl+C")
    except Exception as e:
        click.echo(f"Error starting daemon: {e}", err=True)
        raise


# ---------------------------------------------------------------------------
# scheduler — manage scheduled jobs
# ---------------------------------------------------------------------------

@cli.command("scheduler")
@click.option("--start", is_flag=True, help="Start the scheduler")
@click.option("--list", "list_jobs", is_flag=True, help="List scheduled jobs")
@click.option("--config", default="config/scheduled_jobs.yaml", help="Path to jobs config file")
def scheduler_cmd(start: bool, list_jobs: bool, config: str):
    """Manage scheduled agent tasks (cron-style)."""
    if start:
        asyncio.run(_start_scheduler(config))
    elif list_jobs:
        asyncio.run(_list_scheduled_jobs(config))
    else:
        click.echo("Use --start to run scheduler or --list to see jobs")
        click.echo("Example: agentgw scheduler --start")


async def _start_scheduler(config_path: str):
    """Start the scheduler and run until interrupted."""
    import signal
    from agentgw.scheduler.cron import CronScheduler, ScheduledJob

    svc = _get_service()
    await svc.initialize()

    # Load jobs from config
    config_file = Path(config_path)
    if not config_file.exists():
        click.echo(f"Config file not found: {config_path}", err=True)
        return

    import yaml
    with open(config_file) as f:
        config_data = yaml.safe_load(f) or {}

    jobs_data = config_data.get("jobs", [])
    if not jobs_data:
        click.echo("No jobs defined in config file", err=True)
        return

    # Create scheduler
    log_dir = svc.root / svc.settings.storage.log_dir
    scheduler = CronScheduler(svc, log_dir)

    # Add jobs
    enabled_count = 0
    for job_data in jobs_data:
        job = ScheduledJob(
            name=job_data["name"],
            skill_name=job_data["skill_name"],
            message=job_data["message"],
            cron_expression=job_data["cron_expression"],
            enabled=job_data.get("enabled", True),
            log_output=job_data.get("log_output", True),
        )
        scheduler.add_job(job)
        if job.enabled:
            enabled_count += 1

    if enabled_count == 0:
        click.echo("No enabled jobs. Edit config file to enable jobs.", err=True)
        return

    # Start scheduler
    scheduler.start()
    click.echo(f"Scheduler started with {enabled_count} enabled job(s)")
    click.echo("Press Ctrl+C to stop")

    # Wait for interrupt
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        click.echo("\nShutting down scheduler...")
        scheduler.shutdown()


async def _list_scheduled_jobs(config_path: str):
    """List configured jobs."""
    config_file = Path(config_path)
    if not config_file.exists():
        click.echo(f"Config file not found: {config_path}", err=True)
        return

    import yaml
    with open(config_file) as f:
        config_data = yaml.safe_load(f) or {}

    jobs_data = config_data.get("jobs", [])
    if not jobs_data:
        click.echo("No jobs configured")
        return

    click.echo(f"\nConfigured jobs in {config_path}:\n")
    for job in jobs_data:
        status = "✓ enabled" if job.get("enabled", True) else "✗ disabled"
        click.echo(f"  {job['name']} ({status})")
        click.echo(f"    Skill: {job['skill_name']}")
        click.echo(f"    Cron: {job['cron_expression']}")
        click.echo(f"    Task: {job['message'][:60]}...")
        click.echo()


# ---------------------------------------------------------------------------
# webhooks — webhook management
# ---------------------------------------------------------------------------

@cli.command("webhooks")
@click.option("--list", "list_hooks", is_flag=True, help="List configured webhooks")
@click.option("--config", default="config/webhooks.yaml", help="Webhook config file")
def webhooks_cmd(list_hooks: bool, config: str):
    """Manage webhook configurations."""
    root = get_project_root()
    config_path = root / config

    if not config_path.exists():
        click.echo(f"Webhook config not found: {config_path}", err=True)
        click.echo("Create config/webhooks.yaml to define webhooks")
        sys.exit(1)

    if list_hooks:
        _list_webhooks(config_path)
    else:
        click.echo(f"Webhook config: {config_path}")
        click.echo("Use --list to view configured webhooks")


def _list_webhooks(config_path: Path):
    """List configured webhooks."""
    import yaml
    with open(config_path) as f:
        data = yaml.safe_load(f)

    webhooks = data.get("webhooks", [])
    if not webhooks:
        click.echo("No webhooks configured")
        return

    click.echo(f"\nConfigured webhooks in {config_path}:\n")
    for hook in webhooks:
        status = "✓ enabled" if hook.get("enabled", True) else "✗ disabled"
        click.echo(f"  {hook['name']} ({status})")
        click.echo(f"    URL: {hook['url']}")
        click.echo(f"    Events: {', '.join(hook.get('events', []))}")
        if hook.get("secret"):
            click.echo(f"    Secret: {'*' * 20}")
        click.echo()
