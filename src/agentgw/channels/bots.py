"""Optional Discord/Telegram adapters started by `agentgw serve`."""

from __future__ import annotations

import asyncio
import logging
import os

from agentgw.channels.sessions import SessionMap
from agentgw.harness.run import Harness

logger = logging.getLogger(__name__)


class ChannelBots:
    """Start Discord/Telegram on the daemon event loop when tokens are set."""

    def __init__(self, harness: Harness, sessions: SessionMap) -> None:
        self.harness = harness
        self.sessions = sessions
        self._discord = None
        self._discord_task: asyncio.Task | None = None
        self._telegram = None
        self.started: list[str] = []

    async def start(self) -> list[str]:
        discord_token = (os.environ.get("DISCORD_BOT_TOKEN") or "").strip()
        if discord_token:
            try:
                from agentgw.channels.discord import attach_discord

                bot, task = await attach_discord(
                    self.harness, self.sessions, discord_token
                )
                self._discord = bot
                self._discord_task = task
                task.add_done_callback(self._log_task_error)
                self.started.append("discord")
            except Exception:
                logger.exception("Discord adapter failed to start")

        telegram_token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if telegram_token:
            try:
                from agentgw.channels.telegram import attach_telegram

                self._telegram = await attach_telegram(
                    self.harness, self.sessions, telegram_token
                )
                self.started.append("telegram")
            except Exception:
                logger.exception("Telegram adapter failed to start")

        return list(self.started)

    def _log_task_error(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Channel adapter stopped: %s", exc)

    async def stop(self) -> None:
        if self._telegram is not None:
            app = self._telegram
            try:
                updater = getattr(app, "updater", None)
                if updater is not None and getattr(updater, "running", False):
                    await updater.stop()
                if getattr(app, "running", False):
                    await app.stop()
                await app.shutdown()
            except Exception:
                logger.exception("Telegram adapter failed to stop")
            self._telegram = None

        if self._discord is not None:
            try:
                await self._discord.close()
            except Exception:
                logger.exception("Discord adapter failed to stop")
            if self._discord_task is not None:
                try:
                    await asyncio.wait_for(self._discord_task, timeout=5)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    self._discord_task.cancel()
                except Exception:
                    pass
            self._discord = None
            self._discord_task = None
