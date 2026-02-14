"""File system tools for reading and listing files."""

from __future__ import annotations

from pathlib import Path

from agentgw.tools.decorator import tool


@tool()
def read_file(path: str, max_lines: int = 500) -> str:
    """Read the contents of a file.

    Args:
        path: Path to the file to read.
        max_lines: Maximum number of lines to return.
    """
    p = Path(path).expanduser().resolve()
    if not p.exists():
        return f"Error: File not found: {path}"
    if not p.is_file():
        return f"Error: Not a file: {path}"
    try:
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            return "\n".join(lines[:max_lines]) + f"\n\n... truncated ({len(lines)} total lines)"
        return text
    except Exception as e:
        return f"Error reading file: {e}"


@tool()
def list_files(directory: str = ".", pattern: str = "*") -> list[dict]:
    """List files in a directory matching a glob pattern.

    Args:
        directory: Directory to list files in.
        pattern: Glob pattern to match (e.g. '*.py', '**/*.yaml').
    """
    p = Path(directory).expanduser().resolve()
    if not p.exists():
        return [{"error": f"Directory not found: {directory}"}]
    if not p.is_dir():
        return [{"error": f"Not a directory: {directory}"}]

    results = []
    for item in sorted(p.glob(pattern)):
        results.append({
            "name": item.name,
            "path": str(item),
            "type": "directory" if item.is_dir() else "file",
            "size": item.stat().st_size if item.is_file() else None,
        })
        if len(results) >= 200:
            break
    return results
