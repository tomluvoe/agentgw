"""Workspace-rooted path resolution. File tools cannot escape this root."""

from __future__ import annotations

from pathlib import Path


class Workspace:
    """A directory the agent is allowed to read, write, and exec in."""

    def __init__(self, root: Path):
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, user_path: str) -> Path:
        """Resolve a user-supplied path and reject anything outside the root."""
        p = Path(user_path).expanduser()
        target = p.resolve() if p.is_absolute() else (self.root / p).resolve()
        if not _is_relative_to(target, self.root):
            raise PermissionError(f"Path escapes workspace: {user_path}")
        return target

    def relative(self, path: Path) -> str:
        return str(path.relative_to(self.root))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
