"""Discord channel. Mentions in guilds; all DMs. Session key: discord-{channel_id}."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Awaitable, Callable
from typing import Any

from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.harness.run import Harness

_MENTION = re.compile(r"<@!?\d+>\s*")

SendFn = Callable[[str, str], Awaitable[str]]


def session_key(channel_id: str) -> str:
    return f"discord-{channel_id}"


def _visible_text(content: str) -> str:
    return _MENTION.sub("", content).strip()


def _harness_send(harness: Harness, sessions: SessionMap) -> SendFn:
    async def send(key: str, text: str) -> str:
        reply, _ = await handle_inbound(harness, sessions, key, text)
        return reply

    return send


def _remote_send(url: str) -> SendFn:
    from agentgw.channels.client import AgentClient

    client = AgentClient(url)

    async def send(key: str, text: str) -> str:
        data = await client.chat(text, session_id=key)
        return data.get("response") or ""

    return send


async def handle_discord_content(channel_id: str, content: str, send: SendFn) -> str:
    text = _visible_text(content)
    if not text:
        return ""
    reply = await send(session_key(channel_id), text)
    return reply[:2000]


async def handle_discord_message(
    harness: Harness, sessions: SessionMap, channel_id: str, content: str
) -> str:
    return await handle_discord_content(
        channel_id, content, _harness_send(harness, sessions)
    )


async def handle_discord_remote(client: Any, channel_id: str, content: str) -> str:
    async def send(key: str, text: str) -> str:
        data = await client.chat(text, session_id=key)
        return data.get("response") or ""

    return await handle_discord_content(channel_id, content, send)


def _build_client(send: SendFn):
    import discord

    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)

    @bot.event
    async def on_ready():
        print(f"Discord connected as {bot.user}")

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        in_dm = message.guild is None
        mentioned = bot.user is not None and bot.user.mentioned_in(message)
        if not in_dm and not mentioned:
            return
        reply = await handle_discord_content(
            str(message.channel.id), message.content, send
        )
        if reply:
            await message.channel.send(reply)

    return bot


def _require_token(token: str | None) -> str:
    token = token or os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set")
    return token


def _require_discord() -> None:
    try:
        import discord  # noqa: F401
    except ImportError as e:
        raise RuntimeError("Install the discord extra: uv sync --extra discord") from e


def _resolve_send(
    harness: Harness | None, sessions: SessionMap | None, url: str | None
) -> SendFn:
    if url:
        return _remote_send(url)
    if harness is None:
        raise RuntimeError("Pass a harness or --url / AGENTGW_URL")
    if sessions is None:
        from agentgw.channels.store import SessionStore

        store = SessionStore(harness.package.workspace / ".agentgw" / "sessions")
        sessions = SessionMap(store)
    return _harness_send(harness, sessions)


def run_discord(
    harness: Harness | None = None,
    token: str | None = None,
    *,
    sessions: SessionMap | None = None,
    url: str | None = None,
) -> None:
    _require_discord()
    token = _require_token(token)
    bot = _build_client(_resolve_send(harness, sessions, url))
    bot.run(token)


async def attach_discord(
    harness: Harness, sessions: SessionMap, token: str | None = None
):
    """Start Discord on the current asyncio loop. Returns (client, task)."""
    _require_discord()
    token = _require_token(token)
    bot = _build_client(_harness_send(harness, sessions))
    task = asyncio.create_task(bot.start(token), name="agentgw-discord")
    return bot, task
