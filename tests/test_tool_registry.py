"""Tests for tool registry and @tool decorator."""

import json

import pytest

from agentgw.core.tool_registry import ToolRegistry
from agentgw.tools.decorator import ToolFunction, tool, _TOOL_FUNCTIONS


class TestToolDecorator:
    def test_basic_tool(self):
        @tool(name="test_func")
        def test_func(message: str) -> str:
            """Send a test message.

            Args:
                message: The message to send.
            """
            return f"sent: {message}"

        assert "test_func" in _TOOL_FUNCTIONS
        tf = _TOOL_FUNCTIONS["test_func"]
        assert tf.name == "test_func"
        assert tf.description == "Send a test message."

        schema = tf.schema
        func_schema = schema["function"]
        assert func_schema["name"] == "test_func"
        params = func_schema["parameters"]
        assert "message" in params["properties"]
        assert params["properties"]["message"]["type"] == "string"
        assert "message" in params["required"]

        # Cleanup
        del _TOOL_FUNCTIONS["test_func"]

    def test_tool_with_defaults(self):
        @tool()
        def greet(name: str, greeting: str = "Hello") -> str:
            """Greet someone.

            Args:
                name: Person's name.
                greeting: The greeting to use.
            """
            return f"{greeting}, {name}!"

        tf = _TOOL_FUNCTIONS["greet"]
        params = tf.schema["function"]["parameters"]
        assert "name" in params["required"]
        assert "greeting" not in params["required"]

        del _TOOL_FUNCTIONS["greet"]

    def test_tool_with_list_param(self):
        @tool()
        def process(items: list[str], count: int = 5) -> list[dict]:
            """Process items.

            Args:
                items: List of items.
                count: How many to process.
            """
            return []

        tf = _TOOL_FUNCTIONS["process"]
        params = tf.schema["function"]["parameters"]
        assert params["properties"]["items"]["type"] == "array"
        assert params["properties"]["count"]["type"] == "integer"

        del _TOOL_FUNCTIONS["process"]


class TestToolRegistry:
    def test_discover_built_in_tools(self, tool_registry):
        tools = tool_registry.list_tools()
        assert "read_file" in tools
        assert "list_files" in tools
        assert "search_documents" in tools
        assert "query_db" in tools

    def test_get_schemas(self, tool_registry):
        schemas = tool_registry.get_schemas(["read_file"])
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "read_file"

    def test_get_schemas_all(self, tool_registry):
        schemas = tool_registry.get_schemas()
        assert len(schemas) >= 4

    def test_validate_tool_names(self, tool_registry):
        missing = tool_registry.validate_tool_names(["read_file", "nonexistent_tool"])
        assert missing == ["nonexistent_tool"]

    @pytest.mark.asyncio
    async def test_execute_read_file(self, tool_registry, tmp_dir):
        test_file = tmp_dir / "test.txt"
        test_file.write_text("hello world")

        result = await tool_registry.execute("read_file", {"path": str(test_file)})
        assert "hello world" in result

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, tool_registry):
        result = await tool_registry.execute("nonexistent", {})
        data = json.loads(result)
        assert "error" in data
