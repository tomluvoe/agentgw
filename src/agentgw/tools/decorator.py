"""@tool decorator for defining agent tools with auto-generated JSON schemas."""

from __future__ import annotations

import inspect
import json
from typing import Any, Callable, get_args, get_origin


# Registry of all decorated tools (populated at import time)
_TOOL_FUNCTIONS: dict[str, ToolFunction] = {}


class ToolFunction:
    """Wraps a decorated function with its metadata and JSON schema."""

    def __init__(self, func: Callable, name: str, description: str):
        self.func = func
        self.name = name
        self.description = description
        self.schema = self._build_schema()

    def _python_type_to_json(self, annotation: Any) -> dict:
        """Convert a Python type annotation to a JSON Schema type."""
        if annotation is inspect.Parameter.empty or annotation is Any:
            return {"type": "string"}

        origin = get_origin(annotation)
        args = get_args(annotation)

        # Handle Optional (Union[X, None])
        if origin is type(None):
            return {"type": "string"}

        # Handle list[X]
        if origin is list:
            items = self._python_type_to_json(args[0]) if args else {"type": "string"}
            return {"type": "array", "items": items}

        # Handle dict[str, X]
        if origin is dict:
            return {"type": "object"}

        # Handle Union types (including Optional = Union[X, None])
        import types
        if origin is types.UnionType or (hasattr(origin, '__origin__') and str(origin) == 'typing.Union'):
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return self._python_type_to_json(non_none[0])
            return {"type": "string"}

        # Also handle typing.Union explicitly
        try:
            import typing
            if origin is typing.Union:
                non_none = [a for a in args if a is not type(None)]
                if len(non_none) == 1:
                    return self._python_type_to_json(non_none[0])
                return {"type": "string"}
        except Exception:
            pass

        type_map = {
            str: {"type": "string"},
            int: {"type": "integer"},
            float: {"type": "number"},
            bool: {"type": "boolean"},
        }
        return type_map.get(annotation, {"type": "string"})

    def _build_schema(self) -> dict:
        """Build an OpenAI-compatible function schema from the function signature."""
        sig = inspect.signature(self.func)
        doc = inspect.getdoc(self.func) or self.description

        # Parse parameter descriptions from docstring Args: section
        param_docs = self._parse_param_docs(doc)

        properties: dict = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            prop = self._python_type_to_json(param.annotation)
            if param_name in param_docs:
                prop["description"] = param_docs[param_name]

            properties[param_name] = prop

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def _parse_param_docs(self, docstring: str) -> dict[str, str]:
        """Extract parameter descriptions from Google-style docstring Args section."""
        result: dict[str, str] = {}
        in_args = False
        current_param = None

        for line in docstring.split("\n"):
            stripped = line.strip()
            if stripped.lower().startswith("args:"):
                in_args = True
                continue
            if in_args:
                if stripped == "" or (not stripped.startswith(" ") and not line.startswith("\t") and ":" in stripped and not stripped.startswith("-")):
                    # Check if this is a new section header
                    if stripped and not stripped[0].isspace() and stripped.endswith(":"):
                        break
                # Check for param: description pattern
                if ":" in stripped:
                    parts = stripped.split(":", 1)
                    param_name = parts[0].strip().lstrip("-").strip()
                    if param_name and not param_name.startswith(" "):
                        current_param = param_name
                        result[current_param] = parts[1].strip()
                        continue
                if current_param and stripped:
                    result[current_param] += " " + stripped

        return result

    async def execute(self, arguments: dict) -> Any:
        """Execute the tool function with the given arguments."""
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**arguments)
        return self.func(**arguments)


def tool(
    name: str | None = None,
    description: str | None = None,
) -> Callable:
    """Decorator that marks a function as an agent tool.

    Args:
        name: Tool name (defaults to function name).
        description: Tool description (defaults to first line of docstring).
    """
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        doc = inspect.getdoc(func) or ""
        tool_desc = description or doc.split("\n")[0] or tool_name

        tool_func = ToolFunction(func=func, name=tool_name, description=tool_desc)
        _TOOL_FUNCTIONS[tool_name] = tool_func

        # Attach metadata to the function itself
        func._tool = tool_func
        return func

    return decorator


def get_registered_tools() -> dict[str, ToolFunction]:
    """Return all registered tool functions."""
    return _TOOL_FUNCTIONS.copy()
