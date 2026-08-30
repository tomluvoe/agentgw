"""Tool registry: discover, allowlist, execute."""

from __future__ import annotations

import importlib
import importlib.util
import json
import logging
import sys
from pathlib import Path
from typing import Any

from agentgw.harness.spec import RunContext, ToolPolicy
from agentgw.tools.decorator import (
    ToolFunction,
    clear_registered_tools,
    get_registered_tools,
)


def reset_builtin_tools() -> None:
    """Clear the global @tool registry and re-import harness builtins."""
    import importlib

    from agentgw.tools.builtins import fs, notify, shell

    clear_registered_tools()
    importlib.reload(fs)
    importlib.reload(shell)
    importlib.reload(notify)

logger = logging.getLogger(__name__)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolFunction] = {}

    def add(self, tool: ToolFunction) -> None:
        self._tools[tool.name] = tool

    def collect_registered(self) -> None:
        """Copy tools registered via @tool() since the last collect."""
        for name, tool in get_registered_tools().items():
            self._tools[name] = tool

    def load_module(self, module_name: str) -> None:
        importlib.import_module(module_name)
        self.collect_registered()

    def load_path(self, path: Path) -> None:
        """Import every .py file in a directory (or a single module file)."""
        path = path.expanduser().resolve()
        if path.is_file() and path.suffix == ".py":
            self._import_file(path)
            self.collect_registered()
            return
        if not path.is_dir():
            logger.warning("Tool path does not exist: %s", path)
            return
        for py in sorted(path.glob("*.py")):
            if py.name.startswith("_"):
                continue
            self._import_file(py)
        self.collect_registered()

    def _import_file(self, path: Path) -> None:
        mod_name = f"agentgw_ext_{path.stem}_{abs(hash(str(path))) % 10_000_000}"
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            logger.warning("Cannot import tool module: %s", path)
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            logger.exception("Failed to import tools from %s", path)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def get_schemas(self, policy: ToolPolicy) -> list[dict]:
        return [self._tools[n].schema for n in policy.filter(list(self._tools)) if n in self._tools]

    async def execute(
        self,
        name: str,
        arguments: dict[str, Any],
        policy: ToolPolicy,
        ctx: RunContext | None = None,
    ) -> str:
        if not policy.permits(name):
            return json.dumps({"error": f"Tool not allowed: {name}"})
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            result = await tool.execute(arguments, ctx=ctx)
            if isinstance(result, str):
                return result
            return json.dumps(result, default=str)
        except PermissionError as e:
            return json.dumps({"error": str(e)})
        except Exception as e:
            logger.exception("Tool execution failed: %s", name)
            return json.dumps({"error": str(e)})
