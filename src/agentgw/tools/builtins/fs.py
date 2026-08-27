"""Workspace-rooted file tools."""

from __future__ import annotations

from agentgw.harness.spec import RunContext
from agentgw.harness.workspace import Workspace
from agentgw.tools.decorator import tool


@tool()
def read(path: str, max_lines: int = 500, ctx: RunContext | None = None) -> str:
    """Read a text file from the workspace.

    Args:
        path: Path relative to the workspace root.
        max_lines: Maximum number of lines to return.
    """
    target = _ws(ctx).resolve(path)
    if not target.exists():
        return f"Error: File not found: {path}"
    if not target.is_file():
        return f"Error: Not a file: {path}"
    text = target.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + f"\n\n... truncated ({len(lines)} total lines)"
    return text


@tool()
def write(path: str, content: str, ctx: RunContext | None = None) -> str:
    """Write a text file in the workspace. Creates parent directories.

    Args:
        path: Path relative to the workspace root.
        content: Full file contents to write.
    """
    target = _ws(ctx).resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}"


@tool()
def list_dir(directory: str = ".", pattern: str = "*", ctx: RunContext | None = None) -> list[dict]:
    """List files in a workspace directory.

    Args:
        directory: Directory relative to the workspace root.
        pattern: Glob pattern (e.g. '*.md', '**/*.py').
    """
    workspace = _ws(ctx)
    root = workspace.resolve(directory)
    if not root.exists():
        return [{"error": f"Directory not found: {directory}"}]
    if not root.is_dir():
        return [{"error": f"Not a directory: {directory}"}]

    results = []
    for item in sorted(root.glob(pattern)):
        if not _under(item, workspace.root):
            continue
        results.append(
            {
                "name": item.name,
                "path": str(item.relative_to(workspace.root)),
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else None,
            }
        )
        if len(results) >= 200:
            break
    return results


def _ws(ctx: RunContext | None) -> Workspace:
    if ctx is None:
        raise PermissionError("No run context: file tools require a workspace")
    return Workspace(ctx.workspace)


def _under(path, root) -> bool:
    try:
        path.resolve().relative_to(root)
        return True
    except ValueError:
        return False
