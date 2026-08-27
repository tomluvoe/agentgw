"""Immutable types for a compiled agent run."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SkillRecord:
    """A loaded SKILL.md pack."""

    name: str
    description: str
    body: str
    path: Path
    directory: Path
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    allowed_tools: tuple[str, ...] = ()
    user_invocable: bool = True
    disable_model_invocation: bool = False


@dataclass(frozen=True)
class ToolPolicy:
    """Which tools the model may see and call this run."""

    allow: tuple[str, ...]
    deny: tuple[str, ...] = ()

    def permits(self, name: str) -> bool:
        if name in self.deny:
            return False
        if not self.allow:
            return False
        if "*" in self.allow:
            return True
        return name in self.allow

    def filter(self, names: list[str]) -> list[str]:
        return [n for n in names if self.permits(n)]


@dataclass
class RunContext:
    """Per-run capabilities injected into tool calls. Not sent to the model."""

    workspace: Path
    skill_dirs: dict[str, Path] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class AgentSpec:
    """Everything the loop needs for one turn. Compiled, then frozen in practice."""

    name: str
    description: str
    system_prompt: str
    model: str | None
    provider: str | None
    temperature: float
    max_iterations: int
    tool_policy: ToolPolicy
    activated_skills: tuple[SkillRecord, ...]
    catalog_skills: tuple[SkillRecord, ...]
    workspace: Path
    context: RunContext
