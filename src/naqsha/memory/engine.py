"""Dynamic Memory Engine with SQLite backend.

Supports both Shared Memory (team-wide) and Private Memory (agent-specific)
with optional sqlite-vec embeddings.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from naqsha.memory.scope import MemoryScope

if TYPE_CHECKING:
    pass


class DynamicMemoryEngine:
    """SQLite-backed memory engine with shared and private namespaces.

    The engine manages a single SQLite database with namespace-isolated tables:
    - Shared tables: prefixed with `shared_`
    - Private tables: prefixed with `private_<agent_id>_`

    Optional sqlite-vec support for semantic search can be enabled via config.
    """

    def __init__(
        self,
        *,
        db_path: Path | str,
        enable_embeddings: bool = False,
    ) -> None:
        """Initialize the Dynamic Memory Engine.

        Args:
            db_path: Path to SQLite database file
            enable_embeddings: Whether to load sqlite-vec for embeddings
        """
        self._db_path = Path(db_path)
        self._enable_embeddings = enable_embeddings

        # Ensure parent directory exists
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # Open connection
        self._conn = sqlite3.connect(
            str(self._db_path), isolation_level=None, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrency
        self._conn.execute("PRAGMA journal_mode=WAL")

        # Load sqlite-vec if embeddings are enabled
        if self._enable_embeddings:
            self._load_sqlite_vec()

    def _load_sqlite_vec(self) -> None:
        """Load sqlite-vec extension for vector embeddings.

        Raises:
            ImportError: If sqlite-vec is not installed
        """
        try:
            import sqlite_vec  # type: ignore

            # Load the extension
            sqlite_vec.load(self._conn)
        except ImportError as e:
            raise ImportError(
                "sqlite-vec is required for embeddings support. "
                "Install with: pip install naqsha[embeddings]"
            ) from e

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def get_shared_scope(self) -> MemoryScope:
        """Get a MemoryScope for shared (team-wide) memory.

        Returns:
            MemoryScope with 'shared_' namespace
        """
        return MemoryScope(self._conn, namespace="shared_", agent_id=None)

    def get_private_scope(self, agent_id: str) -> MemoryScope:
        """Get a MemoryScope for private (agent-specific) memory.

        Args:
            agent_id: Agent identifier

        Returns:
            MemoryScope with 'private_<agent_id>_' namespace
        """
        if not agent_id:
            raise ValueError("agent_id cannot be empty")

        namespace = f"private_{agent_id}_"
        return MemoryScope(self._conn, namespace=namespace, agent_id=agent_id)

    @property
    def connection(self) -> sqlite3.Connection:
        """Get the underlying SQLite connection.

        This is exposed for advanced use cases but should generally not be used directly.
        Use get_shared_scope() or get_private_scope() instead.
        """
        return self._conn

    @property
    def embeddings_enabled(self) -> bool:
        """Check if embeddings are enabled."""
        return self._enable_embeddings

    def list_all_tables(self) -> dict[str, list[str]]:
        """List all tables grouped by namespace.

        Returns:
            Dictionary mapping namespace to list of table names (without prefix)
        """
        cursor = self._conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )

        tables: dict[str, list[str]] = {
            "shared": [],
            "private": {},
        }

        for row in cursor:
            name = row[0]
            if name.startswith("shared_"):
                tables["shared"].append(name[7:])  # Remove 'shared_' prefix
            elif name.startswith("private_"):
                # Extract agent_id from 'private_<agent_id>_<table>'
                rest = name[8:]  # Remove 'private_' prefix
                if "_" in rest:
                    agent_id, table_name = rest.split("_", 1)
                    if agent_id not in tables["private"]:
                        tables["private"][agent_id] = []
                    tables["private"][agent_id].append(table_name)

        return tables
