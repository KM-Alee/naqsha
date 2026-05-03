"""Tests for ToolRegistry."""

import pytest

from naqsha.tools import RiskTier, ToolRegistry, agent


def test_registry_register_and_get():
    """Test registering and retrieving tools."""
    registry = ToolRegistry()

    @agent.tool()
    def sample_tool(x: int) -> str:
        """Sample tool."""
        return str(x)

    registry.register(sample_tool)
    
    retrieved = registry.get("sample_tool")
    assert retrieved is sample_tool


def test_registry_has():
    """Test checking if a tool is registered."""
    registry = ToolRegistry()

    @agent.tool()
    def sample_tool(x: int) -> str:
        """Sample tool."""
        return str(x)

    assert not registry.has("sample_tool")
    registry.register(sample_tool)
    assert registry.has("sample_tool")


def test_registry_names():
    """Test getting registered tool names."""
    registry = ToolRegistry()

    @agent.tool()
    def tool_a(x: int) -> str:
        """Tool A."""
        return str(x)

    @agent.tool()
    def tool_b(y: str) -> str:
        """Tool B."""
        return y

    registry.register(tool_a)
    registry.register(tool_b)
    
    names = registry.names()
    assert names == frozenset(["tool_a", "tool_b"])


def test_registry_export_schemas():
    """Test exporting schemas for Model Adapters."""
    registry = ToolRegistry()

    @agent.tool(description="First tool")
    def tool_one(x: int) -> str:
        """Tool one."""
        return str(x)

    @agent.tool(description="Second tool")
    def tool_two(y: str) -> str:
        """Tool two."""
        return y

    registry.register(tool_one)
    registry.register(tool_two)
    
    schemas = registry.export_schemas()
    assert len(schemas) == 2
    
    # Check that schemas are properly formatted
    names = {s["name"] for s in schemas}
    assert names == {"tool_one", "tool_two"}
    
    for schema in schemas:
        assert "name" in schema
        assert "description" in schema
        assert "parameters" in schema
        assert schema["parameters"]["type"] == "object"


def test_registry_get_risk_tier():
    """Test getting risk tier for tools."""
    registry = ToolRegistry()

    @agent.tool(risk_tier=RiskTier.WRITE)
    def write_tool(path: str) -> str:
        """Write tool."""
        return "ok"

    @agent.tool(risk_tier=RiskTier.READ_ONLY)
    def read_tool(path: str) -> str:
        """Read tool."""
        return "ok"

    registry.register(write_tool)
    registry.register(read_tool)
    
    assert registry.get_risk_tier("write_tool") == RiskTier.WRITE
    assert registry.get_risk_tier("read_tool") == RiskTier.READ_ONLY
    assert registry.get_risk_tier("nonexistent") is None


def test_registry_is_read_only():
    """Test checking if tools are read-only."""
    registry = ToolRegistry()

    @agent.tool(risk_tier=RiskTier.WRITE)
    def write_tool(path: str) -> str:
        """Write tool."""
        return "ok"

    @agent.tool(risk_tier=RiskTier.READ_ONLY)
    def read_tool(path: str) -> str:
        """Read tool."""
        return "ok"

    registry.register(write_tool)
    registry.register(read_tool)
    
    assert not registry.is_read_only("write_tool")
    assert registry.is_read_only("read_tool")
    assert not registry.is_read_only("nonexistent")


def test_registry_error_not_decorated():
    """Test error when registering non-decorated function."""
    registry = ToolRegistry()

    def not_a_tool(x: int) -> str:
        """Not decorated."""
        return str(x)

    with pytest.raises(ValueError, match="must be decorated"):
        registry.register(not_a_tool)


def test_registry_error_duplicate_name():
    """Test error when registering duplicate tool name."""
    registry = ToolRegistry()

    @agent.tool()
    def duplicate(x: int) -> str:
        """First."""
        return str(x)

    @agent.tool()
    def duplicate(y: int) -> str:  # noqa: F811
        """Second."""
        return str(y)

    registry.register(duplicate)
    
    with pytest.raises(ValueError, match="already registered"):
        registry.register(duplicate)


def test_registry_clear():
    """Test clearing the registry."""
    registry = ToolRegistry()

    @agent.tool()
    def sample_tool(x: int) -> str:
        """Sample tool."""
        return str(x)

    registry.register(sample_tool)
    assert registry.has("sample_tool")
    
    registry.clear()
    assert not registry.has("sample_tool")
    assert len(registry.names()) == 0


def test_registry_get_nonexistent():
    """Test getting a nonexistent tool returns None."""
    registry = ToolRegistry()
    assert registry.get("nonexistent") is None
