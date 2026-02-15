"""Tests for per-skill model selection."""

from __future__ import annotations

import pytest

from agentgw.core.skill_loader import Skill, SkillLoader
from agentgw.llm.types import Message, StreamChunk


class TestSkillModelSelection:
    """Test that skills can specify their own models."""

    def test_skill_with_explicit_model(self, tmp_path):
        """Skill can specify a model override."""
        skill_file = tmp_path / "test_skill.yaml"
        skill_file.write_text("""
name: test_skill
description: Test skill with explicit model
system_prompt: Test prompt
model: gpt-4o
temperature: 0.5
""")

        loader = SkillLoader(tmp_path)
        loader.load_all()
        skill = loader.load("test_skill")

        assert skill is not None
        assert skill.model == "gpt-4o"
        assert skill.temperature == 0.5

    def test_skill_without_model_uses_none(self, tmp_path):
        """Skill without model field defaults to None."""
        skill_file = tmp_path / "test_skill.yaml"
        skill_file.write_text("""
name: test_skill
description: Test skill without model
system_prompt: Test prompt
""")

        loader = SkillLoader(tmp_path)
        loader.load_all()
        skill = loader.load("test_skill")

        assert skill is not None
        assert skill.model is None  # Will use provider's default

    def test_different_skills_different_models(self, tmp_path):
        """Different skills can use different models."""
        # Create skill 1 with gpt-4o
        skill1_file = tmp_path / "skill1.yaml"
        skill1_file.write_text("""
name: skill1
description: Skill 1
system_prompt: Prompt 1
model: gpt-4o
""")

        # Create skill 2 with gpt-4o-mini
        skill2_file = tmp_path / "skill2.yaml"
        skill2_file.write_text("""
name: skill2
description: Skill 2
system_prompt: Prompt 2
model: gpt-4o-mini
""")

        loader = SkillLoader(tmp_path)
        loader.load_all()

        skill1 = loader.load("skill1")
        skill2 = loader.load("skill2")

        assert skill1.model == "gpt-4o"
        assert skill2.model == "gpt-4o-mini"


class TestModelPassthrough:
    """Test that model is correctly passed to LLM provider."""

    async def test_agent_loop_uses_skill_model(self, sample_skill, memory_store, tool_registry):
        """AgentLoop passes skill's model to LLM."""
        from agentgw.core.agent import AgentLoop
        from agentgw.core.session import Session

        # Track which model was used
        called_with_model = None

        class MockLLM:
            async def chat_stream(self, messages, tools=None, temperature=0.7, model=None):
                nonlocal called_with_model
                called_with_model = model
                # Return a simple text response
                yield StreamChunk(
                    delta_content="Test response",
                    delta_tool_calls=None,
                    finish_reason="stop",
                )

        # Set model on skill
        sample_skill.model = "gpt-4o-test"

        session = Session.create(skill_name="test_skill")
        agent = AgentLoop(
            skill=sample_skill,
            llm=MockLLM(),
            tool_registry=tool_registry,
            memory=memory_store,
            session=session,
        )

        # Run agent
        async for _ in agent.run("test message"):
            pass

        # Verify model was passed
        assert called_with_model == "gpt-4o-test"

    async def test_agent_loop_with_none_model(self, sample_skill, memory_store, tool_registry):
        """AgentLoop passes None when skill has no model (uses provider default)."""
        from agentgw.core.agent import AgentLoop
        from agentgw.core.session import Session

        called_with_model = "not_called"

        class MockLLM:
            async def chat_stream(self, messages, tools=None, temperature=0.7, model=None):
                nonlocal called_with_model
                called_with_model = model
                yield StreamChunk(
                    delta_content="Test response",
                    delta_tool_calls=None,
                    finish_reason="stop",
                )

        # Ensure model is None
        sample_skill.model = None

        session = Session.create(skill_name="test_skill")
        agent = AgentLoop(
            skill=sample_skill,
            llm=MockLLM(),
            tool_registry=tool_registry,
            memory=memory_store,
            session=session,
        )

        async for _ in agent.run("test message"):
            pass

        # Verify None was passed (provider will use its default)
        assert called_with_model is None


class TestModelOverride:
    """Test model override functionality."""

    async def test_service_create_agent_with_model_override(self, tmp_path, monkeypatch):
        """AgentService can override skill's model."""
        from agentgw.core.config import Settings
        from agentgw.core.service import AgentService

        # Mock LLM provider to avoid needing API key
        class MockLLM:
            def __init__(self, api_key, default_model="mock-model"):
                pass

        # Create a skill file
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_file = skills_dir / "test.yaml"
        skill_file.write_text("""
name: test_skill
description: Test
system_prompt: Test prompt
model: gpt-4o
""")

        settings = Settings()
        settings.storage.sqlite_path = tmp_path / "test.db"
        settings.storage.chroma_path = tmp_path / "chroma"
        settings.skills_dir = "skills"
        settings.openai_api_key = "fake-key"  # Set fake key to avoid error

        service = AgentService(settings=settings, root=tmp_path)
        # Replace LLM provider with mock
        monkeypatch.setattr("agentgw.core.service.OpenAIProvider", MockLLM)
        await service.initialize()

        # Create agent with model override
        agent, session, skill = await service.create_agent(
            "test_skill",
            model_override="gpt-4o-mini-override"
        )

        # Verify skill's model was overridden
        assert skill.model == "gpt-4o-mini-override"
