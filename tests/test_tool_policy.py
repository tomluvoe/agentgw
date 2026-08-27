from __future__ import annotations

from pathlib import Path

import pytest

from agentgw.harness.spec import RunContext, ToolPolicy
from agentgw.tools.registry import ToolRegistry, reset_builtin_tools


@pytest.mark.asyncio
async def test_deny_blocks_even_if_model_names_tool(tmp_path: Path):
    reset_builtin_tools()
    registry = ToolRegistry()
    registry.collect_registered()
    ctx = RunContext(workspace=tmp_path)
    policy = ToolPolicy(allow=("read", "write"), deny=("exec",))

    result = await registry.execute("exec", {"command": "echo pwned"}, policy, ctx)
    assert "not allowed" in result
    schemas = registry.get_schemas(policy)
    names = [s["function"]["name"] for s in schemas]
    assert "exec" not in names
    assert "read" in names
