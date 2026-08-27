"""CLI and channel entry points."""

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
def cli():
    """agentgw — agent harness with SKILL.md packs and tools."""


@cli.command()
@click.option("--agent", "-a", "agent_path", required=True, type=click.Path(path_type=Path))
@click.option("--workspace", "-w", default=None, type=click.Path(path_type=Path))
@click.option("--provider", default=None, help="Override LLM provider (openai, anthropic, xai)")
@click.option("--model", "-m", default=None, help="Override LLM model")
def chat(agent_path: Path, workspace: Path | None, provider: str | None, model: str | None):
    """Interactive chat with an agent package."""
    asyncio.run(_chat(agent_path, workspace, provider, model))


@cli.command()
@click.option("--agent", "-a", "agent_path", required=True, type=click.Path(path_type=Path))
@click.option("--workspace", "-w", default=None, type=click.Path(path_type=Path))
@click.option("--provider", default=None, help="Override LLM provider (openai, anthropic, xai)")
@click.option("--model", "-m", default=None)
@click.argument("message")
def run(
    agent_path: Path,
    workspace: Path | None,
    provider: str | None,
    model: str | None,
    message: str,
):
    """Single-shot run. Prints the agent response."""
    asyncio.run(_run_once(agent_path, workspace, provider, model, message))


@cli.command("skills")
@click.option("--agent", "-a", "agent_path", required=True, type=click.Path(path_type=Path))
def list_skills(agent_path: Path):
    """List eligible skills for an agent."""
    pkg = load_package(agent_path)
    if not pkg.skills:
        click.echo("No eligible skills.")
        return
    click.echo(f"{'NAME':<24} {'PATH'}")
    for skill in pkg.skills:
        click.echo(f"{skill.name:<24} {skill.path}")


@cli.command("tools")
@click.option("--agent", "-a", "agent_path", required=True, type=click.Path(path_type=Path))
def list_tools(agent_path: Path):
    """List tools the agent is allowed to call."""
    pkg = load_package(agent_path)
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
    """Serve the agent over HTTP (REST)."""
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


async def _chat(
    agent_path: Path,
    workspace: Path | None,
    provider: str | None,
    model: str | None,
):
    from agentgw.harness.session import Session

    harness = _harness(agent_path, workspace, model, provider)
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


async def _run_once(
    agent_path: Path,
    workspace: Path | None,
    provider: str | None,
    model: str | None,
    message: str,
):
    harness = _harness(agent_path, workspace, model, provider)
    async for chunk in harness.run(message):
        click.echo(chunk, nl=False)
    click.echo()
