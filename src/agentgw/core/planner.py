"""Planner agent that routes user intents to the appropriate skill."""

from __future__ import annotations

import json
import logging

from agentgw.core.skill_loader import Skill, SkillLoader
from agentgw.llm.types import Message

logger = logging.getLogger(__name__)

PLANNER_SYSTEM_PROMPT = """You are an intelligent task router. Your job is to analyze the user's message and determine which skill/agent is best suited to handle it.

Available skills:
{skill_descriptions}

Based on the user's message, respond with a JSON object:
{{
  "skill": "<skill_name>",
  "reasoning": "<brief explanation of why this skill was chosen>",
  "refined_message": "<optionally rewritten message for the target skill, or null to pass through as-is>"
}}

If no skill is a good match, respond with:
{{
  "skill": null,
  "reasoning": "No matching skill found",
  "refined_message": null
}}

Respond ONLY with the JSON object, no additional text."""


class PlannerAgent:
    """Routes user intents to the appropriate skill using LLM classification."""

    def __init__(self, llm, skill_loader: SkillLoader):
        self._llm = llm
        self._skill_loader = skill_loader

    def _build_skill_descriptions(self) -> str:
        """Build a formatted list of available skills for the planner prompt."""
        parts = []
        for skill in self._skill_loader.list_skills():
            tags = ", ".join(skill.tags) if skill.tags else "general"
            parts.append(
                f"- **{skill.name}**: {skill.description.strip()} (tags: {tags})"
            )
        return "\n".join(parts)

    async def route(self, user_message: str) -> PlannerResult:
        """Determine which skill should handle the user's message.

        Returns a PlannerResult with the selected skill name and optional refined message.
        """
        skill_descriptions = self._build_skill_descriptions()
        system_prompt = PLANNER_SYSTEM_PROMPT.format(
            skill_descriptions=skill_descriptions
        )

        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_message),
        ]

        response = await self._llm.chat(
            messages=messages,
            temperature=0.1,  # Low temperature for deterministic routing
        )

        if not response.content:
            logger.warning("Planner returned empty response")
            return PlannerResult(skill=None, reasoning="Empty response from planner")

        try:
            data = json.loads(response.content.strip())
            return PlannerResult(
                skill=data.get("skill"),
                reasoning=data.get("reasoning", ""),
                refined_message=data.get("refined_message"),
            )
        except json.JSONDecodeError:
            logger.warning("Planner returned non-JSON: %s", response.content[:200])
            # Fallback: try to extract skill name from the text
            return PlannerResult(
                skill=None,
                reasoning=f"Could not parse planner response: {response.content[:100]}",
            )


class PlannerResult:
    """Result from the planner agent's routing decision."""

    def __init__(
        self,
        skill: str | None = None,
        reasoning: str = "",
        refined_message: str | None = None,
    ):
        self.skill = skill
        self.reasoning = reasoning
        self.refined_message = refined_message

    def __repr__(self) -> str:
        return f"PlannerResult(skill={self.skill!r}, reasoning={self.reasoning!r})"
