"""Load an agent package: AGENT.md + referenced skill roots and tool modules."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentgw.harness.spec import SkillRecord, ToolPolicy
from agentgw.harness.workspace import Workspace
from agentgw.skills.frontmatter import FrontmatterError, split_frontmatter
from agentgw.skills.gate import is_eligible
from agentgw.skills.loader import discover_skills
from agentgw.tools.registry import ToolRegistry, reset_builtin_tools

logger = logging.getLogger(__name__)

DEFAULT_TOOLS = ("read", "write", "list_dir", "exec")


@dataclass
class AgentPackage:
    """An agent definition plus the skills/tools it includes."""

    path: Path
    name: str
    description: str
    system_prompt: str
    model: str | None = None
    provider: str | None = None
    temperature: float = 0.7
    max_iterations: int = 10
    workspace: Path = field(default_factory=Path.cwd)
    skills: list[SkillRecord] = field(default_factory=list)
    skill_always: list[str] = field(default_factory=list)
    skill_allow: list[str] | None = None
    max_activated: int = 3
    tool_policy: ToolPolicy = field(default_factory=lambda: ToolPolicy(allow=DEFAULT_TOOLS))
    tool_modules: list[str] = field(default_factory=list)
    registry: ToolRegistry = field(default_factory=ToolRegistry)

    @property
    def directory(self) -> Path:
        return self.path.parent


def load_package(
    agent_path: Path,
    *,
    workspace_override: Path | None = None,
    extra_skill_roots: list[Path] | None = None,
) -> AgentPackage:
    """Load AGENT.md and resolve skill/tool includes."""
    agent_path = agent_path.expanduser().resolve()
    if agent_path.is_dir():
        agent_path = agent_path / "AGENT.md"
    if not agent_path.is_file():
        raise FileNotFoundError(f"AGENT.md not found: {agent_path}")

    data, body = split_frontmatter(agent_path.read_text(encoding="utf-8"))
    directory = agent_path.parent
    name = str(data.get("name") or directory.name).strip()
    description = str(data.get("description") or "").strip()
    if not name:
        raise FrontmatterError(f"{agent_path}: missing name")
    if not description:
        raise FrontmatterError(f"{agent_path}: missing description")

    skills_cfg = data.get("skills") or {}
    tools_cfg = data.get("tools") or {}
    if not isinstance(skills_cfg, dict):
        raise FrontmatterError("skills: must be a mapping")
    if not isinstance(tools_cfg, dict):
        raise FrontmatterError("tools: must be a mapping")

    workspace_raw = data.get("workspace", ".")
    workspace = (
        workspace_override.expanduser().resolve()
        if workspace_override
        else _resolve_from(directory, str(workspace_raw))
    )
    Workspace(workspace)  # ensure exists

    roots = _skill_roots(directory, skills_cfg, extra_skill_roots)
    discovered = discover_skills(roots)
    allow_names = _str_list(skills_cfg.get("allow"))
    if allow_names:
        allow_set = set(allow_names)
        discovered = [s for s in discovered if s.name in allow_set]
    eligible = [s for s in discovered if is_eligible(s)]

    policy = ToolPolicy(
        allow=tuple(_str_list(tools_cfg.get("allow")) or list(DEFAULT_TOOLS)),
        deny=tuple(_str_list(tools_cfg.get("deny"))),
    )

    registry = _build_registry(directory, tools_cfg)

    return AgentPackage(
        path=agent_path,
        name=name,
        description=description,
        system_prompt=body.strip(),
        model=_opt_str(data.get("model")),
        provider=_opt_str(data.get("provider")),
        temperature=float(data.get("temperature", 0.7)),
        max_iterations=int(data.get("max_iterations", 10)),
        workspace=workspace,
        skills=eligible,
        skill_always=_str_list(skills_cfg.get("always")),
        skill_allow=allow_names or None,
        max_activated=int(skills_cfg.get("max_activated", 3)),
        tool_policy=policy,
        tool_modules=_str_list(tools_cfg.get("modules")),
        registry=registry,
    )


def _skill_roots(
    directory: Path,
    skills_cfg: dict[str, Any],
    extra: list[Path] | None,
) -> list[Path]:
    """Roots come from config. Agent-local skills/ is included only if listed or present as default.

    Default: the agent's own skills/ directory if it exists, plus any extra roots.
    Shared packs must be listed under skills.roots — they are not inferred.
    """
    roots: list[Path] = []
    configured = skills_cfg.get("roots")
    if configured is None:
        local = directory / "skills"
        if local.is_dir():
            roots.append(local)
    else:
        for raw in _str_list(configured):
            roots.append(_resolve_from(directory, raw))
    for path in extra or []:
        roots.append(path.expanduser().resolve())
    return roots


def _build_registry(directory: Path, tools_cfg: dict[str, Any]) -> ToolRegistry:
    reset_builtin_tools()
    registry = ToolRegistry()
    registry.collect_registered()

    for raw in _str_list(tools_cfg.get("modules")):
        looks_like_module = (
            not Path(raw).is_absolute()
            and not raw.startswith(".")
            and "/" not in raw
            and "\\" not in raw
        )
        if looks_like_module:
            try:
                registry.load_module(raw)
            except Exception:
                logger.exception("Failed to import tool module %s", raw)
            continue
        registry.load_path(_resolve_from(directory, raw))
    return registry


def _resolve_from(directory: Path, raw: str) -> Path:
    p = Path(raw).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (directory / p).resolve()


def _str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
