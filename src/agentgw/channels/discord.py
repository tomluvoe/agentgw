"""Discord channel. Mentions in guilds; all DMs."""

from __future__ import annotations

import os
import re

from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.harness.run import Harness

_MENTION = re.compile(r"<@!?\d+>\s*")


def _visible_text(content: str) -> str:
    return _MENTION.sub("", content).strip()


async def handle_discord_message(harness: Harness, sessions: SessionMap, channel_id: str, content: str) -> str:
    text = _visible_text(content)
    if not text:
        return ""
    reply, _ = await handle_inbound(harness, sessions, f"discord:{channel_id}", text)
    return reply[:2000]


def run_discord(harness: Harness, token: str | None = None) -> None:
    try:
        import discord
    except ImportError as e:
        raise RuntimeError("Install the discord extra: uv sync --extra discord") from e

    token = token or os.environ.get("DISCORD_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("DISCORD_BOT_TOKEN is not set")

    intents = discord.Intents.default()
    intents.message_content = True
    bot = discord.Client(intents=intents)
    sessions = SessionMap()

    @bot.event
    async def on_ready():
        print(f"Discord connected as {bot.user} (agent={harness.package.name})")

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        in_dm = message.guild is None
        mentioned = bot.user is not None and bot.user.mentioned_in(message)
        if not in_dm and not mentioned:
            return
        reply = await handle_discord_message(
            harness, sessions, str(message.channel.id), message.content
        )
        if reply:
            await message.channel.send(reply)

    bot.run(token)
