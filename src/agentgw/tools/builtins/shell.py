"""Run a command with cwd set to the workspace. Not a full sandbox."""

from __future__ import annotations

import subprocess

from agentgw.harness.spec import RunContext
from agentgw.tools.decorator import tool


@tool(name="exec")
def run_command(command: str, timeout: int = 60, ctx: RunContext | None = None) -> str:
    """Run a shell command with the workspace as the working directory.

    Args:
        command: Shell command to run.
        timeout: Seconds before the process is killed.
    """
    if ctx is None:
        raise PermissionError("No run context: exec requires a workspace")
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=ctx.workspace,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**ctx.env} if ctx.env else None,
        )
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    parts = []
    if completed.stdout:
        parts.append(completed.stdout)
    if completed.stderr:
        parts.append(completed.stderr)
    output = "".join(parts).rstrip()
    if completed.returncode != 0:
        suffix = f"\n[exit {completed.returncode}]"
        return (output + suffix) if output else suffix.strip()
    return output or "[exit 0]"
