"""Compile the system prompt: agent body + L1 catalog + L2 skill bodies."""

from __future__ import annotations

from agentgw.harness.spec import SkillRecord
from agentgw.skills.catalog import render_catalog


def compile_system_prompt(
    agent_prompt: str,
    catalog_skills: list[SkillRecord],
    activated: list[SkillRecord],
) -> str:
    parts = [agent_prompt.strip()]
    catalog = render_catalog(catalog_skills)
    if catalog:
        parts.append(
            "You have skills available. The catalog lists every eligible skill. "
            "Follow an active skill's instructions when they apply. "
            "You may read other skill files from their location if you need more detail."
        )
        parts.append(catalog)
    if activated:
        parts.append("## Active skill instructions")
        for skill in activated:
            body = skill.body.replace("{baseDir}", str(skill.directory))
            parts.append(f"### {skill.name}\n{body}")
    return "\n\n".join(p for p in parts if p)
