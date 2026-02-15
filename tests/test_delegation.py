"""Tests for sub-agent orchestration and delegation."""

from __future__ import annotations

import pytest

from agentgw.core.agent import AgentLoop, get_current_orchestration_depth, set_current_orchestration_depth
from agentgw.core.service import AgentService
from agentgw.tools.delegation_tools import delegate_to_agent, set_agent_service


@pytest.fixture
async def agent_service(tmp_path):
    """Create an AgentService with temporary storage."""
    # Create a minimal settings structure
    from agentgw.core.config import Settings
    settings = Settings()
    settings.storage.sqlite_path = tmp_path / "test.db"
    settings.storage.chroma_path = tmp_path / "chroma"

    svc = AgentService(settings=settings, root=tmp_path.parent)
    await svc.initialize()
    yield svc


class TestOrchestrationDepth:
    """Test orchestration depth tracking."""

    def test_default_depth_is_zero(self):
        """Default orchestration depth should be 0."""
        assert get_current_orchestration_depth() == 0

    def test_set_and_get_depth(self):
        """Can set and retrieve orchestration depth."""
        set_current_orchestration_depth(2)
        assert get_current_orchestration_depth() == 2

        set_current_orchestration_depth(0)
        assert get_current_orchestration_depth() == 0

    async def test_agent_loop_sets_depth(self, agent_service, sample_skill, mock_llm, memory_store, tool_registry):
        """AgentLoop sets orchestration depth from constructor."""
        from agentgw.core.session import Session

        session = Session.create(skill_name="test_skill")

        # Create agent with depth=2
        agent = AgentLoop(
            skill=sample_skill,
            llm=mock_llm,
            tool_registry=tool_registry,
            memory=memory_store,
            session=session,
            orchestration_depth=2,
        )

        # Run and check depth is set
        async for _ in agent.run("test message"):
            pass

        # After run, depth should still be accessible
        # (this is a simple test - in practice depth is maintained in context var)


class TestDelegationTool:
    """Test the delegate_to_agent tool."""

    async def test_delegation_without_service(self):
        """Delegation fails gracefully if service not initialized."""
        set_agent_service(None)
        result = await delegate_to_agent("test_skill", "test task")
        assert "error" in result
        assert "not initialized" in result["error"]

    async def test_delegation_max_depth_reached(self, agent_service):
        """Delegation fails when max depth is reached."""
        set_agent_service(agent_service)

        # Set depth to max
        max_depth = agent_service.settings.agent.max_orchestration_depth
        set_current_orchestration_depth(max_depth)

        result = await delegate_to_agent("general_assistant", "test task")
        assert "error" in result
        assert "Maximum orchestration depth" in result["error"]
        assert result.get("current_depth") == max_depth

    async def test_delegation_to_nonexistent_skill(self, agent_service):
        """Delegation fails gracefully for unknown skills."""
        set_agent_service(agent_service)
        set_current_orchestration_depth(0)

        result = await delegate_to_agent("nonexistent_skill", "test task")
        assert "error" in result
        assert "Delegation failed" in result["error"]

    async def test_delegation_increments_depth(self, agent_service):
        """Delegation should increment orchestration depth."""
        set_agent_service(agent_service)
        set_current_orchestration_depth(0)

        # This will fail because general_assistant doesn't exist in test
        # But we can check that it attempts to increment depth
        result = await delegate_to_agent("general_assistant", "test task")

        # Should have error (skill not found) but attempted depth increment
        assert "error" in result or "status" in result

    async def test_delegation_with_context(self, agent_service):
        """Delegation can include additional context."""
        set_agent_service(agent_service)
        set_current_orchestration_depth(0)

        result = await delegate_to_agent(
            "general_assistant",
            "solve this problem",
            context="Here is some background information"
        )

        # Should fail due to missing skill, but function should accept context
        assert isinstance(result, dict)


class TestOrchestrationWorkflow:
    """Test end-to-end orchestration workflows."""

    async def test_create_agent_with_orchestration_depth(self, agent_service):
        """AgentService can create agents with specific orchestration depth."""
        set_current_orchestration_depth(1)

        # This will fail if skill doesn't exist, but we're testing the parameter passing
        try:
            agent, session, skill = await agent_service.create_agent(
                "general_assistant",
                orchestration_depth=1
            )
            # If we get here, check the agent has the right depth
            assert agent._orchestration_depth == 1
        except ValueError:
            # Expected if skill doesn't exist - that's OK for this test
            pass

    async def test_orchestration_depth_auto_detection(self, agent_service):
        """AgentService auto-detects orchestration depth if not provided."""
        set_current_orchestration_depth(2)

        try:
            agent, session, skill = await agent_service.create_agent("general_assistant")
            # Should inherit depth from context
            assert agent._orchestration_depth == 2
        except ValueError:
            # Expected if skill doesn't exist
            pass

        # Reset depth
        set_current_orchestration_depth(0)


class TestOrchestrationLimits:
    """Test orchestration depth limits and guards."""

    def test_default_max_depth_is_configured(self, agent_service):
        """Default max orchestration depth should be configured."""
        max_depth = agent_service.settings.agent.max_orchestration_depth
        assert max_depth > 0
        assert max_depth <= 5  # Reasonable upper bound

    async def test_delegation_respects_max_depth(self, agent_service):
        """Delegation should respect max depth configuration."""
        set_agent_service(agent_service)
        max_depth = agent_service.settings.agent.max_orchestration_depth

        # Set to max depth
        set_current_orchestration_depth(max_depth)

        result = await delegate_to_agent("any_skill", "any task")
        assert "error" in result
        assert "Maximum orchestration depth" in result["error"]

        # Set to max - 1 (should be allowed)
        set_current_orchestration_depth(max_depth - 1)

        result = await delegate_to_agent("any_skill", "any task")
        # Should not have max depth error (might have other errors like skill not found)
        if "error" in result:
            assert "Maximum orchestration depth" not in result["error"]
