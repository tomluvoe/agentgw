"""CLI interface for agentgw using Click."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from agentgw.core.agent import AgentLoop
from agentgw.core.config import get_project_root, load_settings
from agentgw.core.session import Session
from agentgw.core.skill_loader import SkillLoader
from agentgw.core.tool_registry import ToolRegistry
from agentgw.llm.openai_provider import OpenAIProvider
from agentgw.memory.store import MemoryStore
from agentgw.rag.chroma import RAGStore
from agentgw.tools.rag_tools import set_rag_store
from agentgw.tools.sql_tools import set_db_manager


def _load_env():
    """Load .env file if it exists."""
    try:
        from dotenv import load_dotenv
        root = get_project_root()
        load_dotenv(root / ".env")
    except ImportError:
        pass


class AppContext:
    """Holds initialized application components."""

    def __init__(self, require_llm: bool = True):
        _load_env()
        self.settings = load_settings()
        self.root = get_project_root()

        # Initialize skill loader
        skills_dir = self.root / self.settings.skills_dir
        self.skill_loader = SkillLoader(skills_dir)
        self.skill_loader.load_all()

        # Initialize tool registry
        self.tool_registry = ToolRegistry()
        self.tool_registry.discover(self.settings.tools_modules)

        # Initialize storage
        db_path = self.root / self.settings.storage.sqlite_path
        self.memory = MemoryStore(db_path)

        chroma_path = self.root / self.settings.storage.chroma_path
        self.rag_store = RAGStore(chroma_path)

        # Wire up tool dependencies
        set_rag_store(self.rag_store)
        set_db_manager(None)  # DB manager for sql_tools, wired separately

        # Initialize LLM provider only if needed
        self.llm: OpenAIProvider | None = None
        if require_llm:
            self._init_llm()

    def _init_llm(self):
        """Initialize the LLM provider."""
        import os
        api_key = self.settings.openai_api_key
        if not api_key:
            api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            click.echo("Error: OPENAI_API_KEY not set. Add it to .env or environment.", err=True)
            sys.exit(1)
        self.llm = OpenAIProvider(
            api_key=api_key,
            default_model=self.settings.llm.model,
        )

    async def init_async(self):
        """Initialize async components."""
        await self.memory.initialize()


@click.group()
@click.version_option(version="0.1.0", prog_name="agentgw")
def cli():
    """agentgw - Local AI Agent Framework"""
    pass


@cli.command()
@click.option("--skill", "-s", required=True, help="Skill to use")
@click.option("--model", "-m", default=None, help="Override LLM model")
def chat(skill: str, model: str | None):
    """Start an interactive chat session with an agent."""
    asyncio.run(_chat(skill, model))


async def _chat(skill_name: str, model_override: str | None):
    ctx = AppContext()
    await ctx.init_async()

    skill = ctx.skill_loader.load(skill_name)
    if skill is None:
        click.echo(f"Error: Skill '{skill_name}' not found.", err=True)
        click.echo(f"Available skills: {', '.join(s.name for s in ctx.skill_loader.list_skills())}", err=True)
        return

    if model_override:
        skill.model = model_override

    # Validate tools
    missing = ctx.tool_registry.validate_tool_names(skill.tools)
    if missing:
        click.echo(f"Warning: Skill '{skill_name}' references unknown tools: {missing}", err=True)

    session = Session.create(skill_name=skill_name)
    await ctx.memory.create_session(skill_name)

    click.echo(f"Chat session started with skill: {skill.name}")
    click.echo(f"Description: {skill.description.strip()}")
    click.echo("Type 'exit' or 'quit' to end the session.\n")

    agent = AgentLoop(
        skill=skill,
        llm=ctx.llm,
        tool_registry=ctx.tool_registry,
        memory=ctx.memory,
        session=session,
    )

    while True:
        try:
            user_input = click.prompt("You", prompt_suffix="> ")
        except (EOFError, KeyboardInterrupt):
            click.echo("\nGoodbye!")
            break

        if user_input.strip().lower() in ("exit", "quit"):
            click.echo("Goodbye!")
            break

        if not user_input.strip():
            continue

        click.echo("\nAgent> ", nl=False)
        async for chunk in agent.run(user_input):
            click.echo(chunk, nl=False)
        click.echo("\n")


@cli.command()
@click.argument("message")
@click.option("--skill", "-s", required=True, help="Skill to use")
@click.option("--model", "-m", default=None, help="Override LLM model")
def run(message: str, skill: str, model: str | None):
    """Run a single message through a skill and exit."""
    asyncio.run(_run(message, skill, model))


async def _run(message: str, skill_name: str, model_override: str | None):
    ctx = AppContext()
    await ctx.init_async()

    skill = ctx.skill_loader.load(skill_name)
    if skill is None:
        click.echo(f"Error: Skill '{skill_name}' not found.", err=True)
        return

    if model_override:
        skill.model = model_override

    session = Session.create(skill_name=skill_name)

    agent = AgentLoop(
        skill=skill,
        llm=ctx.llm,
        tool_registry=ctx.tool_registry,
        memory=ctx.memory,
        session=session,
    )

    async for chunk in agent.run(message):
        click.echo(chunk, nl=False)
    click.echo()


@cli.command("skills")
def list_skills():
    """List available skills."""
    ctx = AppContext(require_llm=False)
    skills = ctx.skill_loader.list_skills()
    if not skills:
        click.echo("No skills found.")
        return

    click.echo(f"{'Name':<25} {'Description'}")
    click.echo("-" * 70)
    for skill in skills:
        desc = skill.description.strip().split("\n")[0][:45]
        click.echo(f"{skill.name:<25} {desc}")


@cli.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--collection", "-c", default="default", help="ChromaDB collection name")
@click.option("--tags", "-t", multiple=True, help="Tags for the document")
@click.option("--chunk-size", default=512, help="Characters per chunk")
def ingest(file_path: str, collection: str, tags: tuple[str, ...], chunk_size: int):
    """Ingest a document into the RAG knowledge base."""
    asyncio.run(_ingest(file_path, collection, list(tags), chunk_size))


async def _ingest(file_path: str, collection: str, tags: list[str], chunk_size: int):
    ctx = AppContext(require_llm=False)
    text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    chunk_ids = await ctx.rag_store.ingest(
        text=text,
        metadata={"source": file_path, "tags": tags},
        collection=collection,
        chunk_size=chunk_size,
    )
    click.echo(f"Ingested {len(chunk_ids)} chunks from '{file_path}' into collection '{collection}'")
    if tags:
        click.echo(f"Tags: {', '.join(tags)}")


@cli.command("sessions")
def list_sessions():
    """List recent chat sessions."""
    asyncio.run(_list_sessions())


async def _list_sessions():
    ctx = AppContext()
    await ctx.init_async()
    sessions = await ctx.memory.get_sessions()
    if not sessions:
        click.echo("No sessions found.")
        return

    click.echo(f"{'ID':<38} {'Skill':<20} {'Updated'}")
    click.echo("-" * 80)
    for s in sessions:
        click.echo(f"{s['id']:<38} {s['skill_name'] or 'N/A':<20} {s['updated_at']}")
