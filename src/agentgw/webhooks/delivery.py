"""Webhook delivery system for agent events."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class WebhookEvent(str, Enum):
    """Types of webhook events."""
    AGENT_STARTED = "agent.started"
    AGENT_COMPLETED = "agent.completed"
    AGENT_FAILED = "agent.failed"
    TOOL_EXECUTED = "tool.executed"
    SESSION_CREATED = "session.created"
    FEEDBACK_RECEIVED = "feedback.received"


class Webhook:
    """A webhook configuration."""

    def __init__(
        self,
        name: str,
        url: str,
        events: list[WebhookEvent],
        secret: str | None = None,
        enabled: bool = True,
    ):
        self.name = name
        self.url = url
        self.events = events
        self.secret = secret
        self.enabled = enabled


class WebhookDelivery:
    """Handles webhook delivery with retries."""

    def __init__(self, max_retries: int = 3, timeout: int = 30):
        self._max_retries = max_retries
        self._timeout = timeout
        self._webhooks: dict[str, Webhook] = {}

    def register(self, webhook: Webhook) -> None:
        """Register a webhook."""
        self._webhooks[webhook.name] = webhook
        logger.info("Registered webhook '%s' for events: %s", webhook.name, webhook.events)

    def unregister(self, name: str) -> bool:
        """Unregister a webhook."""
        if name in self._webhooks:
            del self._webhooks[name]
            logger.info("Unregistered webhook '%s'", name)
            return True
        return False

    async def send_event(
        self,
        event: WebhookEvent,
        payload: dict[str, Any],
    ) -> None:
        """Send an event to all registered webhooks (non-blocking)."""
        # Fire and forget - don't block agent execution
        asyncio.create_task(self._deliver_event(event, payload))

    async def _deliver_event(
        self,
        event: WebhookEvent,
        payload: dict[str, Any],
    ) -> None:
        """Deliver event to registered webhooks."""
        # Find webhooks subscribed to this event
        targets = [
            wh for wh in self._webhooks.values()
            if wh.enabled and event in wh.events
        ]

        if not targets:
            return

        # Build webhook payload
        webhook_payload = {
            "event": event.value,
            "timestamp": datetime.now().isoformat(),
            "data": payload,
        }

        # Deliver to each webhook
        tasks = [
            self._deliver_to_webhook(wh, webhook_payload)
            for wh in targets
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _deliver_to_webhook(
        self,
        webhook: Webhook,
        payload: dict[str, Any],
    ) -> None:
        """Deliver payload to a single webhook with retries."""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "agentgw-webhook/1.0",
        }

        if webhook.secret:
            # Add signature header (simple HMAC could be added here)
            headers["X-Webhook-Secret"] = webhook.secret

        for attempt in range(self._max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        webhook.url,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self._timeout),
                    ) as response:
                        if response.status >= 200 and response.status < 300:
                            logger.info(
                                "Webhook '%s' delivered successfully (status=%d)",
                                webhook.name,
                                response.status,
                            )
                            return
                        else:
                            logger.warning(
                                "Webhook '%s' returned status %d (attempt %d/%d)",
                                webhook.name,
                                response.status,
                                attempt + 1,
                                self._max_retries,
                            )
            except Exception as e:
                logger.warning(
                    "Webhook '%s' delivery failed: %s (attempt %d/%d)",
                    webhook.name,
                    e,
                    attempt + 1,
                    self._max_retries,
                )

            # Wait before retry (exponential backoff)
            if attempt < self._max_retries - 1:
                await asyncio.sleep(2 ** attempt)

        logger.error("Webhook '%s' delivery failed after %d attempts", webhook.name, self._max_retries)
