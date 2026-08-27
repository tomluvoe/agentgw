"""@tool decorator: OpenAI-style schemas from type hints. ctx is injected, not exposed."""

from __future__ import annotations

import inspect
from typing import Any, Callable, get_args, get_origin

_TOOL_FUNCTIONS: dict[str, ToolFunction] = {}
_SKIP_PARAMS = frozenset({"self", "cls", "ctx", "context"})


class ToolFunction:
    """Wraps a decorated function with its metadata and JSON schema."""

    def __init__(self, func: Callable, name: str, description: str):
        self.func = func
        self.name = name
        self.description = description
        self.schema = self._build_schema()

    def _python_type_to_json(self, annotation: Any) -> dict:
        if annotation is inspect.Parameter.empty or annotation is Any:
            return {"type": "string"}

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is list:
            items = self._python_type_to_json(args[0]) if args else {"type": "string"}
            return {"type": "array", "items": items}
        if origin is dict:
            return {"type": "object"}

        import types
        import typing

        union_origins = {types.UnionType, typing.Union}
        if origin in union_origins:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return self._python_type_to_json(non_none[0])
            return {"type": "string"}

        type_map = {
            str: {"type": "string"},
            int: {"type": "integer"},
            float: {"type": "number"},
            bool: {"type": "boolean"},
        }
        return type_map.get(annotation, {"type": "string"})

    def _build_schema(self) -> dict:
        sig = inspect.signature(self.func)
        doc = inspect.getdoc(self.func) or self.description
        param_docs = self._parse_param_docs(doc)

        properties: dict = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name in _SKIP_PARAMS:
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
        result: dict[str, str] = {}
        in_args = False
        current_param = None
        for line in docstring.split("\n"):
            stripped = line.strip()
            if stripped.lower().startswith("args:"):
                in_args = True
                continue
            if not in_args:
                continue
            if stripped and not line[:1].isspace() and stripped.endswith(":") and " " not in stripped:
                break
            if ":" in stripped:
                parts = stripped.split(":", 1)
                param_name = parts[0].strip().lstrip("-").strip()
                if param_name:
                    current_param = param_name
                    result[current_param] = parts[1].strip()
                    continue
            if current_param and stripped:
                result[current_param] += " " + stripped
        return result

    async def execute(self, arguments: dict, ctx=None) -> Any:
        sig = inspect.signature(self.func)
        kwargs = dict(arguments)
        if "ctx" in sig.parameters:
            kwargs["ctx"] = ctx
        elif "context" in sig.parameters:
            kwargs["context"] = ctx
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**kwargs)
        return self.func(**kwargs)


def tool(name: str | None = None, description: str | None = None) -> Callable:
    """Mark a function as an agent tool. `ctx` / `context` is injected at runtime."""

    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        doc = inspect.getdoc(func) or ""
        tool_desc = description or doc.split("\n")[0] or tool_name
        tool_func = ToolFunction(func=func, name=tool_name, description=tool_desc)
        _TOOL_FUNCTIONS[tool_name] = tool_func
        func._tool = tool_func  # type: ignore[attr-defined]
        return func

    return decorator


def get_registered_tools() -> dict[str, ToolFunction]:
    return _TOOL_FUNCTIONS.copy()


def clear_registered_tools() -> None:
    _TOOL_FUNCTIONS.clear()
