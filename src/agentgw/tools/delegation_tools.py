"""Tools for sub-agent orchestration and delegation."""

from __future__ import annotations

from agentgw.tools.decorator import tool

# This will be set during app initialization
_agent_service = None


def set_agent_service(service) -> None:
    """Set the AgentService instance for delegation."""
    global _agent_service
    _agent_service = service


@tool()
async def delegate_to_agent(
    skill_name: str,
    task: str,
    context: str | None = None,
) -> dict:
    """Delegate a task to another specialized agent skill.

    Use this to break down complex tasks into subtasks handled by specialized agents.
    The delegated skill will have its own conversation context and tools.

    Args:
        skill_name: Name of the skill to delegate to (e.g., "code_assistant").
        task: The specific task or question to delegate.
        context: Optional additional context to provide to the sub-agent.

    Returns:
        A dict with the result from the delegated agent.

    Example:
        result = await delegate_to_agent(
            skill_name="code_assistant",
            task="Write a Python function to validate email addresses",
            context="The function should use regex and handle edge cases"
        )
    """
    if _agent_service is None:
        return {"error": "Agent service not initialized for delegation"}

    # Get current orchestration context (injected by AgentLoop)
    # This is a special mechanism to track depth
    from agentgw.core.agent import get_current_orchestration_depth, set_current_orchestration_depth

    current_depth = get_current_orchestration_depth()
    max_depth = _agent_service.settings.agent.max_orchestration_depth

    if current_depth >= max_depth:
        return {
            "error": f"Maximum orchestration depth ({max_depth}) reached. Cannot delegate further.",
            "current_depth": current_depth,
        }

    # Build the full message for the sub-agent
    full_task = task
    if context:
        full_task = f"{context}\n\n{task}"

    try:
        # Create a new agent for the delegated skill
        # Use a new session to keep delegation isolated
        set_current_orchestration_depth(current_depth + 1)

        agent, session, skill = await _agent_service.create_agent(skill_name)

        # Run the delegated task to completion (non-streaming)
        result = await agent.run_to_completion(full_task)

        return {
            "status": "ok",
            "skill": skill_name,
            "result": result,
            "depth": current_depth + 1,
        }

    except ValueError as e:
        return {"error": f"Delegation failed: {e}"}
    finally:
        # Reset depth after delegation completes
        set_current_orchestration_depth(current_depth)
