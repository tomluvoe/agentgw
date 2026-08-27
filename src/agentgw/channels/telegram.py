"""Telegram channel. One chat id maps to one session."""

from __future__ import annotations

import os

from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.harness.run import Harness


async def handle_telegram_message(
    harness: Harness, sessions: SessionMap, chat_id: str, text: str
) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    reply, _ = await handle_inbound(harness, sessions, f"telegram:{chat_id}", text)
    return reply


def run_telegram(harness: Harness, token: str | None = None) -> None:
    try:
        from telegram.ext import Application, MessageHandler, filters
    except ImportError as e:
        raise RuntimeError(
            "Install the telegram extra: uv sync --extra telegram"
        ) from e

    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    sessions = SessionMap()

    async def on_text(update, context) -> None:
        if update.message is None or update.effective_chat is None:
            return
        reply = await handle_telegram_message(
            harness,
            sessions,
            str(update.effective_chat.id),
            update.message.text or "",
        )
        if reply:
            await update.message.reply_text(reply)

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    print(f"Telegram polling (agent={harness.package.name})")
    app.run_polling()
