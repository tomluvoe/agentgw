"""Telegram channel. One chat id maps to one session: telegram-{chat_id}."""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.harness.run import Harness

SendFn = Callable[[str, str], Awaitable[str]]


def session_key(chat_id: str) -> str:
    return f"telegram-{chat_id}"


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


async def handle_telegram_content(chat_id: str, text: str, send: SendFn) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    return await send(session_key(chat_id), text)


async def handle_telegram_message(
    harness: Harness, sessions: SessionMap, chat_id: str, text: str
) -> str:
    return await handle_telegram_content(chat_id, text, _harness_send(harness, sessions))


async def handle_telegram_remote(client: Any, chat_id: str, text: str) -> str:
    async def send(key: str, msg: str) -> str:
        data = await client.chat(msg, session_id=key)
        return data.get("response") or ""

    return await handle_telegram_content(chat_id, text, send)


def _require_token(token: str | None) -> str:
    token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    return token


def _require_telegram():
    try:
        from telegram.ext import Application, MessageHandler, filters
    except ImportError as e:
        raise RuntimeError(
            "Install the telegram extra: uv sync --extra telegram"
        ) from e
    return Application, MessageHandler, filters


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


def _build_application(send: SendFn, token: str):
    Application, MessageHandler, filters = _require_telegram()

    async def on_text(update, context) -> None:
        if update.message is None or update.effective_chat is None:
            return
        reply = await handle_telegram_content(
            str(update.effective_chat.id),
            update.message.text or "",
            send,
        )
        if reply:
            await update.message.reply_text(reply)

    app = Application.builder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    return app


def run_telegram(
    harness: Harness | None = None,
    token: str | None = None,
    *,
    sessions: SessionMap | None = None,
    url: str | None = None,
) -> None:
    token = _require_token(token)
    app = _build_application(_resolve_send(harness, sessions, url), token)
    print("Telegram polling")
    app.run_polling()


async def attach_telegram(
    harness: Harness, sessions: SessionMap, token: str | None = None
):
    """Start Telegram polling on the current asyncio loop. Returns the Application."""
    token = _require_token(token)
    app = _build_application(_harness_send(harness, sessions), token)
    await app.initialize()
    await app.start()
    if app.updater is None:
        raise RuntimeError("Telegram updater is not available")
    await app.updater.start_polling(drop_pending_updates=True)
    return app
