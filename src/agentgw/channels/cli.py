"""CLI and channel entry points.

`agentgw serve` is the long-running agent process. Other commands talk to it
when `--url` / `AGENTGW_URL` is set; otherwise they load the agent in-process.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click

from agentgw.agent.package import load_package
from agentgw.harness.run import Harness
from agentgw.llm.factory import create_llm


@click.group()
@click.version_option(version="0.2.0", prog_name="agentgw")
@click.option(
    "--url",
    envvar="AGENTGW_URL",
    default=None,
    help="URL of a running agentgw daemon (or set AGENTGW_URL).",
)
@click.pass_context
def cli(ctx: click.Context, url: str | None):
    """agentgw — agent harness with SKILL.md packs and tools."""
    ctx.ensure_object(dict)
    ctx.obj["url"] = url


@cli.command()
@click.option("--agent", "-a", "agent_path", default=None, type=click.Path(path_type=Path))
@click.option("--workspace", "-w", default=None, type=click.Path(path_type=Path))
@click.option("--provider", default=None, help="Override LLM provider (openai, anthropic, xai)")
@click.option("--model", "-m", default=None, help="Override LLM model")
@click.option("--session", "session_id", default=None, help="Resume a daemon session id")
@click.pass_context
def chat(
    ctx: click.Context,
    agent_path: Path | None,
    workspace: Path | None,
    provider: str | None,
    model: str | None,
    session_id: str | None,
):
    """Interactive chat. Uses the daemon when --url / AGENTGW_URL is set."""
    asyncio.run(_chat(ctx.obj.get("url"), agent_path, workspace, provider, model, session_id))


@cli.command()
@click.option("--agent", "-a", "agent_path", default=None, type=click.Path(path_type=Path))
@click.option("--workspace", "-w", default=None, type=click.Path(path_type=Path))
@click.option("--provider", default=None, help="Override LLM provider (openai, anthropic, xai)")
@click.option("--model", "-m", default=None)
@click.option("--session", "session_id", default=None)
@click.argument("message")
@click.pass_context
def run(
    ctx: click.Context,
    agent_path: Path | None,
    workspace: Path | None,
    provider: str | None,
    model: str | None,
    session_id: str | None,
    message: str,
):
    """Single-shot run. Prints the agent response."""
    asyncio.run(
        _run_once(ctx.obj.get("url"), agent_path, workspace, provider, model, session_id, message)
    )


@cli.command("skills")
@click.option("--agent", "-a", "agent_path", default=None, type=click.Path(path_type=Path))
@click.pass_context
def list_skills(ctx: click.Context, agent_path: Path | None):
    """List eligible skills for an agent or a running daemon."""
    url = ctx.obj.get("url")
    if url:
        asyncio.run(_remote_skills(url))
        return
    pkg = load_package(_require_agent(agent_path))
    if not pkg.skills:
        click.echo("No eligible skills.")
        return
    click.echo(f"{'NAME':<24} {'PATH'}")
    for skill in pkg.skills:
        click.echo(f"{skill.name:<24} {skill.path}")


@cli.command("tools")
@click.option("--agent", "-a", "agent_path", default=None, type=click.Path(path_type=Path))
@click.pass_context
def list_tools(ctx: click.Context, agent_path: Path | None):
    """List tools the agent is allowed to call."""
    url = ctx.obj.get("url")
    if url:
        asyncio.run(_remote_tools(url))
        return
    pkg = load_package(_require_agent(agent_path))
    names = pkg.tool_policy.filter(pkg.registry.names())
    for name in names:
        click.echo(name)


@cli.command()
@click.option("--agent", "-a", "agent_path", required=True, type=click.Path(path_type=Path))
@click.option("--workspace", "-w", default=None, type=click.Path(path_type=Path))
@click.option("--provider", default=None)
@click.option("--model", "-m", default=None)
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8080, type=int)
def serve(
    agent_path: Path,
    workspace: Path | None,
    provider: str | None,
    model: str | None,
    host: str,
    port: int,
):
    """Run the agent as a long-lived daemon with a REST API."""
    from agentgw.channels.http import serve as http_serve

    harness = _harness(agent_path, workspace, model, provider)
    try:
        http_serve(harness, host=host, port=port)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--agent", "-a", "agent_path", required=True, type=click.Path(path_type=Path))
@click.option("--workspace", "-w", default=None, type=click.Path(path_type=Path))
@click.option("--provider", default=None)
@click.option("--model", "-m", default=None)
def discord(agent_path: Path, workspace: Path | None, provider: str | None, model: str | None):
    """Run the agent as a Discord bot (DISCORD_BOT_TOKEN)."""
    from agentgw.channels.discord import run_discord

    harness = _harness(agent_path, workspace, model, provider)
    try:
        run_discord(harness)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--agent", "-a", "agent_path", required=True, type=click.Path(path_type=Path))
@click.option("--workspace", "-w", default=None, type=click.Path(path_type=Path))
@click.option("--provider", default=None)
@click.option("--model", "-m", default=None)
def telegram(agent_path: Path, workspace: Path | None, provider: str | None, model: str | None):
    """Run the agent as a Telegram bot (TELEGRAM_BOT_TOKEN)."""
    from agentgw.channels.telegram import run_telegram

    harness = _harness(agent_path, workspace, model, provider)
    try:
        run_telegram(harness)
    except RuntimeError as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


def _require_agent(agent_path: Path | None) -> Path:
    if agent_path is None:
        click.echo("Error: --agent is required unless --url / AGENTGW_URL points at a daemon.", err=True)
        sys.exit(1)
    return agent_path


def _harness(
    agent_path: Path,
    workspace: Path | None,
    model: str | None,
    provider: str | None = None,
) -> Harness:
    pkg = load_package(agent_path, workspace_override=workspace)
    try:
        llm = create_llm(provider=provider or pkg.provider, model=model or pkg.model)
    except (RuntimeError, ValueError) as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    return Harness(pkg, llm)


async def _remote_skills(url: str) -> None:
    from agentgw.channels.client import AgentClient

    skills = await AgentClient(url).skills()
    if not skills:
        click.echo("No eligible skills.")
        return
    click.echo(f"{'NAME':<24} {'PATH'}")
    for skill in skills:
        click.echo(f"{skill['name']:<24} {skill.get('path', '')}")


async def _remote_tools(url: str) -> None:
    from agentgw.channels.client import AgentClient

    for name in await AgentClient(url).tools():
        click.echo(name)


async def _chat(
    url: str | None,
    agent_path: Path | None,
    workspace: Path | None,
    provider: str | None,
    model: str | None,
    session_id: str | None,
):
    if url:
        await _remote_chat(url, session_id)
        return
    from agentgw.harness.session import Session

    harness = _harness(_require_agent(agent_path), workspace, model, provider)
    session = Session.create(harness.package.name)
    click.echo(f"Agent: {harness.package.name}")
    click.echo(f"Workspace: {harness.package.workspace}")
    click.echo(f"Skills: {', '.join(s.name for s in harness.package.skills) or '(none)'}")
    click.echo("Type exit or quit to stop.\n")

    while True:
        try:
            user_input = click.prompt("You", prompt_suffix="> ")
        except (EOFError, KeyboardInterrupt):
            click.echo("\nGoodbye!")
            break
        stripped = user_input.strip()
        if stripped.lower() in {"exit", "quit"}:
            click.echo("Goodbye!")
            break
        if not stripped:
            continue
        click.echo("\nAgent> ", nl=False)
        async for chunk in harness.run(stripped, session=session):
            click.echo(chunk, nl=False)
        click.echo("\n")


async def _remote_chat(url: str, session_id: str | None) -> None:
    from agentgw.channels.client import AgentClient

    client = AgentClient(url)
    health = await client.health()
    click.echo(f"Daemon: {url}  agent={health.get('agent')}")
    if session_id:
        click.echo(f"Session: {session_id}")
    click.echo("Type exit or quit to stop.\n")
    while True:
        try:
            user_input = click.prompt("You", prompt_suffix="> ")
        except (EOFError, KeyboardInterrupt):
            click.echo("\nGoodbye!")
            break
        stripped = user_input.strip()
        if stripped.lower() in {"exit", "quit"}:
            click.echo("Goodbye!")
            break
        if not stripped:
            continue
        data = await client.chat(stripped, session_id=session_id)
        session_id = data["session_id"]
        click.echo(f"\nAgent> {data['response']}\n")


async def _run_once(
    url: str | None,
    agent_path: Path | None,
    workspace: Path | None,
    provider: str | None,
    model: str | None,
    session_id: str | None,
    message: str,
):
    if url:
        from agentgw.channels.client import AgentClient

        data = await AgentClient(url).chat(message, session_id=session_id)
        click.echo(data["response"])
        click.echo(f"[session {data['session_id']}]", err=True)
        return
    harness = _harness(_require_agent(agent_path), workspace, model, provider)
    async for chunk in harness.run(message):
        click.echo(chunk, nl=False)
    click.echo()
