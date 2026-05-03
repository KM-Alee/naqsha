"""Tool contracts and starter tool implementations."""

# V2 Decorator-Driven API
# V1 compatibility
from naqsha.tools.base import (
    FunctionTool,
    Tool,
    ToolObservation,
    ToolSpec,
    validate_arguments,
)
from naqsha.tools.context import AgentContext
from naqsha.tools.decorated_adapter import decorated_to_function_tool
from naqsha.tools.decorator import RiskTier, ToolDefinitionError, agent, tool
from naqsha.tools.executor import ToolExecutor
from naqsha.tools.registry import ToolRegistry

__all__ = [
    # V2 API
    "AgentContext",
    "agent",
    "tool",
    "RiskTier",
    "ToolDefinitionError",
    "ToolRegistry",
    "ToolExecutor",
    "decorated_to_function_tool",
    # V1 API
    "Tool",
    "ToolSpec",
    "ToolObservation",
    "FunctionTool",
    "validate_arguments",
]
