"""Tests for the planner agent."""

import json

import pytest

from agentgw.core.planner import PlannerAgent, PlannerResult
from agentgw.core.skill_loader import Skill, SkillLoader
from agentgw.llm.types import LLMResponse, Message

from tests.conftest import MockLLMProvider


class MockSkillLoader:
    """Minimal skill loader for testing planner routing."""

    def list_skills(self):
        return [
            Skill(
                name="summarize_document",
                description="Summarizes documents and text",
                system_prompt="You summarize.",
                tags=["summarization", "documents"],
            ),
            Skill(
                name="general_assistant",
                description="General-purpose assistant",
                system_prompt="You help.",
                tags=["general"],
            ),
        ]


class TestPlannerAgent:
    @pytest.mark.asyncio
    async def test_route_to_skill(self):
        mock_llm = MockLLMProvider([
            LLMResponse(
                content=json.dumps({
                    "skill": "summarize_document",
                    "reasoning": "User wants to summarize text",
                    "refined_message": None,
                }),
                finish_reason="stop",
            )
        ])
        planner = PlannerAgent(llm=mock_llm, skill_loader=MockSkillLoader())
        result = await planner.route("Please summarize this article for me")

        assert result.skill == "summarize_document"
        assert "summarize" in result.reasoning.lower()

    @pytest.mark.asyncio
    async def test_route_no_match(self):
        mock_llm = MockLLMProvider([
            LLMResponse(
                content=json.dumps({
                    "skill": None,
                    "reasoning": "No matching skill",
                    "refined_message": None,
                }),
                finish_reason="stop",
            )
        ])
        planner = PlannerAgent(llm=mock_llm, skill_loader=MockSkillLoader())
        result = await planner.route("Do something completely unrelated")

        assert result.skill is None

    @pytest.mark.asyncio
    async def test_route_with_refined_message(self):
        mock_llm = MockLLMProvider([
            LLMResponse(
                content=json.dumps({
                    "skill": "general_assistant",
                    "reasoning": "General help needed",
                    "refined_message": "Help me with X",
                }),
                finish_reason="stop",
            )
        ])
        planner = PlannerAgent(llm=mock_llm, skill_loader=MockSkillLoader())
        result = await planner.route("I need help")

        assert result.skill == "general_assistant"
        assert result.refined_message == "Help me with X"

    @pytest.mark.asyncio
    async def test_route_handles_malformed_json(self):
        mock_llm = MockLLMProvider([
            LLMResponse(content="This is not JSON at all", finish_reason="stop")
        ])
        planner = PlannerAgent(llm=mock_llm, skill_loader=MockSkillLoader())
        result = await planner.route("Something")

        assert result.skill is None
        assert "parse" in result.reasoning.lower() or "Could not" in result.reasoning

    @pytest.mark.asyncio
    async def test_route_handles_empty_response(self):
        mock_llm = MockLLMProvider([
            LLMResponse(content=None, finish_reason="stop")
        ])
        planner = PlannerAgent(llm=mock_llm, skill_loader=MockSkillLoader())
        result = await planner.route("Something")

        assert result.skill is None
