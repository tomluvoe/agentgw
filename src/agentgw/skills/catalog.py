"""L1 skill catalog injected into the system prompt."""

from __future__ import annotations

from xml.sax.saxutils import escape

from agentgw.harness.spec import SkillRecord


def render_catalog(skills: list[SkillRecord]) -> str:
    """Compact XML listing: name, description, location. Always cheap to include."""
    if not skills:
        return ""
    parts = ["<available_skills>"]
    for skill in skills:
        if skill.disable_model_invocation:
            continue
        parts.append("  <skill>")
        parts.append(f"    <name>{escape(skill.name)}</name>")
        parts.append(f"    <description>{escape(skill.description)}</description>")
        parts.append(f"    <location>{escape(str(skill.path))}</location>")
        parts.append("  </skill>")
    parts.append("</available_skills>")
    if len(parts) == 2:
        return ""
    return "\n".join(parts)
