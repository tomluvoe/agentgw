"""Load webhook configurations from YAML."""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from agentgw.webhooks.delivery import Webhook, WebhookDelivery, WebhookEvent

logger = logging.getLogger(__name__)


def load_webhooks_from_config(
    config_path: Path,
    webhook_delivery: WebhookDelivery,
) -> None:
    """Load webhooks from a YAML config file and register them.

    Args:
        config_path: Path to webhooks.yaml
        webhook_delivery: WebhookDelivery instance to register webhooks with
    """
    if not config_path.exists():
        logger.warning("Webhook config not found: %s", config_path)
        return

    try:
        with open(config_path) as f:
            data = yaml.safe_load(f)
    except Exception as e:
        logger.error("Failed to load webhook config: %s", e)
        return

    if not data or "webhooks" not in data:
        logger.info("No webhooks configured")
        return

    for webhook_config in data["webhooks"]:
        try:
            # Convert string event names to WebhookEvent enums
            events = [WebhookEvent(e) for e in webhook_config.get("events", [])]

            webhook = Webhook(
                name=webhook_config["name"],
                url=webhook_config["url"],
                events=events,
                secret=webhook_config.get("secret"),
                enabled=webhook_config.get("enabled", True),
            )
            webhook_delivery.register(webhook)
        except Exception as e:
            logger.error("Failed to register webhook '%s': %s", webhook_config.get("name", "?"), e)
