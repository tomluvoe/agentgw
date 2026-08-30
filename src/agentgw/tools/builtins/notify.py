"""Outbound notify: webhook URL, optional Telegram, optional Discord webhook."""

from __future__ import annotations

import os

import httpx

from agentgw.tools.decorator import tool


async def _post_json(url: str, payload: dict) -> int:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.status_code


async def deliver_notification(text: str) -> list[str]:
    """Send `text` to every configured sink. Returns sink names that succeeded."""
    sent: list[str] = []
    errors: list[str] = []

    webhook = os.environ.get("NOTIFY_WEBHOOK_URL") or ""
    if webhook.strip():
        try:
            await _post_json(webhook.strip(), {"text": text, "content": text})
            sent.append("webhook")
        except Exception as e:
            errors.append(f"webhook: {e}")

    discord_url = os.environ.get("DISCORD_WEBHOOK_URL") or ""
    if discord_url.strip():
        try:
            await _post_json(discord_url.strip(), {"content": text})
            sent.append("discord")
        except Exception as e:
            errors.append(f"discord: {e}")

    token = os.environ.get("TELEGRAM_BOT_TOKEN") or ""
    chat_id = os.environ.get("NOTIFY_CHAT_ID") or ""
    if token.strip() and chat_id.strip():
        try:
            await _post_json(
                f"https://api.telegram.org/bot{token.strip()}/sendMessage",
                {"chat_id": chat_id.strip(), "text": text},
            )
            sent.append("telegram")
        except Exception as e:
            errors.append(f"telegram: {e}")

    if sent:
        return sent
    if errors:
        return [f"error: {'; '.join(errors)}"]
    return [
        "error: no notify sink configured "
        "(NOTIFY_WEBHOOK_URL, DISCORD_WEBHOOK_URL, or TELEGRAM_BOT_TOKEN+NOTIFY_CHAT_ID)"
    ]


@tool()
async def notify(text: str) -> str:
    """Send a short notification to the operator.

    Uses env sinks, not the chat you are in: NOTIFY_WEBHOOK_URL,
    DISCORD_WEBHOOK_URL, and/or TELEGRAM_BOT_TOKEN + NOTIFY_CHAT_ID.

    Args:
        text: Message to deliver.
    """
    result = await deliver_notification(text)
    if result and result[0].startswith("error:"):
        return result[0]
    return "sent via " + ", ".join(result)
