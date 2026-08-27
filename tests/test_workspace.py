from __future__ import annotations

from pathlib import Path

import pytest

from agentgw.harness.spec import RunContext, ToolPolicy
from agentgw.harness.workspace import Workspace
from agentgw.tools.registry import ToolRegistry, reset_builtin_tools


def test_resolve_inside_and_escape(tmp_path: Path):
    ws = Workspace(tmp_path)
    inside = ws.resolve("notes/a.md")
    assert inside == (tmp_path / "notes" / "a.md").resolve()
    with pytest.raises(PermissionError):
        ws.resolve("../etc/passwd")
    with pytest.raises(PermissionError):
        ws.resolve("/etc/passwd")


@pytest.mark.asyncio
async def test_read_write_jailed(tmp_path: Path):
    reset_builtin_tools()
    registry = ToolRegistry()
    registry.collect_registered()
    ctx = RunContext(workspace=tmp_path)
    policy = ToolPolicy(allow=("read", "write", "list_dir", "exec"))

    written = await registry.execute(
        "write", {"path": "hello.txt", "content": "hi"}, policy, ctx
    )
    assert "Wrote" in written
    text = await registry.execute("read", {"path": "hello.txt"}, policy, ctx)
    assert text == "hi"
    escaped = await registry.execute("read", {"path": "/etc/passwd"}, policy, ctx)
    assert "escapes workspace" in escaped
