"""Tests for ToolExecutor and context injection."""

from pathlib import Path

import pytest

from naqsha.tools import AgentContext, ToolExecutor, ToolObservation, agent


@pytest.fixture
def sample_context():
    """Create a sample AgentContext for testing."""
    return AgentContext(
        shared_memory=None,
        private_memory=None,
        span=None,
        workspace_path=Path("/tmp/test"),
        agent_id="test-agent",
        run_id="test-run-123",
    )


def test_executor_basic_execution(sample_context):
    """Test basic tool execution without context injection."""
    executor = ToolExecutor(sample_context)

    @agent.tool()
    def simple_tool(x: int, y: int) -> str:
        """Simple tool."""
        return f"sum={x + y}"

    result = executor.execute(simple_tool, {"x": 5, "y": 3})
    
    assert isinstance(result, ToolObservation)
    assert result.ok is True
    assert result.content == "sum=8"


@pytest.mark.asyncio
async def test_executor_async_tool(sample_context):
    """Test executing async tool."""
    executor = ToolExecutor(sample_context)

    @agent.tool()
    async def async_tool(text: str) -> str:
        """Async tool."""
        return f"async: {text}"

    result = await executor.execute(async_tool, {"text": "hello"})
    
    assert isinstance(result, ToolObservation)
    assert result.ok is True
    assert result.content == "async: hello"


def test_executor_context_injection(sample_context):
    """Test that AgentContext is injected when requested."""
    executor = ToolExecutor(sample_context)

    @agent.tool()
    def context_tool(text: str, ctx: AgentContext) -> str:
        """Tool with context."""
        return f"{text} from {ctx.agent_id}"

    result = executor.execute(context_tool, {"text": "hello"})
    
    assert isinstance(result, ToolObservation)
    assert result.ok is True
    assert result.content == "hello from test-agent"


def test_executor_context_not_in_arguments(sample_context):
    """Test that ctx is not required in arguments dict."""
    executor = ToolExecutor(sample_context)

    @agent.tool()
    def context_tool(ctx: AgentContext) -> str:
        """Tool with only context."""
        return f"run: {ctx.run_id}"

    # Arguments dict should not include ctx
    result = executor.execute(context_tool, {})
    
    assert isinstance(result, ToolObservation)
    assert result.ok is True
    assert result.content == "run: test-run-123"


def test_executor_string_return(sample_context):
    """Test tool returning string directly."""
    executor = ToolExecutor(sample_context)

    @agent.tool()
    def string_tool(text: str) -> str:
        """Returns string."""
        return text.upper()

    result = executor.execute(string_tool, {"text": "hello"})
    
    assert isinstance(result, ToolObservation)
    assert result.ok is True
    assert result.content == "HELLO"


def test_executor_observation_return(sample_context):
    """Test tool returning ToolObservation directly."""
    executor = ToolExecutor(sample_context)

    @agent.tool()
    def observation_tool(ok: bool) -> ToolObservation:
        """Returns observation."""
        return ToolObservation(ok=ok, content="explicit observation")

    result = executor.execute(observation_tool, {"ok": False})
    
    assert isinstance(result, ToolObservation)
    assert result.ok is False
    assert result.content == "explicit observation"


def test_executor_dict_return(sample_context):
    """Test tool returning dict."""
    executor = ToolExecutor(sample_context)

    @agent.tool()
    def dict_tool(ok: bool) -> dict:
        """Returns dict."""
        return {"ok": ok, "content": "dict result", "metadata": {"key": "value"}}

    result = executor.execute(dict_tool, {"ok": True})
    
    assert isinstance(result, ToolObservation)
    assert result.ok is True
    assert result.content == "dict result"
    assert result.metadata == {"key": "value"}


def test_executor_other_type_return(sample_context):
    """Test tool returning other types (converted to string)."""
    executor = ToolExecutor(sample_context)

    @agent.tool()
    def int_tool(x: int) -> int:
        """Returns int."""
        return x * 2

    result = executor.execute(int_tool, {"x": 21})
    
    assert isinstance(result, ToolObservation)
    assert result.ok is True
    assert result.content == "42"


@pytest.mark.asyncio
async def test_executor_async_with_context(sample_context):
    """Test async tool with context injection."""
    executor = ToolExecutor(sample_context)

    @agent.tool()
    async def async_context_tool(text: str, ctx: AgentContext) -> str:
        """Async tool with context."""
        return f"{text} in {ctx.workspace_path}"

    result = await executor.execute(async_context_tool, {"text": "working"})
    
    assert isinstance(result, ToolObservation)
    assert result.ok is True
    assert result.content == "working in /tmp/test"


def test_executor_failed_tool_returns_observation(sample_context):
    """Tool exceptions wrap as structured failed observations (structured escalation)."""

    executor = ToolExecutor(sample_context)

    @agent.tool()
    def failing_tool(x: int) -> str:
        raise ValueError("intentional failure")

    result = executor.execute(failing_tool, {"x": 1})
    assert isinstance(result, ToolObservation)
    assert result.ok is False
    assert "intentional failure" in result.content
    assert result.metadata and result.metadata.get("error") == "ValueError"
    assert result.metadata.get("tool_error") is True


def test_executor_multiple_params_with_context(sample_context):
    """Test tool with multiple params and context."""
    executor = ToolExecutor(sample_context)

    @agent.tool()
    def multi_tool(a: int, b: str, c: bool, ctx: AgentContext) -> str:
        """Multiple params."""
        return f"{a},{b},{c},{ctx.agent_id}"

    result = executor.execute(
        multi_tool,
        {"a": 42, "b": "test", "c": True},
    )
    
    assert isinstance(result, ToolObservation)
    assert result.ok is True
    assert result.content == "42,test,True,test-agent"
