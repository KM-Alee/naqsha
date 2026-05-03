"""Tests for memory_schema tool."""

import tempfile
from pathlib import Path

import pytest

from naqsha.memory.engine import DynamicMemoryEngine
from naqsha.tools.context import AgentContext
from naqsha.tools.decorator import RiskTier
from naqsha.tools.memory_schema import list_memory_tables, memory_schema


@pytest.fixture
def temp_db_path():
    """Create a temporary database path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "memory.db"


@pytest.fixture
def agent_context(temp_db_path):
    """Create an AgentContext with memory engine."""
    engine = DynamicMemoryEngine(db_path=temp_db_path)

    ctx = AgentContext(
        shared_memory=engine.get_shared_scope(),
        private_memory=engine.get_private_scope("test_agent"),
        span=None,
        workspace_path=Path("/tmp/workspace"),
        agent_id="test_agent",
        run_id="test_run",
    )

    yield ctx
    engine.close()


class TestMemorySchemaTool:
    """Test memory_schema tool."""

    def test_create_table_in_private_memory(self, agent_context):
        """Tool creates table in private memory."""
        result = memory_schema(
            "CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT)",
            ctx=agent_context,
        )

        assert "Successfully executed DDL" in result
        assert "private_test_agent_" in result

        tables = agent_context.private_memory.list_tables()
        assert "tasks" in tables

    def test_create_index(self, agent_context):
        """Tool creates index."""
        memory_schema(
            "CREATE TABLE users (id INTEGER, name TEXT)",
            ctx=agent_context,
        )

        result = memory_schema(
            "CREATE INDEX idx_users_name ON users(name)",
            ctx=agent_context,
        )

        assert "Successfully executed DDL" in result

    def test_alter_table_add_column(self, agent_context):
        """Tool adds column to existing table."""
        memory_schema(
            "CREATE TABLE users (id INTEGER)",
            ctx=agent_context,
        )

        result = memory_schema(
            "ALTER TABLE users ADD COLUMN name TEXT",
            ctx=agent_context,
        )

        assert "Successfully executed DDL" in result

    def test_drop_table_forbidden(self, agent_context):
        """Tool rejects DROP TABLE."""
        memory_schema(
            "CREATE TABLE users (id INTEGER)",
            ctx=agent_context,
        )

        result = memory_schema(
            "DROP TABLE users",
            ctx=agent_context,
        )

        assert "DDL Error" in result
        assert "Forbidden" in result

    def test_delete_forbidden(self, agent_context):
        """Tool rejects DELETE."""
        result = memory_schema(
            "DELETE FROM users",
            ctx=agent_context,
        )

        assert "DDL Error" in result
        assert "Forbidden" in result

    def test_update_forbidden(self, agent_context):
        """Tool rejects UPDATE."""
        result = memory_schema(
            "UPDATE users SET name = 'Alice'",
            ctx=agent_context,
        )

        assert "DDL Error" in result
        assert "Forbidden" in result

    def test_no_memory_engine(self):
        """Tool handles missing memory engine."""
        ctx = AgentContext(
            shared_memory=None,
            private_memory=None,
            span=None,
            workspace_path=Path("/tmp/workspace"),
            agent_id="test_agent",
            run_id="test_run",
        )

        result = memory_schema(
            "CREATE TABLE users (id INTEGER)",
            ctx=ctx,
        )

        assert "Error" in result
        assert "No memory engine available" in result

    def test_sql_execution_error(self, agent_context):
        """Tool handles SQL execution errors."""
        memory_schema(
            "CREATE TABLE users (id INTEGER PRIMARY KEY)",
            ctx=agent_context,
        )

        result = memory_schema(
            "CREATE TABLE users (id INTEGER)",
            ctx=agent_context,
        )

        assert "Execution Error" in result


class TestListMemoryTablesTool:
    """Test list_memory_tables tool."""

    def test_list_empty_memory(self, agent_context):
        """Tool lists empty memory."""
        result = list_memory_tables(ctx=agent_context)

        assert "Shared tables: (none)" in result
        assert "Private tables" in result
        assert "(none)" in result

    def test_list_shared_tables(self, agent_context):
        """Tool lists shared tables."""
        agent_context.shared_memory.execute("CREATE TABLE users (id INTEGER)")

        result = list_memory_tables(ctx=agent_context)

        assert "Shared tables:" in result
        assert "shared_users" in result

    def test_list_private_tables(self, agent_context):
        """Tool lists private tables."""
        agent_context.private_memory.execute("CREATE TABLE notes (content TEXT)")

        result = list_memory_tables(ctx=agent_context)

        assert "Private tables" in result
        assert "private_test_agent_notes" in result

    def test_list_both_shared_and_private(self, agent_context):
        """Tool lists both shared and private tables."""
        agent_context.shared_memory.execute("CREATE TABLE users (id INTEGER)")

        agent_context.private_memory.execute("CREATE TABLE notes (content TEXT)")

        result = list_memory_tables(ctx=agent_context)

        assert "shared_users" in result
        assert "private_test_agent_notes" in result

    def test_list_no_memory_engine(self):
        """Tool handles missing memory engine."""
        ctx = AgentContext(
            shared_memory=None,
            private_memory=None,
            span=None,
            workspace_path=Path("/tmp/workspace"),
            agent_id="test_agent",
            run_id="test_run",
        )

        result = list_memory_tables(ctx=ctx)

        assert "No memory engine available" in result


class TestMemorySchemaToolRegistration:
    """Test that memory_schema tools are properly decorated."""

    def test_memory_schema_has_tool_schema(self):
        """memory_schema tool has __tool_schema__."""
        assert hasattr(memory_schema, "__tool_schema__")
        schema = memory_schema.__tool_schema__
        assert "parameters" in schema
        assert "properties" in schema["parameters"]
        assert "sql" in schema["parameters"]["properties"]

    def test_memory_schema_risk_tier(self):
        """memory_schema tool has write risk tier."""
        assert hasattr(memory_schema, "__tool_risk_tier__")
        assert memory_schema.__tool_risk_tier__ == RiskTier.WRITE

    def test_list_memory_tables_has_tool_schema(self):
        """list_memory_tables tool has __tool_schema__."""
        assert hasattr(list_memory_tables, "__tool_schema__")
        schema = list_memory_tables.__tool_schema__
        assert "parameters" in schema
        assert "properties" in schema["parameters"]
        assert len(schema["parameters"]["properties"]) == 0

    def test_list_memory_tables_risk_tier(self):
        """list_memory_tables tool has read risk tier."""
        assert hasattr(list_memory_tables, "__tool_risk_tier__")
        assert list_memory_tables.__tool_risk_tier__ == RiskTier.READ_ONLY
