"""SQLite connection manager and query helper."""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database connections and schema initialization."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self, schema_sql: str) -> None:
        """Create tables if they don't exist."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(schema_sql)
            await db.commit()
        logger.info("Database initialized at %s", self._db_path)

    async def execute(self, sql: str, params: tuple = ()) -> int:
        """Execute a write statement. Returns lastrowid."""
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(sql, params)
            await db.commit()
            return cursor.lastrowid or 0

    async def execute_query(self, sql: str, params: tuple = ()) -> list[dict]:
        """Execute a SELECT query and return rows as dicts."""
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(sql, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def execute_many(self, sql: str, param_list: list[tuple]) -> None:
        """Execute a statement with multiple parameter sets."""
        async with aiosqlite.connect(self._db_path) as db:
            await db.executemany(sql, param_list)
            await db.commit()
