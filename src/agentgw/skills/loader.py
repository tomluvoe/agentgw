"""Discover and load Agent Skills SKILL.md packs from configured roots."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from agentgw.harness.spec import SkillRecord
from agentgw.skills.frontmatter import FrontmatterError, split_frontmatter

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")
MAX_WALK_DEPTH = 6


def load_skill(path: Path) -> SkillRecord:
    """Load a single SKILL.md file."""
    text = path.read_text(encoding="utf-8")
    data, body = split_frontmatter(text)

    name = str(data.get("name") or path.parent.name).strip()
    description = str(data.get("description") or "").strip()
    if not name:
        raise FrontmatterError(f"{path}: missing name")
    if not NAME_RE.match(name) or len(name) > 64:
        raise FrontmatterError(
            f"{path}: name must be 1-64 chars of lowercase letters, digits, and hyphens"
        )
    if not description:
        raise FrontmatterError(f"{path}: missing description")
    if len(description) > 1024:
        raise FrontmatterError(f"{path}: description exceeds 1024 characters")

    dir_name = path.parent.name
    if dir_name != name:
        logger.warning("Skill name %r does not match directory %r (%s)", name, dir_name, path)

    metadata = _normalize_metadata(data.get("metadata"))
    allowed = _parse_allowed_tools(data.get("allowed-tools") or data.get("allowed_tools"))

    return SkillRecord(
        name=name,
        description=description,
        body=body.strip(),
        path=path.resolve(),
        directory=path.parent.resolve(),
        license=_opt_str(data.get("license")),
        compatibility=_opt_str(data.get("compatibility")),
        metadata=metadata,
        allowed_tools=tuple(allowed),
        user_invocable=_as_bool(data.get("user-invocable"), default=True),
        disable_model_invocation=_as_bool(
            data.get("disable-model-invocation"), default=False
        ),
    )


def discover_skills(roots: list[Path]) -> list[SkillRecord]:
    """Find SKILL.md files under each root. Later roots override earlier names."""
    by_name: dict[str, SkillRecord] = {}
    for root in roots:
        root = root.expanduser().resolve()
        if not root.is_dir():
            logger.debug("Skill root does not exist: %s", root)
            continue
        for skill_path in _iter_skill_files(root):
            try:
                skill = load_skill(skill_path)
            except (FrontmatterError, OSError, ValueError) as e:
                logger.warning("Skipping skill %s: %s", skill_path, e)
                continue
            by_name[skill.name] = skill
    return list(by_name.values())


def _iter_skill_files(root: Path):
    root = root.resolve()
    for path in root.rglob("SKILL.md"):
        try:
            rel = path.parent.resolve().relative_to(root)
        except ValueError:
            continue
        depth = len(rel.parts)
        if depth > MAX_WALK_DEPTH:
            continue
        yield path


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_allowed_tools(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [part for part in str(value).split() if part]


def _normalize_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {"raw": value}
    if isinstance(value, dict):
        return value
    return {}
