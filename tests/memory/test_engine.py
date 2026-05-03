"""Tests for DynamicMemoryEngine."""

import tempfile
from pathlib import Path

import pytest

from naqsha.memory.engine import DynamicMemoryEngine


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "memory.db"


class TestDynamicMemoryEngineInit:
    """Test DynamicMemoryEngine initialization."""

    def test_init_creates_database(self, temp_db_path):
        """Engine creates database file."""
        assert not temp_db_path.exists()

        engine = DynamicMemoryEngine(db_path=temp_db_path)
        assert temp_db_path.exists()

        engine.close()

    def test_init_creates_parent_directory(self):
        """Engine creates parent directories if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "subdir" / "memory.db"
            assert not db_path.parent.exists()

            engine = DynamicMemoryEngine(db_path=db_path)
            assert db_path.exists()
            assert db_path.parent.exists()

            engine.close()

    def test_init_without_embeddings(self, temp_db_path):
        """Engine initializes without embeddings by default."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)
        assert not engine.embeddings_enabled
        engine.close()

    def test_init_with_embeddings_flag(self, temp_db_path):
        """Engine can be initialized with embeddings flag."""
        # This will fail if sqlite-vec is not installed, which is expected
        try:
            engine = DynamicMemoryEngine(db_path=temp_db_path, enable_embeddings=True)
            assert engine.embeddings_enabled
            engine.close()
        except ImportError:
            # sqlite-vec not installed, skip this test
            pytest.skip("sqlite-vec not installed")


class TestDynamicMemoryEngineScopes:
    """Test scope creation and isolation."""

    def test_get_shared_scope(self, temp_db_path):
        """Get shared memory scope."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)

        scope = engine.get_shared_scope()
        assert scope.namespace == "shared_"
        assert scope.agent_id is None

        engine.close()

    def test_get_private_scope(self, temp_db_path):
        """Get private memory scope."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)

        scope = engine.get_private_scope("agent1")
        assert scope.namespace == "private_agent1_"
        assert scope.agent_id == "agent1"

        engine.close()

    def test_private_scope_requires_agent_id(self, temp_db_path):
        """Private scope requires non-empty agent_id."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)

        with pytest.raises(ValueError, match="agent_id cannot be empty"):
            engine.get_private_scope("")

        engine.close()

    def test_multiple_private_scopes(self, temp_db_path):
        """Multiple agents can have private scopes."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)

        scope1 = engine.get_private_scope("agent1")
        scope2 = engine.get_private_scope("agent2")

        assert scope1.namespace == "private_agent1_"
        assert scope2.namespace == "private_agent2_"

        engine.close()


class TestDynamicMemoryEngineIsolation:
    """Test namespace isolation between scopes."""

    def test_shared_private_isolation(self, temp_db_path):
        """Shared and private scopes are isolated."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)

        shared = engine.get_shared_scope()
        private = engine.get_private_scope("agent1")

        shared.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        shared.execute("INSERT INTO users VALUES (1, 'Alice')")

        private.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        private.execute("INSERT INTO users VALUES (2, 'Bob')")

        shared_rows = shared.query("SELECT * FROM users")
        assert len(shared_rows) == 1
        assert shared_rows[0]["name"] == "Alice"

        private_rows = private.query("SELECT * FROM users")
        assert len(private_rows) == 1
        assert private_rows[0]["name"] == "Bob"

        engine.close()

    def test_private_private_isolation(self, temp_db_path):
        """Private scopes are isolated from each other."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)

        private1 = engine.get_private_scope("agent1")
        private2 = engine.get_private_scope("agent2")

        private1.execute("CREATE TABLE notes (content TEXT)")
        private1.execute("INSERT INTO notes VALUES ('Agent1 secret')")

        private2.execute("CREATE TABLE notes (content TEXT)")
        private2.execute("INSERT INTO notes VALUES ('Agent2 secret')")

        rows1 = private1.query("SELECT * FROM notes")
        assert len(rows1) == 1
        assert rows1[0]["content"] == "Agent1 secret"

        rows2 = private2.query("SELECT * FROM notes")
        assert len(rows2) == 1
        assert rows2[0]["content"] == "Agent2 secret"

        engine.close()


class TestDynamicMemoryEngineListTables:
    """Test table listing across namespaces."""

    def test_list_all_tables_empty(self, temp_db_path):
        """List tables when database is empty."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)

        tables = engine.list_all_tables()
        assert tables["shared"] == []
        assert tables["private"] == {}

        engine.close()

    def test_list_all_tables_with_data(self, temp_db_path):
        """List all tables across namespaces."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)

        shared = engine.get_shared_scope()
        shared.execute("CREATE TABLE users (id INTEGER)")
        shared.execute("CREATE TABLE posts (id INTEGER)")

        private1 = engine.get_private_scope("agent1")
        private1.execute("CREATE TABLE notes (content TEXT)")

        private2 = engine.get_private_scope("agent2")
        private2.execute("CREATE TABLE tasks (title TEXT)")
        private2.execute("CREATE TABLE reminders (text TEXT)")

        tables = engine.list_all_tables()

        assert sorted(tables["shared"]) == ["posts", "users"]
        assert sorted(tables["private"]["agent1"]) == ["notes"]
        assert sorted(tables["private"]["agent2"]) == ["reminders", "tasks"]

        engine.close()


class TestDynamicMemoryEngineTransactions:
    """Test transactional behavior."""

    def test_transaction_commit(self, temp_db_path):
        """Committed transactions persist."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)
        scope = engine.get_shared_scope()

        scope.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        scope.begin()
        scope.execute("INSERT INTO users VALUES (1, 'Alice')")
        scope.commit()

        rows = scope.query("SELECT * FROM users")
        assert len(rows) == 1

        engine.close()

    def test_transaction_rollback(self, temp_db_path):
        """Rolled back transactions are discarded."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)
        scope = engine.get_shared_scope()

        scope.execute("CREATE TABLE users (id INTEGER, name TEXT)")
        scope.begin()
        scope.execute("INSERT INTO users VALUES (1, 'Alice')")
        scope.rollback()

        rows = scope.query("SELECT * FROM users")
        assert len(rows) == 0

        engine.close()

    def test_transaction_failure_rollback(self, temp_db_path):
        """Failed transactions can be rolled back."""
        engine = DynamicMemoryEngine(db_path=temp_db_path)
        scope = engine.get_shared_scope()

        scope.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        scope.begin()
        scope.execute("INSERT INTO users VALUES (1, 'Alice')")

        try:
            scope.execute("INSERT INTO users VALUES (1, 'Bob')")
        except Exception:
            scope.rollback()

        rows = scope.query("SELECT * FROM users")
        assert len(rows) == 0

        engine.close()
