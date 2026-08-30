"""Named inbound webhooks. A hook turns a JSON body into a user message."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from agentgw.channels.sessions import SessionMap, handle_inbound
from agentgw.harness.run import Harness

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = (
    "Webhook `{name}` received. JSON payload:\n{payload}\n\n"
    "If this matches something in memory/WATCH.md, act. "
    "Otherwise acknowledge briefly."
)


@dataclass
class Hook:
    name: str
    session: str
    template: str = DEFAULT_TEMPLATE
    enabled: bool = True

    def render(self, payload: Any) -> str:
        body = json.dumps(payload, default=str, indent=2)
        return (
            self.template.replace("{name}", self.name).replace("{payload}", body)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "session": self.session,
            "enabled": self.enabled,
            "template": self.template,
        }


def load_hooks(path: Path) -> list[Hook]:
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("hooks") or []
    hooks: list[Hook] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("name"):
            logger.warning("Skipping invalid hook entry: %s", item)
            continue
        name = str(item["name"])
        hooks.append(
            Hook(
                name=name,
                session=str(item.get("session") or f"hook-{name}"),
                template=str(item.get("template") or DEFAULT_TEMPLATE).strip(),
                enabled=bool(item.get("enabled", True)),
            )
        )
    return hooks


class HookRunner:
    def __init__(self, harness: Harness, sessions: SessionMap, hooks: list[Hook]):
        self.harness = harness
        self.sessions = sessions
        self.hooks = {hook.name: hook for hook in hooks}

    def list_hooks(self) -> list[dict[str, Any]]:
        return [hook.as_dict() for hook in self.hooks.values()]

    async def run(self, name: str, payload: Any) -> dict[str, Any]:
        hook = self.hooks.get(name)
        if hook is None:
            raise KeyError(name)
        if not hook.enabled:
            raise PermissionError(name)
        message = hook.render(payload)
        reply, session = await handle_inbound(
            self.harness, self.sessions, hook.session, message
        )
        return {
            "hook": hook.name,
            "session_id": session.id,
            "response": reply,
        }
