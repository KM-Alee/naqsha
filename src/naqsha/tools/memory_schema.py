"""Memory Schema Tool for autonomous schema evolution.

Allows agents to create tables and indexes in their memory database.
"""

from __future__ import annotations

from naqsha.memory.ddl import ForbiddenDDLError, validate_ddl
from naqsha.tools.context import AgentContext
from naqsha.tools.decorator import RiskTier, agent


@agent.tool(
    risk_tier=RiskTier.WRITE,
    description="Execute DDL to create tables or indexes in agent memory. "
    "Only CREATE TABLE, CREATE INDEX, and ALTER TABLE ADD COLUMN are permitted.",
)
def memory_schema(sql: str, ctx: AgentContext) -> str:
    """Execute DDL statement to modify memory schema.

    This tool allows agents to autonomously evolve their memory schema by creating
    new tables, indexes, or adding columns. All DDL is validated against a safelist
    to prevent destructive operations.

    Permitted operations:
    - CREATE TABLE [IF NOT EXISTS] table_name (...)
    - CREATE [UNIQUE] INDEX index_name ON table_name (...)
    - ALTER TABLE table_name ADD COLUMN column_name type

    Forbidden operations:
    - DROP TABLE, DROP INDEX
    - DELETE, UPDATE, TRUNCATE, INSERT
    - Any other destructive DDL or DML

    The tool automatically applies namespace prefixes based on whether you're using
    shared or private memory.

    Args:
        sql: DDL statement to execute
        ctx: Agent context (automatically injected)

    Returns:
        Success message or error description
    """
    if not ctx.shared_memory and not ctx.private_memory:
        return "Error: No memory engine available. Memory must be configured for this agent."

    try:
        validate_ddl(sql)
    except ForbiddenDDLError as e:
        return f"DDL Error: {e}"

    scope = ctx.private_memory if ctx.private_memory else ctx.shared_memory

    if not scope:
        return "Error: No memory scope available"

    try:
        scope.execute(sql)
        return f"Successfully executed DDL statement. Namespace: {scope.namespace}"
    except Exception as e:
        return f"Execution Error: {type(e).__name__}: {e}"


@agent.tool(
    risk_tier=RiskTier.READ_ONLY,
    description="List all tables in agent memory (shared and private namespaces).",
)
def list_memory_tables(ctx: AgentContext) -> str:
    """List all memory tables accessible to this agent.

    Shows tables in both shared (team-wide) and private (agent-specific) namespaces.

    Args:
        ctx: Agent context (automatically injected)

    Returns:
        Formatted list of tables or error message
    """
    if not ctx.shared_memory and not ctx.private_memory:
        return "No memory engine available."

    tables_info = []

    if ctx.shared_memory:
        try:
            shared_tables = ctx.shared_memory.list_tables()
            if shared_tables:
                tables_info.append("Shared tables:")
                for table in shared_tables:
                    tables_info.append(f"  - shared_{table}")
            else:
                tables_info.append("Shared tables: (none)")
        except Exception as e:
            tables_info.append(f"Error listing shared tables: {e}")

    if ctx.private_memory:
        try:
            private_tables = ctx.private_memory.list_tables()
            if private_tables:
                tables_info.append(f"\nPrivate tables (agent {ctx.agent_id}):")
                for table in private_tables:
                    tables_info.append(f"  - private_{ctx.agent_id}_{table}")
            else:
                tables_info.append(f"\nPrivate tables (agent {ctx.agent_id}): (none)")
        except Exception as e:
            tables_info.append(f"Error listing private tables: {e}")

    return "\n".join(tables_info) if tables_info else "No tables found."
