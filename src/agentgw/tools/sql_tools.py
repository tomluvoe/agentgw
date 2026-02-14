"""SQL tools for querying the SQLite database."""

from __future__ import annotations

from agentgw.tools.decorator import tool

_db_manager = None


def set_db_manager(manager) -> None:
    """Set the database manager instance for tool use."""
    global _db_manager
    _db_manager = manager


@tool()
async def query_db(query: str) -> list[dict]:
    """Execute a read-only SQL query against the SQLite database.

    Only SELECT statements are allowed for safety.

    Args:
        query: SQL SELECT query to execute.
    """
    if _db_manager is None:
        return [{"error": "Database not initialized"}]

    stripped = query.strip().upper()
    if not stripped.startswith("SELECT"):
        return [{"error": "Only SELECT queries are allowed"}]

    try:
        return await _db_manager.execute_query(query)
    except Exception as e:
        return [{"error": f"Query failed: {e}"}]
