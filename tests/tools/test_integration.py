"""Integration tests for the decorator-driven API."""

from pathlib import Path

import pytest

from naqsha.tools import AgentContext, RiskTier, ToolExecutor, ToolRegistry, agent


@pytest.fixture
def registry():
    """Create a fresh registry for each test."""
    return ToolRegistry()


@pytest.fixture
def context():
    """Create a sample context."""
    return AgentContext(
        shared_memory=None,
        private_memory=None,
        span=None,
        workspace_path=Path("/tmp/test"),
        agent_id="integration-agent",
        run_id="integration-run",
    )


def test_full_workflow(registry, context):
    """Test the complete workflow: define, register, execute."""

    @agent.tool(risk_tier=RiskTier.READ_ONLY, description="Calculate sum")
    def add(a: int, b: int) -> str:
        """Add two numbers."""
        return f"result: {a + b}"

    registry.register(add)

    assert registry.has("add")
    assert registry.get_risk_tier("add") == RiskTier.READ_ONLY
    assert registry.is_read_only("add")

    schemas = registry.export_schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "add"
    assert schemas[0]["description"] == "Calculate sum"

    executor = ToolExecutor(context)
    tool_func = registry.get("add")
    result = executor.execute(tool_func, {"a": 10, "b": 32})

    assert result.ok is True
    assert result.content == "result: 42"


def test_multiple_tools_workflow(registry, context):
    """Test workflow with multiple tools."""

    @agent.tool()
    def tool_a(x: int) -> str:
        """Tool A."""
        return f"a:{x}"

    @agent.tool(risk_tier=RiskTier.WRITE)
    def tool_b(y: str, ctx: AgentContext) -> str:
        """Tool B with context."""
        return f"b:{y}:{ctx.agent_id}"

    @agent.tool(risk_tier=RiskTier.HIGH)
    def tool_c(z: bool) -> str:
        """Tool C."""
        return f"c:{z}"

    registry.register(tool_a)
    registry.register(tool_b)
    registry.register(tool_c)

    assert registry.names() == frozenset(["tool_a", "tool_b", "tool_c"])

    assert registry.get_risk_tier("tool_a") == RiskTier.READ_ONLY
    assert registry.get_risk_tier("tool_b") == RiskTier.WRITE
    assert registry.get_risk_tier("tool_c") == RiskTier.HIGH

    executor = ToolExecutor(context)

    result_a = executor.execute(registry.get("tool_a"), {"x": 1})
    assert result_a.content == "a:1"

    result_b = executor.execute(registry.get("tool_b"), {"y": "test"})
    assert result_b.content == "b:test:integration-agent"

    result_c = executor.execute(registry.get("tool_c"), {"z": True})
    assert result_c.content == "c:True"


@pytest.mark.asyncio
async def test_async_workflow(registry, context):
    """Test workflow with async tools."""

    @agent.tool()
    async def async_add(a: int, b: int) -> str:
        """Async add."""
        return f"async_result: {a + b}"

    registry.register(async_add)

    executor = ToolExecutor(context)
    tool_func = registry.get("async_add")
    result = await executor.execute(tool_func, {"a": 20, "b": 22})

    assert result.ok is True
    assert result.content == "async_result: 42"


def test_schema_export_format(registry):
    """Test that exported schemas match expected format for Model Adapters."""

    @agent.tool(description="Read a file")
    def read_file(path: str, max_bytes: int = 1024) -> str:
        """Read file content."""
        return "content"

    registry.register(read_file)

    schemas = registry.export_schemas()
    assert len(schemas) == 1

    schema = schemas[0]

    assert schema["name"] == "read_file"
    assert schema["description"] == "Read a file"
    assert "parameters" in schema

    params = schema["parameters"]
    assert params["type"] == "object"
    assert "properties" in params
    assert "required" in params
    assert params["additionalProperties"] is False

    props = params["properties"]
    assert "path" in props
    assert props["path"]["type"] == "string"
    assert "max_bytes" in props
    assert props["max_bytes"]["type"] == "integer"

    assert "path" in params["required"]
    assert "max_bytes" not in params["required"]


def test_context_isolation(context):
    """Test that context is properly isolated per executor."""
    context1 = AgentContext(
        shared_memory=None,
        private_memory=None,
        span=None,
        workspace_path=Path("/tmp/agent1"),
        agent_id="agent-1",
        run_id="run-1",
    )

    context2 = AgentContext(
        shared_memory=None,
        private_memory=None,
        span=None,
        workspace_path=Path("/tmp/agent2"),
        agent_id="agent-2",
        run_id="run-2",
    )

    @agent.tool()
    def context_tool(ctx: AgentContext) -> str:
        """Uses context."""
        return ctx.agent_id

    executor1 = ToolExecutor(context1)
    executor2 = ToolExecutor(context2)

    result1 = executor1.execute(context_tool, {})
    result2 = executor2.execute(context_tool, {})

    assert result1.content == "agent-1"
    assert result2.content == "agent-2"
