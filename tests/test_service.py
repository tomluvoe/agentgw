"""Tests for the shared service layer."""

import pytest

from agentgw.core.service import AgentService
from agentgw.core.config import Settings, LLMConfig, AgentConfig, StorageConfig


class TestAgentService:
    @pytest.fixture
    async def service(self, tmp_dir):
        """Create a service with test paths (no LLM needed for most tests)."""
        settings = Settings(
            llm=LLMConfig(provider="openai", model="test-model"),
            agent=AgentConfig(),
            storage=StorageConfig(
                sqlite_path=str(tmp_dir / "test.db"),
                chroma_path=str(tmp_dir / "chroma"),
                log_dir=str(tmp_dir / "logs"),
            ),
            skills_dir="skills",
            openai_api_key="test-key",
        )
        svc = AgentService(settings=settings)
        await svc.initialize()
        return svc

    @pytest.mark.asyncio
    async def test_create_agent_new_session(self, service, sample_skill):
        # Ensure the skill loader has at least a skill we can load
        service.skill_loader._skills["test_skill"] = sample_skill

        agent, session, skill = await service.create_agent("test_skill")
        assert session.id is not None
        assert skill.name == "test_skill"
        assert len(session.get_messages()) == 0

    @pytest.mark.asyncio
    async def test_create_agent_resume_session(self, service, sample_skill, memory_store):
        service.skill_loader._skills["test_skill"] = sample_skill

        # Create a session and add some messages
        agent1, session1, _ = await service.create_agent("test_skill")
        from agentgw.llm.types import Message
        await service.memory.save_message(
            session1.id, Message(role="user", content="Hello"), "test_skill"
        )
        await service.memory.save_message(
            session1.id, Message(role="assistant", content="Hi!"), "test_skill"
        )

        # Resume the session
        agent2, session2, _ = await service.create_agent(
            "test_skill", session_id=session1.id
        )
        assert session2.id == session1.id
        assert len(session2.get_messages()) == 2

    @pytest.mark.asyncio
    async def test_create_agent_unknown_skill(self, service):
        with pytest.raises(ValueError, match="not found"):
            await service.create_agent("nonexistent_skill")

    @pytest.mark.asyncio
    async def test_llm_lazy_init(self, tmp_dir):
        settings = Settings(
            storage=StorageConfig(
                sqlite_path=str(tmp_dir / "test.db"),
                chroma_path=str(tmp_dir / "chroma"),
                log_dir=str(tmp_dir / "logs"),
            ),
            openai_api_key="",
        )
        svc = AgentService(settings=settings)
        # LLM should not be initialized yet
        assert svc._llm is None
        # Accessing .llm without a key should raise
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            _ = svc.llm
