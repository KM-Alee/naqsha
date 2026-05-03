"""Tests for the @agent.tool decorator and schema generation."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from naqsha.tools import AgentContext, RiskTier, ToolDefinitionError, agent


class SampleModel(BaseModel):
    """Sample Pydantic model for testing."""

    name: str
    count: int


def test_decorator_basic_primitives():
    """Test decorator with basic primitive types."""

    @agent.tool()
    def simple_tool(text: str, number: int) -> str:
        """A simple tool."""
        return f"{text}: {number}"

    assert hasattr(simple_tool, "__is_naqsha_tool__")
    assert hasattr(simple_tool, "__tool_schema__")
    assert hasattr(simple_tool, "__tool_risk_tier__")
    assert hasattr(simple_tool, "__tool_read_only__")

    schema = simple_tool.__tool_schema__
    assert schema["name"] == "simple_tool"
    assert schema["description"] == "A simple tool."
    assert schema["parameters"]["type"] == "object"
    assert schema["parameters"]["properties"]["text"]["type"] == "string"
    assert schema["parameters"]["properties"]["number"]["type"] == "integer"
    assert set(schema["parameters"]["required"]) == {"text", "number"}
    assert schema["parameters"]["additionalProperties"] is False


def test_decorator_all_primitive_types():
    """Test decorator with all supported primitive types."""

    @agent.tool()
    def all_types(
        a_str: str,
        an_int: int,
        a_float: float,
        a_bool: bool,
    ) -> str:
        """Tool with all primitive types."""
        return "ok"

    schema = all_types.__tool_schema__
    props = schema["parameters"]["properties"]
    assert props["a_str"]["type"] == "string"
    assert props["an_int"]["type"] == "integer"
    assert props["a_float"]["type"] == "number"
    assert props["a_bool"]["type"] == "boolean"


def test_decorator_optional_parameter():
    """Test decorator with Optional[T] parameter."""

    @agent.tool()
    def optional_tool(required: str, optional: int | None) -> str:
        """Tool with optional parameter."""
        return "ok"

    schema = optional_tool.__tool_schema__
    assert "required" in schema["parameters"]["required"]
    assert "optional" not in schema["parameters"]["required"]
    assert schema["parameters"]["properties"]["optional"]["type"] == "integer"


def test_decorator_with_default_value():
    """Test decorator with default parameter values."""

    @agent.tool()
    def default_tool(text: str, count: int = 5) -> str:
        """Tool with default value."""
        return "ok"

    schema = default_tool.__tool_schema__
    assert "text" in schema["parameters"]["required"]
    assert "count" not in schema["parameters"]["required"]


def test_decorator_list_type():
    """Test decorator with list[T] type."""

    @agent.tool()
    def list_tool(items: list[str]) -> str:
        """Tool with list parameter."""
        return "ok"

    schema = list_tool.__tool_schema__
    props = schema["parameters"]["properties"]
    assert props["items"]["type"] == "array"
    assert props["items"]["items"]["type"] == "string"


def test_decorator_dict_type():
    """Test decorator with dict[str, T] type."""

    @agent.tool()
    def dict_tool(mapping: dict[str, int]) -> str:
        """Tool with dict parameter."""
        return "ok"

    schema = dict_tool.__tool_schema__
    props = schema["parameters"]["properties"]
    assert props["mapping"]["type"] == "object"
    assert props["mapping"]["additionalProperties"]["type"] == "integer"


def test_decorator_pydantic_model():
    """Test decorator with Pydantic BaseModel parameter."""

    @agent.tool()
    def model_tool(data: SampleModel) -> str:
        """Tool with Pydantic model."""
        return "ok"

    schema = model_tool.__tool_schema__
    props = schema["parameters"]["properties"]
    # Pydantic generates its own schema
    assert "data" in props
    assert props["data"]["type"] == "object"
    assert "properties" in props["data"]


def test_decorator_async_function():
    """Test decorator with async def function."""

    @agent.tool()
    async def async_tool(text: str) -> str:
        """Async tool."""
        return text

    assert hasattr(async_tool, "__is_naqsha_tool__")
    schema = async_tool.__tool_schema__
    assert schema["name"] == "async_tool"


def test_decorator_context_injection_omitted():
    """Test that AgentContext parameter is omitted from schema."""

    @agent.tool()
    def context_tool(text: str, ctx: AgentContext) -> str:
        """Tool with context injection."""
        return text

    schema = context_tool.__tool_schema__
    props = schema["parameters"]["properties"]
    assert "text" in props
    assert "ctx" not in props
    assert schema["parameters"]["required"] == ["text"]


def test_decorator_risk_tier():
    """Test decorator with different risk tiers."""

    @agent.tool(risk_tier=RiskTier.WRITE)
    def write_tool(path: str) -> str:
        """Write tool."""
        return "ok"

    assert write_tool.__tool_risk_tier__ == RiskTier.WRITE
    assert write_tool.__tool_read_only__ is False

    @agent.tool(risk_tier=RiskTier.HIGH)
    def high_tool(cmd: str) -> str:
        """High risk tool."""
        return "ok"

    assert high_tool.__tool_risk_tier__ == RiskTier.HIGH
    assert high_tool.__tool_read_only__ is False

    @agent.tool(risk_tier=RiskTier.READ_ONLY)
    def read_tool(path: str) -> str:
        """Read tool."""
        return "ok"

    assert read_tool.__tool_risk_tier__ == RiskTier.READ_ONLY
    assert read_tool.__tool_read_only__ is True


def test_decorator_custom_description():
    """Test decorator with custom description."""

    @agent.tool(description="Custom description here")
    def described_tool(x: int) -> str:
        """This docstring is ignored."""
        return "ok"

    schema = described_tool.__tool_schema__
    assert schema["description"] == "Custom description here"


def test_decorator_docstring_description():
    """Test decorator uses first line of docstring."""

    @agent.tool()
    def docstring_tool(x: int) -> str:
        """
        First line of docstring.
        
        More details here.
        """
        return "ok"

    schema = docstring_tool.__tool_schema__
    assert schema["description"] == "First line of docstring."


def test_decorator_error_missing_type_hint():
    """Test decorator raises error for missing type hint."""

    with pytest.raises(ToolDefinitionError, match="must have a type hint"):

        @agent.tool()
        def bad_tool(text):  # Missing type hint
            """Bad tool."""
            return "ok"


def test_decorator_error_unsupported_type():
    """Test decorator raises error for unsupported type."""

    with pytest.raises(ToolDefinitionError, match="unsupported type hint"):

        @agent.tool()
        def bad_tool(obj: object) -> str:
            """Bad tool."""
            return "ok"


def test_decorator_error_untyped_list():
    """Test decorator raises error for untyped list."""

    with pytest.raises(ToolDefinitionError, match="unsupported type hint"):

        @agent.tool()
        def bad_tool(items: list) -> str:  # type: ignore[type-arg]
            """Bad tool."""
            return "ok"


def test_decorator_error_non_str_dict_key():
    """Test decorator raises error for dict with non-str keys."""

    with pytest.raises(ToolDefinitionError, match="dict keys must be str"):

        @agent.tool()
        def bad_tool(mapping: dict[int, str]) -> str:
            """Bad tool."""
            return "ok"


def test_decorator_complex_nested():
    """Test decorator with complex nested types."""

    @agent.tool()
    def nested_tool(
        items: list[dict[str, int]],
        optional_list: list[str] | None,
    ) -> str:
        """Tool with nested types."""
        return "ok"

    schema = nested_tool.__tool_schema__
    props = schema["parameters"]["properties"]
    
    # list[dict[str, int]]
    assert props["items"]["type"] == "array"
    assert props["items"]["items"]["type"] == "object"
    assert props["items"]["items"]["additionalProperties"]["type"] == "integer"
    
    # Optional[list[str]]
    assert props["optional_list"]["type"] == "array"
    assert props["optional_list"]["items"]["type"] == "string"
    assert "optional_list" not in schema["parameters"]["required"]


def test_decorator_preserves_function():
    """Test that decorator preserves the original function."""

    @agent.tool()
    def original(x: int) -> str:
        """Original function."""
        return f"x={x}"

    # Function should still be callable
    result = original(x=42)
    assert result == "x=42"


def test_decorator_multiple_context_params():
    """Test tool with multiple AgentContext parameters (edge case)."""

    @agent.tool()
    def multi_ctx(text: str, ctx: AgentContext, ctx2: AgentContext) -> str:
        """Tool with multiple context params."""
        return text

    schema = multi_ctx.__tool_schema__
    props = schema["parameters"]["properties"]
    # Both ctx params should be omitted
    assert "text" in props
    assert "ctx" not in props
    assert "ctx2" not in props
