"""YAML frontmatter parsing for SKILL.md and AGENT.md."""

from __future__ import annotations

from typing import Any

import yaml


class FrontmatterError(ValueError):
    pass


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Return (frontmatter, body). Requires a leading YAML --- block."""
    if not text.startswith("---"):
        raise FrontmatterError("File must start with YAML frontmatter delimited by ---")

    rest = text[3:]
    if rest.startswith("\n"):
        rest = rest[1:]
    end = rest.find("\n---")
    if end == -1:
        raise FrontmatterError("Frontmatter closing --- not found")

    raw_fm = rest[:end]
    body = rest[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]

    data = yaml.safe_load(raw_fm) or {}
    if not isinstance(data, dict):
        raise FrontmatterError("Frontmatter must be a YAML mapping")
    return data, body
