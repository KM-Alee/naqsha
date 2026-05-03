"""Tests for MemoryScope namespace enforcement."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from naqsha.memory.ddl import ForbiddenDDLError
from naqsha.memory.scope import MemoryScope


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = Path(f.name)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    yield conn

    conn.close()
    db_path.unlink()


class TestMemoryScopeInit:
    """Test MemoryScope initialization and validation."""

    def test_shared_scope_valid(self, temp_db):
        """Shared scope with correct namespace."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        assert scope.namespace == "shared_"
        assert scope.agent_id is None

    def test_private_scope_valid(self, temp_db):
        """Private scope with correct namespace and agent_id."""
        scope = MemoryScope(temp_db, namespace="private_agent1_", agent_id="agent1")
        assert scope.namespace == "private_agent1_"
        assert scope.agent_id == "agent1"

    def test_namespace_must_end_with_underscore(self, temp_db):
        """Namespace must end with underscore."""
        with pytest.raises(ValueError, match="must end with underscore"):
            MemoryScope(temp_db, namespace="shared", agent_id=None)

    def test_private_requires_agent_id(self, temp_db):
        """Private namespace requires agent_id."""
        with pytest.raises(ValueError, match="requires agent_id"):
            MemoryScope(temp_db, namespace="private_agent1_", agent_id=None)

    def test_private_namespace_mismatch(self, temp_db):
        """Private namespace must match agent_id."""
        with pytest.raises(ValueError, match="Private namespace mismatch"):
            MemoryScope(temp_db, namespace="private_agent1_", agent_id="agent2")

    def test_invalid_namespace(self, temp_db):
        """Invalid namespace format."""
        with pytest.raises(ValueError, match="Invalid namespace"):
            MemoryScope(temp_db, namespace="custom_", agent_id=None)


class TestMemoryScopeTablePrefixing:
    """Test automatic table name prefixing."""

    def test_create_table_prefixed(self, temp_db):
        """CREATE TABLE gets namespace prefix."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        scope.execute("CREATE TABLE users (id INTEGER, name TEXT)")

        cursor = temp_db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='shared_users'"
        )
        assert cursor.fetchone() is not None

    def test_select_from_prefixed(self, temp_db):
        """SELECT FROM gets namespace prefix."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        scope.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        scope.execute("INSERT INTO users VALUES (1, 'Alice')")

        rows = scope.query("SELECT * FROM users")
        assert len(rows) == 1
        assert rows[0]["name"] == "Alice"

    def test_private_scope_isolation(self, temp_db):
        """Private scopes are isolated by agent_id."""
        scope1 = MemoryScope(temp_db, namespace="private_agent1_", agent_id="agent1")
        scope2 = MemoryScope(temp_db, namespace="private_agent2_", agent_id="agent2")

        scope1.execute("CREATE TABLE notes (content TEXT)")
        scope1.execute("INSERT INTO notes VALUES ('Agent1 note')")

        scope2.execute("CREATE TABLE notes (content TEXT)")
        scope2.execute("INSERT INTO notes VALUES ('Agent2 note')")

        rows1 = scope1.query("SELECT * FROM notes")
        assert len(rows1) == 1
        assert rows1[0]["content"] == "Agent1 note"

        rows2 = scope2.query("SELECT * FROM notes")
        assert len(rows2) == 1
        assert rows2[0]["content"] == "Agent2 note"


class TestMemoryScopeDDLEnforcement:
    """Test DDL safelist enforcement through MemoryScope."""

    def test_create_table_allowed(self, temp_db):
        """CREATE TABLE is allowed."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        scope.execute("CREATE TABLE users (id INTEGER)")

    def test_create_index_allowed(self, temp_db):
        """CREATE INDEX is allowed."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        scope.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        scope.execute("CREATE INDEX idx_users_name ON users(name)")

    def test_alter_table_add_column_allowed(self, temp_db):
        """ALTER TABLE ADD COLUMN is allowed."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        scope.execute("CREATE TABLE users (id INTEGER)")
        scope.execute("ALTER TABLE users ADD COLUMN name TEXT")

    def test_drop_table_forbidden(self, temp_db):
        """DROP TABLE is forbidden."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        scope.execute("CREATE TABLE users (id INTEGER)")

        with pytest.raises(ForbiddenDDLError):
            scope.execute("DROP TABLE users")


class TestMemoryScopeTransactions:
    """Test transaction support."""

    def test_commit_transaction(self, temp_db):
        """Commit saves changes."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        scope.execute("CREATE TABLE users (id INTEGER, name TEXT)")

        scope.begin()
        scope.execute("INSERT INTO users VALUES (1, 'Alice')")
        scope.commit()

        rows = scope.query("SELECT * FROM users")
        assert len(rows) == 1

    def test_rollback_transaction(self, temp_db):
        """Rollback discards changes."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        scope.execute("CREATE TABLE users (id INTEGER, name TEXT)")

        scope.begin()
        scope.execute("INSERT INTO users VALUES (1, 'Alice')")
        scope.rollback()

        rows = scope.query("SELECT * FROM users")
        assert len(rows) == 0


class TestMemoryScopeListTables:
    """Test table listing."""

    def test_list_tables_empty(self, temp_db):
        """List tables when none exist."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        tables = scope.list_tables()
        assert tables == []

    def test_list_tables_shared(self, temp_db):
        """List shared tables."""
        scope = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        scope.execute("CREATE TABLE users (id INTEGER)")
        scope.execute("CREATE TABLE posts (id INTEGER)")

        tables = scope.list_tables()
        assert sorted(tables) == ["posts", "users"]

    def test_list_tables_private(self, temp_db):
        """List private tables."""
        scope = MemoryScope(temp_db, namespace="private_agent1_", agent_id="agent1")
        scope.execute("CREATE TABLE notes (content TEXT)")
        scope.execute("CREATE TABLE tasks (title TEXT)")

        tables = scope.list_tables()
        assert sorted(tables) == ["notes", "tasks"]

    def test_list_tables_isolation(self, temp_db):
        """Each scope only sees its own tables."""
        shared = MemoryScope(temp_db, namespace="shared_", agent_id=None)
        private1 = MemoryScope(temp_db, namespace="private_agent1_", agent_id="agent1")
        private2 = MemoryScope(temp_db, namespace="private_agent2_", agent_id="agent2")

        shared.execute("CREATE TABLE users (id INTEGER)")
        private1.execute("CREATE TABLE notes (content TEXT)")
        private2.execute("CREATE TABLE tasks (title TEXT)")

        assert shared.list_tables() == ["users"]
        assert private1.list_tables() == ["notes"]
        assert private2.list_tables() == ["tasks"]
