"""Shared extra tool. Agents include this directory via tools.modules."""

from agentgw.tools.decorator import tool


@tool()
def echo(text: str) -> str:
    """Return the given text unchanged.

    Args:
        text: Text to echo back.
    """
    return text
