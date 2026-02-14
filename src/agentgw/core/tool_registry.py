"""Tool registry: auto-discover, validate, and execute @tool functions."""

from __future__ import annotations

import importlib
import json
import logging
import pkgutil
from typing import Any

from agentgw.tools.decorator import ToolFunction, get_registered_tools

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Manages discovery and execution of @tool decorated functions."""

    def __init__(self):
        self._tools: dict[str, ToolFunction] = {}

    def discover(self, module_names: list[str]) -> None:
        """Import modules (and their submodules) to trigger @tool registration."""
        for module_name in module_names:
            try:
                mod = importlib.import_module(module_name)
                # If it's a package, import all submodules
                if hasattr(mod, "__path__"):
                    for _importer, submod_name, _is_pkg in pkgutil.iter_modules(mod.__path__):
                        full_name = f"{module_name}.{submod_name}"
                        try:
                            importlib.import_module(full_name)
                        except Exception as e:
                            logger.warning("Failed to import tool module %s: %s", full_name, e)
            except Exception as e:
                logger.warning("Failed to import tool module %s: %s", module_name, e)

        # Collect all registered tools
        self._tools = get_registered_tools()
        logger.info("Discovered %d tools: %s", len(self._tools), list(self._tools.keys()))

    def get(self, name: str) -> ToolFunction | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all available tool names."""
        return list(self._tools.keys())

    def get_schemas(self, names: list[str] | None = None) -> list[dict]:
        """Return OpenAI function-calling schemas for the given tool names.

        If names is None, return schemas for all tools.
        """
        if names is None:
            return [t.schema for t in self._tools.values()]
        return [
            self._tools[n].schema
            for n in names
            if n in self._tools
        ]

    def validate_tool_names(self, names: list[str]) -> list[str]:
        """Return list of tool names that don't exist in the registry."""
        return [n for n in names if n not in self._tools]

    async def execute(self, name: str, arguments: dict[str, Any]) -> str:
        """Execute a tool and return the result as a string."""
        tool = self._tools.get(name)
        if tool is None:
            return json.dumps({"error": f"Unknown tool: {name}"})

        try:
            result = await tool.execute(arguments)
            if isinstance(result, str):
                return result
            return json.dumps(result, default=str)
        except Exception as e:
            logger.exception("Tool execution failed: %s", name)
            return json.dumps({"error": str(e)})
