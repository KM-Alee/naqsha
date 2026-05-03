"""Memory scope enforcement for shared and private namespaces.

Enforces `shared_` and `private_<agent_id>_` namespace prefixes at the SQL level.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from naqsha.memory.ddl import is_ddl_statement, validate_ddl


class MemoryScope:
    """Scoped access to memory with namespace enforcement.

    A MemoryScope provides SQL execution with automatic namespace prefix enforcement.
    All table names are automatically prefixed with the scope's namespace.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        namespace: str,
        agent_id: str | None = None,
    ) -> None:
        """Initialize a memory scope.

        Args:
            conn: SQLite connection
            namespace: Namespace prefix (e.g., "shared_" or "private_agent1_")
            agent_id: Agent ID for private scopes (None for shared)
        """
        self._conn = conn
        self._namespace = namespace
        self._agent_id = agent_id

        # Validate namespace format
        if not namespace.endswith("_"):
            raise ValueError(f"Namespace must end with underscore: {namespace}")

        if namespace.startswith("private_"):
            if not agent_id:
                raise ValueError("Private namespace requires agent_id")
            expected = f"private_{agent_id}_"
            if namespace != expected:
                raise ValueError(
                    f"Private namespace mismatch: expected {expected}, got {namespace}"
                )
        elif namespace != "shared_":
            raise ValueError(
                f"Invalid namespace: must be 'shared_' or 'private_<agent_id>_', got {namespace}"
            )

    @property
    def namespace(self) -> str:
        """Get the namespace prefix."""
        return self._namespace

    @property
    def agent_id(self) -> str | None:
        """Get the agent ID (None for shared scope)."""
        return self._agent_id

    def _prefix_table_names(self, sql: str) -> str:
        """Add namespace prefix to table names in SQL statement.

        This is a simple implementation that handles common cases.
        It looks for table names after CREATE TABLE, FROM, JOIN, INTO, UPDATE, etc.
        """
        # For DDL statements, prefix the table name
        if is_ddl_statement(sql):
            # CREATE TABLE table_name -> CREATE TABLE namespace_table_name
            sql = re.sub(
                r"(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)" + r"(\w+)",
                rf"\1{self._namespace}\2",
                sql,
                flags=re.IGNORECASE,
            )
            # CREATE INDEX ... ON table_name -> CREATE INDEX ... ON namespace_table_name
            sql = re.sub(
                r"(\bON\s+)(\w+)",
                rf"\1{self._namespace}\2",
                sql,
                flags=re.IGNORECASE,
            )
            # ALTER TABLE table_name -> ALTER TABLE namespace_table_name
            sql = re.sub(
                r"(ALTER\s+TABLE\s+)(\w+)",
                rf"\1{self._namespace}\2",
                sql,
                flags=re.IGNORECASE,
            )
        else:
            # For DML statements, prefix table names after FROM, JOIN, INTO, UPDATE
            # FROM table_name
            sql = re.sub(
                r"(\bFROM\s+)(\w+)",
                rf"\1{self._namespace}\2",
                sql,
                flags=re.IGNORECASE,
            )
            # JOIN table_name
            sql = re.sub(
                r"(\bJOIN\s+)(\w+)",
                rf"\1{self._namespace}\2",
                sql,
                flags=re.IGNORECASE,
            )
            # INTO table_name
            sql = re.sub(
                r"(\bINTO\s+)(\w+)",
                rf"\1{self._namespace}\2",
                sql,
                flags=re.IGNORECASE,
            )
            # UPDATE table_name
            sql = re.sub(
                r"(UPDATE\s+)(\w+)",
                rf"\1{self._namespace}\2",
                sql,
                flags=re.IGNORECASE,
            )

        return sql

    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
    ) -> sqlite3.Cursor:
        """Execute SQL with namespace enforcement.

        Args:
            sql: SQL statement
            params: Query parameters

        Returns:
            SQLite cursor

        Raises:
            ForbiddenDDLError: If DDL statement violates safelist
        """
        # Validate DDL if applicable (only for schema-changing operations)
        if is_ddl_statement(sql):
            validate_ddl(sql)

        # Prefix table names with namespace
        prefixed_sql = self._prefix_table_names(sql)

        if params is None:
            return self._conn.execute(prefixed_sql)
        else:
            return self._conn.execute(prefixed_sql, params)

    def query(
        self,
        sql: str,
        params: tuple[Any, ...] | dict[str, Any] | None = None,
    ) -> list[sqlite3.Row]:
        """Execute query and return all rows.

        Args:
            sql: SQL query
            params: Query parameters

        Returns:
            List of rows
        """
        cursor = self.execute(sql, params)
        return cursor.fetchall()

    def begin(self) -> None:
        """Begin a transaction."""
        self._conn.execute("BEGIN")

    def commit(self) -> None:
        """Commit the current transaction."""
        self._conn.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self._conn.rollback()

    def list_tables(self) -> list[str]:
        """List all tables in this namespace.

        Returns:
            List of table names (without namespace prefix)
        """
        cursor = self._conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name LIKE ?
            ORDER BY name
            """,
            (f"{self._namespace}%",),
        )
        tables = []
        for row in cursor:
            name = row[0]
            # Remove namespace prefix
            if name.startswith(self._namespace):
                tables.append(name[len(self._namespace) :])
        return tables
