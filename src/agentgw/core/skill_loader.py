"""Load and validate SKILL definitions from YAML files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """A loaded skill definition."""

    name: str
    description: str
    system_prompt: str
    tools: list[str] = field(default_factory=list)
    model: str | None = None
    temperature: float = 0.7
    max_iterations: int = 10
    tags: list[str] = field(default_factory=list)
    examples: list[dict] = field(default_factory=list)
    sub_agents: list[str] = field(default_factory=list)
    rag_context: dict | None = None


class SkillLoader:
    """Loads skill YAML files from a directory."""

    REQUIRED_FIELDS = {"name", "description", "system_prompt"}

    def __init__(self, skills_dir: Path):
        self._skills_dir = skills_dir
        self._skills: dict[str, Skill] = {}

    def load_all(self) -> dict[str, Skill]:
        """Load all .yaml/.yml files from the skills directory."""
        if not self._skills_dir.exists():
            logger.warning("Skills directory not found: %s", self._skills_dir)
            return {}

        self._skills.clear()
        for path in sorted(self._skills_dir.iterdir()):
            if path.name.startswith("_"):
                continue
            if path.suffix not in (".yaml", ".yml"):
                continue
            try:
                skill = self._load_file(path)
                self._skills[skill.name] = skill
                logger.info("Loaded skill: %s", skill.name)
            except Exception as e:
                logger.warning("Failed to load skill %s: %s", path.name, e)

        return self._skills.copy()

    def load(self, name: str) -> Skill | None:
        """Get a loaded skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> list[Skill]:
        """Return all loaded skills."""
        return list(self._skills.values())

    def _load_file(self, path: Path) -> Skill:
        """Load and validate a single YAML skill file."""
        with open(path) as f:
            data = yaml.safe_load(f)

        if not isinstance(data, dict):
            raise ValueError(f"Skill file must contain a YAML mapping: {path}")

        missing = self.REQUIRED_FIELDS - set(data.keys())
        if missing:
            raise ValueError(f"Missing required fields in {path.name}: {missing}")

        return Skill(
            name=data["name"],
            description=data["description"],
            system_prompt=data["system_prompt"],
            tools=data.get("tools", []),
            model=data.get("model"),
            temperature=data.get("temperature", 0.7),
            max_iterations=data.get("max_iterations", 10),
            tags=data.get("tags", []),
            examples=data.get("examples", []),
            sub_agents=data.get("sub_agents", []),
            rag_context=data.get("rag_context"),
        )
